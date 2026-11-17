"""Gestione della batteria per un tablet sempre collegato.

Obiettivo: tenere la batteria tra `min` e `max` (es. 40-80%) invece che sempre al
100%, così non si gonfia e resta comunque una riserva in caso di blackout.

Metodi, in ordine di preferenza:
  1. "kernel": se il driver espone charge_control_end_threshold, si imposta la soglia
     e fa tutto l'hardware.
  2. "presa": altrimenti si accende/spegne una presa smart di Home Assistant che
     alimenta il caricatore (sotto min -> accendi, sopra max -> spegni).
  3. "lettura": nessun controllo possibile, solo monitoraggio e avviso.
"""
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from .homeassistant import HomeAssistant

log = logging.getLogger("batteria")
SYS = Path("/sys/class/power_supply")

STATI = {
    "Charging": "In carica",
    "Discharging": "A batteria",
    "Full": "Carica completa",
    "Not charging": "Collegato, non in carica",
    "Unknown": "Sconosciuto",
}
ALIMENTATORI = {"Mains", "USB", "USB_C", "USB_PD", "USB_PD_DRP", "USB_DCP", "USB_CDP", "USB_ACA", "USB_TYPE_C"}


def _r(path, default=""):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def _int(path):
    try:
        return int(_r(path))
    except ValueError:
        return None


def leggi(root=SYS):
    """Stato della batteria letto da sysfs."""
    out = {"presente": False}
    root = Path(root)
    if not root.is_dir():
        return out
    batt, alim = None, None
    for d in sorted(root.iterdir()):
        t = _r(d / "type")
        if t == "Battery":
            if batt is None and _r(d / "present", "1") != "0" and _r(d / "scope") != "Device":
                batt = d
        elif t in ALIMENTATORI:
            if _r(d / "online") == "1":
                alim = True
            elif alim is None:
                alim = False
    if batt is None:
        return out

    cap = _int(batt / "capacity")
    if cap is None:
        for now, full in (("energy_now", "energy_full"), ("charge_now", "charge_full")):
            n, f = _int(batt / now), _int(batt / full)
            if n is not None and f:
                cap = round(100 * n / f)
                break
    status = _r(batt / "status", "Unknown")
    t = _int(batt / "temp")
    if alim is None:
        alim = status in ("Charging", "Full", "Not charging")
    soglia = batt / "charge_control_end_threshold"
    out.update({
        "presente": True,
        "nome": batt.name,
        "percentuale": cap,
        "stato": status,
        "stato_it": STATI.get(status, status),
        "alimentato": alim,
        "temperatura": round(t / 10, 1) if t is not None else None,
        "salute": _r(batt / "health"),
        "soglia_kernel": str(soglia) if soglia.exists() else "",
        "soglia_attuale": _int(soglia) if soglia.exists() else None,
    })
    return out


def decidi(percentuale, alimentato, minimo, massimo):
    """'on' / 'off' / None per la presa del caricatore."""
    if percentuale is None:
        return None
    if percentuale <= minimo and not alimentato:
        return "on"
    if percentuale >= massimo and alimentato:
        return "off"
    return None


class BatteryManager:
    INTERVALLO = 30           # secondi tra un controllo e l'altro
    RIPETI_DOPO = 120         # non ripetere lo stesso comando prima di N secondi
    SENSORI_OGNI = 120

    def __init__(self, full_cfg, root=SYS):
        self.root = root
        self.stato = {"presente": False}
        self._wake = threading.Event()
        self._ultimo_cmd = (None, float("-inf"))
        self._ultimi_sensori = float("-inf")
        self._azione = ""
        self._errore = ""
        self.configure(full_cfg)

    def configure(self, full):
        self.cfg = dict(full["batteria"])
        h = full["homeassistant"]
        self.ha = HomeAssistant(h.get("url"), h.get("token"))
        self._wake.set()

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:          # non deve mai fermare il demone
                log.exception("batteria: %s", e)
            self._wake.wait(self.INTERVALLO)
            self._wake.clear()

    # ------------------------------------------------------------
    def tick(self):
        b = leggi(self.root)
        c = self.cfg
        st = dict(b, min=c["min"], max=c["max"], allarme=c["allarme_min"], presa=c["presa"],
                  metodo="assente", avviso=False)
        if not b["presente"]:
            self.stato = dict(st, azione=self._azione, errore=self._errore)
            return

        if not c["gestione"]:
            st["metodo"] = "disattivata"
        elif b["soglia_kernel"]:
            st["metodo"] = "kernel"
            self._imposta_soglia(b)
        elif c["presa"] and self.ha.configurato:
            st["metodo"] = "presa"
            azione = decidi(b["percentuale"], b["alimentato"], c["min"], c["max"])
            if azione:
                self._comanda(azione, automatico=True)
        else:
            st["metodo"] = "lettura"

        p = b["percentuale"]
        st["avviso"] = p is not None and p <= c["allarme_min"] and not b["alimentato"]
        if c["invia_ha"] and self.ha.configurato and time.monotonic() - self._ultimi_sensori > self.SENSORI_OGNI:
            self._invia_sensori(b)
        self.stato = dict(st, azione=self._azione, errore=self._errore)

    def _imposta_soglia(self, b):
        try:
            if b["soglia_attuale"] != self.cfg["max"]:
                Path(b["soglia_kernel"]).write_text(str(self.cfg["max"]))
                self._azione = f"soglia di carica impostata a {self.cfg['max']}%"
            start = Path(b["soglia_kernel"]).with_name("charge_control_start_threshold")
            if start.exists() and _int(start) != self.cfg["min"]:
                start.write_text(str(self.cfg["min"]))
            self._errore = ""
        except OSError as e:
            self._errore = f"impossibile impostare la soglia ({e.strerror})"

    def _comanda(self, azione, automatico):
        cmd, quando = self._ultimo_cmd
        if automatico and cmd == azione and time.monotonic() - quando < self.RIPETI_DOPO:
            return
        self._ultimo_cmd = (azione, time.monotonic())
        on = azione == "on"
        try:
            self.ha.accendi(self.cfg["presa"], on)
            ora = datetime.now().strftime("%H:%M")
            self._azione = f"presa {'accesa' if on else 'spenta'} alle {ora}" + ("" if automatico else " (manuale)")
            self._errore = ""
            log.info(self._azione)
        except Exception as e:
            self._errore = f"presa: {e}"
            log.warning(self._errore)

    def presa_manuale(self, on):
        if not (self.cfg["presa"] and self.ha.configurato):
            return {"ok": False, "errore": "presa o Home Assistant non configurati"}
        self._comanda("on" if on else "off", automatico=False)
        self._wake.set()
        return {"ok": not self._errore, "errore": self._errore, "azione": self._azione}

    def _invia_sensori(self, b):
        self._ultimi_sensori = time.monotonic()
        try:
            self.ha.imposta_stato("sensor.comodino_batteria", b["percentuale"], {
                "unit_of_measurement": "%",
                "device_class": "battery",
                "state_class": "measurement",
                "friendly_name": "Comodino batteria",
                "in_carica": b["stato"] == "Charging",
                "alimentato": b["alimentato"],
                "stato": b["stato_it"],
            })
            if b["temperatura"] is not None:
                self.ha.imposta_stato("sensor.comodino_batteria_temperatura", b["temperatura"], {
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "friendly_name": "Comodino temperatura batteria",
                })
        except Exception as e:
            log.warning("sensori HA: %s", e)
