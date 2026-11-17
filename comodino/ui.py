"""Interfaccia a tutto schermo (PySide6 + QML).

Avvio:  python3 -m comodino.ui          (kiosk, a tutto schermo, tastiera virtuale)
        python3 -m comodino.ui --dev    (finestra 1280x800, per provarla sul PC)
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DEV = "--dev" in sys.argv
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
if not DEV:
    os.environ.setdefault("QT_IM_MODULE", "qtvirtualkeyboard")

from PySide6.QtCore import Property, QObject, Qt, QTimer, QUrl, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from . import config, geocode, icsparse, ota, sistema, weather  # noqa: E402
from .luminosita import Backlight  # noqa: E402
from .homeassistant import HomeAssistant  # noqa: E402
from .webconfig import WebConfig  # noqa: E402


def _hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


class Backend(QObject):
    meteoChanged = Signal()
    agendaChanged = Signal()
    svegliaChanged = Signal()
    notteChanged = Signal()
    erroreChanged = Signal()
    configChanged = Signal()
    haChanged = Signal()
    webChanged = Signal()
    risultato = Signal(str, "QVariant")      # esito delle operazioni lente (nome, dati)

    _meteoPronto = Signal(object)
    _agendaPronta = Signal(object, object)
    _haPronto = Signal(object)
    _climaPronto = Signal(object)
    climaChanged = Signal()
    _webStato = Signal()
    _webSalvato = Signal()
    otaChanged = Signal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._meteo = {}
        self._agenda = []
        self._ha = []
        self._clima = {}
        self._sveglia = {"attiva": False, "ora": 7, "minuto": 0, "giorni": [],
                         "suona": False, "prossima": None, "snooze_fino": None,
                         "connessa": False}
        self._notte = False
        self._errore = ""
        self._awake_until = 0.0
        self.backlight = Backlight(cfg["schermo"]["retroilluminazione"])
        self._wake = {k: threading.Event() for k in ("meteo", "agenda", "ha")}

        self._meteoPronto.connect(self._set_meteo)
        self._agendaPronta.connect(self._set_agenda)
        self._haPronto.connect(self._set_ha)
        self._climaPronto.connect(self._set_clima)
        self._webStato.connect(self.webChanged)
        self._webSalvato.connect(self._ricarica)     # dal thread del server web al thread principale
        self.web = WebConfig(on_saved=self._salvato_da_web, on_state=self._webStato.emit)

        for target in (self._loop_meteo, self._loop_agenda, self._loop_ha):
            threading.Thread(target=target, daemon=True).start()

        self._t_alarm = QTimer(self, interval=1000, timeout=self._poll_alarm)
        self._t_alarm.start()
        self._t_screen = QTimer(self, interval=5000, timeout=self._update_screen)
        self._t_screen.start()

        self._ota = {"stato": "", "errore": "", "disponibile": None, "occupato": False,
                     "ultimo_controllo": 0.0}
        self.risultato.connect(self._ota_esito)
        self._t_ota = QTimer(self, interval=15 * 60 * 1000, timeout=self._ota_notturno)
        self._t_ota.start()
        self._update_screen()

    @property
    def tz(self):
        return ZoneInfo(self.cfg["luogo"]["fuso"])

    # ================================================ proprietà per QML
    @Property("QVariantMap", notify=meteoChanged)
    def meteo(self):
        return self._meteo

    @Property("QVariantList", notify=agendaChanged)
    def agenda(self):
        return self._agenda

    @Property("QVariantMap", notify=svegliaChanged)
    def sveglia(self):
        return self._sveglia

    @Property(bool, notify=notteChanged)
    def notte(self):
        return self._notte

    @Property(str, notify=erroreChanged)
    def errore(self):
        return self._errore

    @Property("QVariantMap", notify=climaChanged)
    def clima(self):
        return self._clima

    @Property("QVariantList", notify=haChanged)
    def haEntita(self):
        return self._ha

    @Property("QVariantMap", notify=configChanged)
    def impostazioni(self):
        c = self.cfg
        return {
            "citta": c["luogo"]["nome"],
            "lat": c["luogo"]["lat"], "lon": c["luogo"]["lon"],
            "rotazione": c["schermo"]["rotazione"],
            "tema": c["schermo"]["tema"],
            "layout": c["schermo"]["layout"],
            "notte_stile": c["schermo"]["notte_stile"],
            "notte_inizio": c["schermo"]["notte_inizio"],
            "notte_fine": c["schermo"]["notte_fine"],
            "luminosita_giorno": c["schermo"]["luminosita_giorno"],
            "luminosita_notte": c["schermo"]["luminosita_notte"],
            "calendari": len(c["calendario"]["ics_urls"]),
            "ha_url": c["homeassistant"]["url"],
            "ha_token": bool(c["homeassistant"]["token"]),
            "ha_entita": len(c["homeassistant"]["entita"]),
            "ha_anticipo": c["homeassistant"]["anticipo_min"],
            "batt_gestione": c["batteria"]["gestione"],
            "batt_min": c["batteria"]["min"],
            "batt_max": c["batteria"]["max"],
            "batt_allarme": c["batteria"]["allarme_min"],
            "batt_presa": c["batteria"]["presa"],
        }

    @Property("QVariantMap", notify=svegliaChanged)
    def batteria(self):
        return self._sveglia.get("batteria") or {"presente": False}

    @Property("QVariantMap", notify=configChanged)
    def luminosita(self):
        return self.backlight.stato()

    @Property(int, notify=configChanged)
    def rotazione(self):
        return self.cfg["schermo"]["rotazione"]

    @Property(str, notify=configChanged)
    def citta(self):
        return self.cfg["luogo"]["nome"]

    @Property("QVariantMap", notify=otaChanged)
    def otaStato(self):
        a = self.cfg["aggiornamenti"]
        loc = ota.stato_locale()
        d = self._ota["disponibile"] or {}
        return {
            "versione": loc["versione"],
            "da_aggiornamento": loc["da_aggiornamento"],
            "precedente": loc["precedente"],
            "repo": a["repo"],
            "automatico": a["automatico"],
            "chiave": ota.chiave_pubblica() is not None,
            "nuova": d.get("versione", ""),
            "note": d.get("note", ""),
            "data": d.get("data", ""),
            "stato": self._ota["stato"],
            "errore": self._ota["errore"],
            "occupato": self._ota["occupato"],
        }

    @Property("QVariantMap", notify=webChanged)
    def webStato(self):
        if not self.web.attivo:
            return {"attivo": False}
        ip = sistema.local_ip() or "IP-del-tablet"
        return {"attivo": True, "pin": self.web.pin,
                "url": f"http://{ip}:{self.web.porta}",
                "scade": datetime.fromtimestamp(self.web.scade).strftime("%H:%M")}

    # ================================================ aggiornamenti in background
    def _sleep(self, key, seconds):
        ev = self._wake[key]
        ev.wait(seconds)
        ev.clear()

    def _loop_meteo(self):
        while True:
            l = self.cfg["luogo"]
            try:
                dati = weather.fetch(l["lat"], l["lon"], l["fuso"])
                try:
                    dati["aria"] = weather.aria(l["lat"], l["lon"], l["fuso"])
                except Exception as e:          # la qualità dell'aria è un extra
                    print("aria:", e, file=sys.stderr)
                    dati["aria"] = {}
                self._meteoPronto.emit(dati)
                delay = self.cfg["meteo"]["aggiorna_min"] * 60
            except Exception as e:
                print("meteo:", e, file=sys.stderr)
                delay = 60          # rete non ancora pronta: riprova presto
            self._sleep("meteo", delay)

    def _loop_agenda(self):
        while True:
            c = self.cfg["calendario"]
            rows, errors = icsparse.load_agenda(c["ics_urls"], self.cfg["luogo"]["fuso"], c["giorni"])
            self._agendaPronta.emit(rows, errors)
            self._sleep("agenda", 30 if errors else c["aggiorna_min"] * 60)

    def _loop_ha(self):
        while True:
            h = self.cfg["homeassistant"]
            ha = HomeAssistant(h["url"], h["token"])
            if ha.configurato and h["entita"]:
                self._haPronto.emit(ha.stati(h["entita"]))
            else:
                self._haPronto.emit([])
            self._climaPronto.emit(self._leggi_clima(ha))
            self._sleep("ha", 30)

    @Slot(object)
    def _set_meteo(self, data):
        self._meteo = data
        self.meteoChanged.emit()

    @Slot(object, object)
    def _set_agenda(self, rows, errors):
        if not errors or rows:
            self._agenda = rows
            self.agendaChanged.emit()
        err = ("Calendario: " + errors[0]) if errors else ""
        if not self.cfg["calendario"]["ics_urls"]:
            err = "Nessun calendario configurato"
        if err != self._errore:
            self._errore = err
            self.erroreChanged.emit()

    def _leggi_clima(self, ha):
        """{'interno': {temp, umidita}, 'esterno': {...}} dai sensori di HA (se configurati)."""
        c = self.cfg["clima"]
        out = {}
        if not ha.configurato:
            return out
        ids = {k: v for k, v in c.items() if v}
        if not ids:
            return out
        stati = {s["id"]: s for s in ha.stati(list(ids.values()))}
        for luogo in ("interno", "esterno"):
            val = {}
            for grandezza in ("temp", "umidita"):
                eid = c.get(f"{luogo}_{grandezza}")
                try:
                    v = float(stati[eid]["stato"]) if eid else None
                except (KeyError, TypeError, ValueError):
                    v = None
                if v is not None:
                    val[grandezza] = round(v, 1) if grandezza == "temp" else round(v)
            if val:
                out[luogo] = val
        return out

    @Slot(object)
    def _set_clima(self, data):
        if data != self._clima:
            self._clima = data
            self.climaChanged.emit()

    @Slot(object)
    def _set_ha(self, data):
        if data != self._ha:
            self._ha = data
            self.haChanged.emit()

    # ================================================ sveglia (client del demone)
    def _alarm_request(self, payload, timeout=0.5):
        with socket.create_connection(("127.0.0.1", self.cfg["sveglia"]["porta"]), timeout=timeout) as s:
            s.sendall((json.dumps(payload) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        return json.loads(buf)

    def _call(self, payload):
        try:
            resp = self._alarm_request(payload)
            if not resp.get("ok"):
                return
            st = dict(resp["stato"], connessa=True)
        except (OSError, ValueError):
            st = dict(self._sveglia, connessa=False, suona=False)
        if st != self._sveglia:
            was_ringing = self._sveglia.get("suona")
            self._sveglia = st
            self.svegliaChanged.emit()
            if st.get("suona") != was_ringing:
                self._update_screen()

    def _poll_alarm(self):
        self._call({"cmd": "stato"})

    @Slot(bool, int, int, list)
    def impostaSveglia(self, attiva, ora, minuto, giorni):
        self._call({"cmd": "imposta", "attiva": attiva, "ora": ora,
                    "minuto": minuto, "giorni": [int(g) for g in giorni]})

    @Slot()
    def snooze(self):
        self._call({"cmd": "snooze"})

    @Slot()
    def stop(self):
        self._call({"cmd": "stop"})

    @Slot()
    def provaSveglia(self):
        self._call({"cmd": "prova"})

    # ================================================ schermo giorno/notte
    def _is_night(self):
        s = self.cfg["schermo"]
        now = datetime.now(self.tz)
        m = now.hour * 60 + now.minute
        a, b = _hm(s["notte_inizio"]), _hm(s["notte_fine"])
        return (a <= m < b) if a < b else (m >= a or m < b)

    def _update_screen(self, force=False):
        s = self.cfg["schermo"]
        night = self._is_night()
        if night != self._notte:
            self._notte = night
            self.notteChanged.emit()
        bright = (self._sveglia.get("suona") or not night
                  or time.monotonic() < self._awake_until)
        self.backlight.set(s["luminosita_giorno"] if bright else s["luminosita_notte"], force)

    @Slot()
    def tocco(self):
        """Di notte un tocco riaccende lo schermo per qualche secondo."""
        self._awake_until = time.monotonic() + self.cfg["schermo"]["risveglio_tocco_sec"]
        self._update_screen()

    # ================================================ impostazioni
    def _salva(self, parziale):
        config.save_overrides(parziale)
        self._ricarica()

    # quali aggiornamenti in background dipendono da quali sezioni della configurazione
    _DIPENDENZE = {"meteo": ("luogo", "meteo"),
                   "agenda": ("calendario", "luogo"),
                   "ha": ("homeassistant", "clima")}

    @Slot()
    def _ricarica(self):
        vecchia, self.cfg = self.cfg, config.load()
        if vecchia["schermo"]["retroilluminazione"] != self.cfg["schermo"]["retroilluminazione"]:
            self.backlight.scegli(self.cfg["schermo"]["retroilluminazione"])
        self._update_screen(force=True)
        self.configChanged.emit()
        for loop, sezioni in self._DIPENDENZE.items():
            if any(vecchia.get(k) != self.cfg.get(k) for k in sezioni):
                self._wake[loop].set()
        try:
            self._alarm_request({"cmd": "ricarica"})
        except (OSError, ValueError):
            pass

    def _salvato_da_web(self):
        # chiamato dal thread del server web: il segnale lo porta sul thread principale
        self._webSalvato.emit()

    def _async(self, nome, fn, *args):
        def run():
            try:
                res = fn(*args)
            except Exception as e:
                res = {"ok": False, "errore": str(e)}
            self.risultato.emit(nome, res)
        threading.Thread(target=run, daemon=True).start()

    @Slot(int)
    def impostaRotazione(self, gradi):
        self._salva({"schermo": {"rotazione": int(gradi) % 360}})

    @Slot()
    def prossimaRetroilluminazione(self):
        alt = self.backlight.stato()["alternative"]
        if len(alt) > 1:
            cur = self.backlight.dev.name if self.backlight.dev else ""
            nxt = alt[(alt.index(cur) + 1) % len(alt)] if cur in alt else alt[0]
            self._salva({"schermo": {"retroilluminazione": nxt}})

    @Slot(str)
    def impostaLayout(self, nome):
        if nome in ("classico", "stazione"):
            self._salva({"schermo": {"layout": nome}})

    @Slot(str)
    def impostaTema(self, nome):
        if re.fullmatch(r"[a-z]{1,20}", nome):
            self._salva({"schermo": {"tema": nome}})

    @Slot(str)
    def impostaStileNotte(self, nome):
        if re.fullmatch(r"[a-z]{1,20}", nome):
            self._salva({"schermo": {"notte_stile": nome}})

    @Slot(str, str)
    def impostaNotte(self, inizio, fine):
        self._salva({"schermo": {"notte_inizio": inizio, "notte_fine": fine}})

    @Slot(int, int)
    def impostaLuminosita(self, giorno, notte):
        self._salva({"schermo": {"luminosita_giorno": max(5, min(100, giorno)),
                                 "luminosita_notte": max(1, min(100, notte))}})

    @Slot(str)
    def cercaLuogo(self, testo):
        self._async("luogo", geocode.cerca, testo)

    @Slot(str, float, float, str)
    def impostaLuogo(self, nome, lat, lon, fuso):
        self._salva({"luogo": {"nome": nome, "lat": lat, "lon": lon, "fuso": fuso}})

    @Slot()
    def wifiScansiona(self):
        self._async("wifi_reti", sistema.wifi_scan)

    @Slot(str, str)
    def wifiConnetti(self, ssid, password):
        self._async("wifi_connetti", sistema.wifi_connect, ssid, password)

    @Slot()
    def wifiStato(self):
        def stato():
            return dict(sistema.wifi_status(), ip=sistema.local_ip())
        self._async("wifi_stato", stato)

    @Slot(str)
    def haToggle(self, entity_id):
        h = self.cfg["homeassistant"]

        def go():
            HomeAssistant(h["url"], h["token"]).toggle(entity_id)
            time.sleep(0.5)
            self._wake["ha"].set()
            return {"ok": True}
        self._async("ha_toggle", go)

    # ---------------------------------------------- aggiornamenti via GitHub
    def _ota_set(self, **kw):
        self._ota.update(kw)
        self.otaChanged.emit()

    def _sveglia_vicina(self, minuti=60):
        s = self._sveglia
        if s.get("suona"):
            return True
        for k in ("prossima", "snooze_fino"):
            if s.get(k):
                try:
                    t = datetime.fromisoformat(s[k])
                    if timedelta(0) <= t - datetime.now() <= timedelta(minutes=minuti):
                        return True
                except ValueError:
                    pass
        return False

    def _ota_controlla(self):
        a = self.cfg["aggiornamenti"]
        info = ota.ultima_release(a["repo"], a["token"])
        nuova = ota.versione(info["versione"]) > ota.versione(ota.__version__)
        return {"ok": True, "info": info if nuova else None,
                "messaggio": f"Disponibile la versione {info['versione']}" if nuova
                             else f"Sei già all'ultima versione ({ota.__version__})"}

    @Slot()
    def otaControlla(self):
        if self._ota["occupato"]:
            return
        self._ota_set(occupato=True, stato="Controllo in corso…", errore="")
        self._async("ota_controlla", self._ota_controlla)

    @Slot()
    def otaInstalla(self):
        info = self._ota["disponibile"]
        if self._ota["occupato"] or not info:
            return
        if self._sveglia_vicina(15):
            self._ota_set(errore="Sveglia imminente: riprova più tardi")
            return
        self._ota_set(occupato=True, stato=f"Installo la versione {info['versione']}…", errore="")
        a = self.cfg["aggiornamenti"]
        self._async("ota_installa", lambda: {"ok": True, "versione": ota.installa(info, a["token"])})

    @Slot()
    def otaRipristina(self):
        if self._ota["occupato"]:
            return
        self._ota_set(occupato=True, stato="Ripristino…", errore="")
        self._async("ota_ripristina", lambda: {"ok": True, "versione": ota.ripristina()})

    @Slot(bool)
    def otaAutomatico(self, on):
        self._salva({"aggiornamenti": {"automatico": bool(on)}})
        self.otaChanged.emit()

    @Slot(str, "QVariant")
    def _ota_esito(self, nome, dati):
        if not nome.startswith("ota_"):
            return
        ok = bool(dati and dati.get("ok"))
        err = "" if ok else (dati or {}).get("errore", "errore sconosciuto")
        if nome == "ota_controlla":
            self._ota_set(occupato=False, ultimo_controllo=time.time(), errore=err,
                          disponibile=dati.get("info") if ok else self._ota["disponibile"],
                          stato=dati.get("messaggio", "") if ok else "")
            if ok and dati.get("info") and getattr(self, "_ota_auto_installa", False):
                self._ota_auto_installa = False
                if not self._sveglia_vicina(60):
                    self.otaInstalla()
        elif nome in ("ota_installa", "ota_ripristina"):
            if ok:
                self._ota_set(occupato=True, disponibile=None,
                              stato=f"Versione {dati['versione']} pronta: riavvio dell'app…")
                self._riavvia_app()
            else:
                self._ota_set(occupato=False, stato="", errore=err)

    def _riavvia_app(self):
        """Riavvia il demone sveglia e l'interfaccia (session.sh la rilancia con la nuova versione)."""
        if DEV:
            self._ota_set(occupato=False, stato="Installata: riavvia l'app per usarla")
            return
        try:
            subprocess.run(["systemctl", "--user", "restart", "comodino-alarmd"], timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            pass
        QTimer.singleShot(1500, QGuiApplication.quit)

    def _ota_notturno(self):
        """Ogni 15 minuti: tra le 03:00 e le 05:00, una volta al giorno, controlla e installa."""
        a = self.cfg["aggiornamenti"]
        if not (a["automatico"] and a["repo"]) or self._ota["occupato"]:
            return
        if not 3 <= datetime.now().hour < 5 or time.time() - self._ota["ultimo_controllo"] < 20 * 3600:
            return
        if self._sveglia_vicina(60):
            return
        self._ota_auto_installa = True
        self.otaControlla()

    # ---------------------------------------------- batteria
    @Slot(int, int, int)
    def impostaBatteria(self, minimo, massimo, allarme):
        minimo = max(10, min(90, minimo))
        massimo = max(minimo + 10, min(100, massimo))
        allarme = max(5, min(minimo - 5, allarme))
        self._salva({"batteria": {"min": minimo, "max": massimo, "allarme_min": allarme}})

    @Slot(bool)
    def gestioneBatteria(self, on):
        self._salva({"batteria": {"gestione": bool(on)}})

    @Slot(str)
    def impostaPresa(self, entity_id):
        self._salva({"batteria": {"presa": entity_id}})

    @Slot()
    def cercaPrese(self):
        h = self.cfg["homeassistant"]

        def go():
            ha = HomeAssistant(h["url"], h["token"])
            if not ha.configurato:
                return {"ok": False, "errore": "configura prima Home Assistant (scheda Da PC)"}
            prese = ha.prese()
            if not prese:
                return {"ok": False, "errore": "nessun interruttore (switch.*) trovato in Home Assistant"}
            return {"ok": True, "prese": prese}
        self._async("prese", go)

    @Slot(bool)
    def provaPresa(self, on):
        def go():
            r = self._alarm_request({"cmd": "presa", "on": on}, timeout=15)
            if not r.get("ok"):
                return {"ok": False, "errore": r.get("errore", "errore")}
            return {"ok": True, "messaggio": "Presa accesa" if on else "Presa spenta"}
        self._async("presa", go)

    @Slot(bool)
    def webAttiva(self, on):
        if on:
            w = self.cfg["web"]
            try:
                self.web.start(w["porta"], w["durata_min"])
            except OSError as e:
                self.risultato.emit("web", {"ok": False, "errore": f"porta {w['porta']} occupata ({e})"})
        else:
            self.web.stop()

    @Slot()
    def riavvia(self):
        sistema.reboot()

    @Slot()
    def spegni(self):
        sistema.poweroff()

    @Slot()
    def diagnostica(self):
        for ev in self._wake.values():
            ev.set()
        self._async("diagnostica", self._diagnostica)

    def _diagnostica(self):
        c = self.cfg
        voci = []

        def voce(nome, ok, dettaglio):
            voci.append({"voce": nome, "ok": ok, "dettaglio": dettaglio})

        w = sistema.wifi_status()
        voce("Wi-Fi", w["connesso"], f"{w['ssid']} · segnale {w['segnale']}%" if w["connesso"] else "non connesso")
        ip = sistema.local_ip()
        voce("Indirizzo IP", bool(ip), ip or "nessuno")
        ntp = sistema.ntp_synced()
        voce("Ora sincronizzata", ntp, {True: "sì (NTP)", False: "no: controlla la rete", None: "non verificabile"}[ntp])

        l = c["luogo"]
        try:
            m = weather.fetch(l["lat"], l["lon"], l["fuso"])
            voce("Meteo", True, f"{l['nome']}: {m['temp']}° {m['descrizione']}")
        except Exception as e:
            voce("Meteo", False, str(e))

        urls = c["calendario"]["ics_urls"]
        if not urls:
            voce("Calendario Google", False, "nessun calendario: aggiungilo da PC (scheda Da PC)")
        tz = ZoneInfo(l["fuso"])
        now = datetime.now(tz)
        start = datetime.combine(now.date(), dtime(0), tz)
        for i, u in enumerate(urls, 1):
            try:
                n = len(icsparse.occurrences(icsparse.parse(icsparse.fetch(u), tz),
                                             start, start + timedelta(days=c["calendario"]["giorni"]), tz))
                voce(f"Calendario {i}", True, f"{n} eventi nei prossimi {c['calendario']['giorni']} giorni")
            except Exception as e:
                voce(f"Calendario {i}", False, icsparse.spiega_errore(e))

        try:
            st = self._alarm_request({"cmd": "stato"})["stato"]
            if st["attiva"]:
                det = f"attiva, prossima: {st['prossima'].replace('T', ' ')}" if st.get("prossima") else "attiva"
            else:
                det = "servizio ok, sveglia spenta"
            voce("Sveglia", True, det)
        except (OSError, ValueError, KeyError):
            voce("Sveglia", False, "servizio non raggiungibile")

        h = c["homeassistant"]
        r = HomeAssistant(h["url"], h["token"]).verifica()
        voce("Home Assistant", r["ok"], r["dettaglio"])

        b = self._sveglia.get("batteria") or {}
        if b.get("presente"):
            metodi = {"kernel": "limite di carica hardware", "presa": "presa smart",
                      "lettura": "solo lettura (nessuna presa configurata)", "disattivata": "gestione disattivata"}
            ok = not b.get("errore") and not b.get("avviso")
            if b.get("metodo") == "lettura":
                ok = None
            voce("Batteria", ok, f"{b.get('percentuale')}% · {b.get('stato_it')} · {metodi.get(b.get('metodo'), '')}"
                 + (f" · {b['errore']}" if b.get("errore") else ""))
        else:
            voce("Batteria", None, "non rilevata")
        bl = self.backlight.stato()
        if not bl["dispositivo"]:
            voce("Luminosità", False, bl["errore"])
        else:
            voce("Luminosità", not bl["errore"],
                 f"{bl['dispositivo']} ({bl['tipo']}) · {bl['valore']}/{bl['max']}"
                 + (f" · via {bl['metodo']}" if bl["metodo"] else "")
                 + (f" · {bl['errore']}" if bl["errore"] else "")
                 + (f" · altri: {', '.join(a for a in bl['alternative'] if a != bl['dispositivo'])}"
                    if len(bl["alternative"]) > 1 else ""))
        voce("Schermo", True, f"rotazione {c['schermo']['rotazione']}° · notte {c['schermo']['notte_inizio']}–{c['schermo']['notte_fine']}")
        return {"ok": True, "voci": voci}


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Comodino")
    if not DEV:
        app.setOverrideCursor(Qt.BlankCursor)
    backend = Backend(config.load())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("modalitaDev", DEV)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
