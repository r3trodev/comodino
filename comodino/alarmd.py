"""Demone sveglia.

Gira come servizio systemd utente, indipendente dall'interfaccia: se la UI
si blocca o si riavvia, la sveglia suona comunque.

Protocollo: una riga JSON per richiesta su TCP 127.0.0.1:<porta>.
  {"cmd": "stato"}
  {"cmd": "imposta", "attiva": true, "ora": 7, "minuto": 0, "giorni": [0,1,2,3,4]}
  {"cmd": "snooze"} | {"cmd": "stop"} | {"cmd": "prova"} | {"cmd": "ricarica"}
  {"cmd": "presa", "on": true}   (test manuale della presa del caricatore)
  {"cmd": "salva_sveglia", "sveglia": {id?, nome, attiva, ora, minuto, giorni, data?}}
  {"cmd": "elimina_sveglia", "id": "2"} | {"cmd": "attiva_sveglia", "id": "2", "attiva": false}
  {"cmd": "pisolino", "minuti": 20}
Lo stato include anche "batteria" (vedi batteria.py), gestita in un thread a parte.
giorni: 0 = lunedì ... 6 = domenica.

Se Home Assistant è configurato, invia l'evento `comodino_sveglia` con
azione = "pre" (N minuti prima), "suona", "rimanda", "spenta".
"""
import json
import logging
import math
import os
import shutil
import socketserver
import struct
import subprocess
import threading
import time
import wave
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path

from . import config
from .batteria import BatteryManager
from .homeassistant import HomeAssistant

log = logging.getLogger("alarmd")

DEFAULT_STATE = {"sveglie": [], "snooze_fino": None}


# ---------------------------------------------------------------- suono

def make_chime(path):
    """Genera un suono di sveglia gentile (tre note, poi pausa)."""
    rate = 44100
    notes = [(880.0, 0.35), (1108.7, 0.35), (1318.5, 0.7)]
    frames = bytearray()
    for freq, dur in notes:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = min(1.0, t / 0.01) * math.exp(-3.0 * t / dur)
            v = env * (0.6 * math.sin(2 * math.pi * freq * t)
                       + 0.25 * math.sin(2 * math.pi * freq * 2 * t))
            frames += struct.pack("<h", int(v * 30000))
    frames += b"\x00\x00" * int(rate * 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


class Volume:
    """Volume di sistema via wpctl (PipeWire). Se manca, non fa nulla."""

    def __init__(self):
        self.wpctl = shutil.which("wpctl")
        self.saved = None

    def _run(self, *args):
        try:
            return subprocess.run([self.wpctl, *args], capture_output=True,
                                  text=True, timeout=3).stdout
        except Exception:
            return ""

    def save(self):
        if self.wpctl:
            out = self._run("get-volume", "@DEFAULT_AUDIO_SINK@")
            try:
                self.saved = float(out.split()[1])
            except (IndexError, ValueError):
                self.saved = None
            self._run("set-mute", "@DEFAULT_AUDIO_SINK@", "0")

    def set(self, v):
        if self.wpctl:
            self._run("set-volume", "@DEFAULT_AUDIO_SINK@", f"{v:.2f}")

    def restore(self):
        if self.wpctl and self.saved is not None:
            self.set(self.saved)


class Ringer:
    """Riproduce il suono in loop con volume crescente."""

    def __init__(self, sound, cfg):
        self.sound = sound
        self.cfg = cfg
        self._stop = threading.Event()
        self._thread = None
        self._proc = None
        self.volume = Volume()

    @property
    def active(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.active:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        p = self._proc
        if p and p.poll() is None:
            p.terminate()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None

    def _player(self):
        for cmd in (["pw-play"], ["paplay"], ["aplay", "-q"]):
            if shutil.which(cmd[0]):
                return cmd
        return None

    def _loop(self):
        c = self.cfg
        v0, v1, ramp = c["volume_iniziale"], c["volume_finale"], max(1, c["rampa_sec"])
        self.volume.save()
        t0 = time.monotonic()
        player = self._player()
        try:
            while not self._stop.is_set():
                frac = min(1.0, (time.monotonic() - t0) / ramp)
                self.volume.set(v0 + (v1 - v0) * frac)
                if player:
                    self._proc = subprocess.Popen(player + [str(self.sound)],
                                                  stdout=subprocess.DEVNULL,
                                                  stderr=subprocess.DEVNULL)
                    self._proc.wait()
                elif os.name == "nt":   # sviluppo su Windows
                    import winsound
                    winsound.PlaySound(str(self.sound), winsound.SND_FILENAME)
                else:
                    log.error("nessun player audio trovato (pw-play/paplay/aplay)")
                    self._stop.wait(2)
        finally:
            self.volume.restore()


# ---------------------------------------------------------------- logica sveglia

def _valida_sveglia(sv):
    """Normalizza una sveglia ricevuta dall'interfaccia."""
    out = {
        "id": str(sv.get("id") or ""),
        "nome": (str(sv.get("nome") or "Sveglia").strip() or "Sveglia")[:30],
        "attiva": bool(sv.get("attiva", True)),
        "ora": int(sv.get("ora", 7)) % 24,
        "minuto": int(sv.get("minuto", 0)) % 60,
        "giorni": sorted({int(g) % 7 for g in sv.get("giorni") or []}),
    }
    if sv.get("data") and not out["giorni"]:
        out["data"] = date.fromisoformat(str(sv["data"])[:10]).isoformat()
    return out


def occorrenza(sv, t):
    """Prossimo istante (> t) in cui suona la sveglia sv, oppure None."""
    if not sv.get("attiva"):
        return None
    hm = dtime(sv["ora"], sv["minuto"])
    if sv.get("data"):
        at = datetime.combine(date.fromisoformat(sv["data"]), hm)
        return at if at > t else None
    for d in range(8):
        day = (t + timedelta(days=d)).date()
        if day.weekday() in sv["giorni"]:
            at = datetime.combine(day, hm)
            if at > t:
                return at
    return None


def prossima_data(ora, minuto, dopo=None):
    """Data della prossima volta che sarà ora:minuto (oggi se non è ancora passato)."""
    dopo = dopo or datetime.now()
    at = datetime.combine(dopo.date(), dtime(ora, minuto))
    return (at if at > dopo else at + timedelta(days=1)).date().isoformat()


class Alarm:
    def __init__(self, cfg, ha_cfg=None, batt=None):
        self.cfg = cfg
        self.batt = batt
        self.ha_cfg = ha_cfg or {}
        self.ha = HomeAssistant(self.ha_cfg.get("url"), self.ha_cfg.get("token"))
        self.anticipo = int(self.ha_cfg.get("anticipo_min") or 0)
        self.lock = threading.RLock()
        self.path = config.state_dir() / "sveglia.json"
        self.state = {"sveglie": [], "snooze_fino": None}
        try:
            self.state.update(json.loads(self.path.read_text()))
        except (FileNotFoundError, ValueError):
            pass
        self._migra()
        self.telefono = None            # sveglia impostata da Home Assistant (dal telefono)
        self.suonando = None            # sveglia che sta suonando (dict) o None
        sound = cfg["suono"]
        if not sound or not Path(sound).is_file():
            sound = config.state_dir() / "chime.wav"
            if not sound.exists():
                make_chime(sound)
        self.ringer = Ringer(sound, cfg)
        self.ring_started = None

    def _migra(self):
        """Formato vecchio (una sola sveglia) -> elenco."""
        st = self.state
        if "ora" in st:
            st["sveglie"] = [_valida_sveglia({"id": "1", "nome": "Sveglia", "attiva": st.get("attiva", False),
                                              "ora": st.get("ora", 7), "minuto": st.get("minuto", 0),
                                              "giorni": st.get("giorni", [])})]
            for k in ("ora", "minuto", "giorni", "attiva"):
                st.pop(k, None)

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        os.replace(tmp, self.path)

    # ---------------------------------------------- calcolo prossime sveglie
    def tutte(self):
        return self.state["sveglie"] + ([self.telefono] if self.telefono else [])

    def snooze_until(self):
        s = self.state.get("snooze_fino")
        return datetime.fromisoformat(s) if s else None

    def prossima(self, t):
        """(istante, sveglia) della prossima sveglia programmata dopo t, senza snooze."""
        best = (None, None)
        for sv in self.tutte():
            at = occorrenza(sv, t)
            if at and (best[0] is None or at < best[0]):
                best = (at, sv)
        return best

    def next_scheduled_after(self, t):
        return self.prossima(t)[0]

    def next_after(self, t):
        """Prossimo istante di suono (sveglia o snooze) strettamente dopo t."""
        candidates = []
        sn = self.snooze_until()
        if sn and sn > t:
            candidates.append(sn)
        sch = self.next_scheduled_after(t)
        if sch:
            candidates.append(sch)
        return min(candidates) if candidates else None

    def pre_due(self, last, now):
        """True se tra last e now è scattato l'istante 'anticipo' prima di una sveglia."""
        if self.anticipo <= 0:
            return False
        a = timedelta(minutes=self.anticipo)
        nxt = self.next_scheduled_after(last + a)
        return nxt is not None and nxt <= now + a

    def notify(self, azione, sv=None):
        if not self.ha.configurato:
            return
        sv = sv or self.suonando or self.prossima(datetime.now())[1] or {}
        dati = {"azione": azione, "nome": sv.get("nome", ""),
                "ora": f"{sv.get('ora', 0):02d}:{sv.get('minuto', 0):02d}" if sv else ""}
        if azione == "pre":
            dati["tra_minuti"] = self.anticipo

        def send():
            try:
                self.ha.evento("comodino_sveglia", dati)
            except Exception as e:
                log.warning("Home Assistant: %s", e)
        threading.Thread(target=send, daemon=True).start()

    def reload(self):
        full = config.load()
        with self.lock:
            self.cfg = full["sveglia"]
            self.ringer.cfg = self.cfg
            self.ha_cfg = full["homeassistant"]
            self.ha = HomeAssistant(self.ha_cfg.get("url"), self.ha_cfg.get("token"))
            self.anticipo = int(self.ha_cfg.get("anticipo_min") or 0)
            if not (self.ha_cfg.get("sveglia_ora") and self.ha.configurato):
                self.telefono = None
        if self.batt:
            self.batt.configure(full)

    def status(self):
        with self.lock:
            now = datetime.now()
            nxt = self.next_after(now)
            at, sv = self.prossima(now)
            sn = self.snooze_until()
            nome = "Pisolino" if (sn and sn > now and (at is None or sn <= at)) else (sv or {}).get("nome", "")
            elenco = []
            for x in self.state["sveglie"]:
                o = occorrenza(x, now)
                elenco.append(dict(x, prossima=o.isoformat(timespec="minutes") if o else None))
            tel = None
            if self.telefono:
                o = occorrenza(self.telefono, now)
                tel = dict(self.telefono, prossima=o.isoformat(timespec="minutes") if o else None)
            return {
                "sveglie": elenco,
                "telefono": tel,
                "attiva": any(s.get("attiva") for s in self.tutte()),
                "snooze_fino": self.state.get("snooze_fino"),
                "batteria": self.batt.stato if self.batt else {"presente": False},
                "suona": self.ringer.active,
                "suona_nome": (self.suonando or {}).get("nome", "") if self.ringer.active else "",
                "prossima": nxt.isoformat(timespec="minutes") if nxt else None,
                "prossima_nome": nome,
            }

    # ---------------------------------------------- modifiche
    def salva_sveglia(self, dati):
        with self.lock:
            sv = _valida_sveglia(dati)
            if not sv["giorni"] and not sv.get("data"):
                sv["data"] = prossima_data(sv["ora"], sv["minuto"])     # "una volta sola"
            ids = [x["id"] for x in self.state["sveglie"]]
            if not sv["id"] or sv["id"] not in ids:
                if len(ids) >= 10:
                    raise ValueError("massimo 10 sveglie")
                sv["id"] = str(max([int(i) for i in ids if i.isdigit()] + [0]) + 1)
                self.state["sveglie"].append(sv)
            else:
                self.state["sveglie"][ids.index(sv["id"])] = sv
            self.state["snooze_fino"] = None
            self.save()
            return sv["id"]

    def configure(self, data):
        """Compatibilità con la vecchia interfaccia: modifica la prima sveglia."""
        primo = self.state["sveglie"][0] if self.state["sveglie"] else {"id": "", "nome": "Sveglia"}
        self.salva_sveglia({**primo, **{k: data[k] for k in ("attiva", "ora", "minuto", "giorni") if k in data}})

    def elimina_sveglia(self, sid):
        with self.lock:
            prima = len(self.state["sveglie"])
            self.state["sveglie"] = [x for x in self.state["sveglie"] if x["id"] != str(sid)]
            if len(self.state["sveglie"]) == prima:
                raise ValueError("sveglia non trovata")
            self.save()

    def attiva_sveglia(self, sid, attiva):
        with self.lock:
            for x in self.state["sveglie"]:
                if x["id"] == str(sid):
                    x["attiva"] = bool(attiva)
                    if attiva and x.get("data") and occorrenza(x, datetime.now()) is None:
                        x["data"] = prossima_data(x["ora"], x["minuto"])   # una tantum già passata
                    self.save()
                    return
            raise ValueError("sveglia non trovata")

    def pisolino(self, minuti):
        minuti = int(minuti)
        if not 1 <= minuti <= 240:
            raise ValueError("pisolino tra 1 e 240 minuti")
        with self.lock:
            until = datetime.now() + timedelta(minutes=minuti)
            self.state["snooze_fino"] = until.isoformat(timespec="seconds")
            self.save()

    def imposta_telefono(self, sv):
        with self.lock:
            self.telefono = sv

    # ---------------------------------------------- suono
    def ring(self, sv=None):
        with self.lock:
            log.info("sveglia! %s", (sv or {}).get("nome", ""))
            self.suonando = sv or {"nome": "Prova", "ora": datetime.now().hour, "minuto": datetime.now().minute}
            self.ring_started = time.monotonic()
            self.ringer.start()
            self.notify("suona", self.suonando)

    def snooze(self):
        with self.lock:
            was = self.ringer.active
            self.ringer.stop()
            if was:
                self.notify("rimanda")
            until = datetime.now() + timedelta(minutes=self.cfg["snooze_min"])
            self.state["snooze_fino"] = until.isoformat(timespec="seconds")
            self.save()

    def stop(self):
        with self.lock:
            was = self.ringer.active
            self.ringer.stop()
            if was:
                self.notify("spenta")
            self.suonando = None
            self.state["snooze_fino"] = None
            self.save()

    def tick(self, last, now):
        """Un passo del ciclo principale (separato da run() per i test)."""
        with self.lock:
            if self.pre_due(last, now):
                self.notify("pre")
            sn = self.snooze_until()
            at, sv = self.prossima(last)
            if sn and last < sn <= now and not self.ringer.active:
                self.state["snooze_fino"] = None
                self.save()
                self.ring(dict(self.suonando or {}, nome=(self.suonando or {}).get("nome") or "Pisolino")
                          if self.suonando else {"nome": "Pisolino", "ora": sn.hour, "minuto": sn.minute})
            elif at and at <= now and not self.ringer.active:
                if now - at < timedelta(minutes=30):   # non suonare per sveglie molto vecchie
                    self.state["snooze_fino"] = None
                    if sv.get("data") and sv is not self.telefono:
                        sv["attiva"] = False             # "una volta sola": si spegne dopo aver suonato
                    self.save()
                    self.ring(sv)
            if (self.ringer.active and self.ring_started and
                    time.monotonic() - self.ring_started > self.cfg["durata_max_min"] * 60):
                log.info("spegnimento automatico")
                self.stop()

    def run(self):
        last = datetime.now()
        while True:
            time.sleep(1)
            now = datetime.now()
            if now < last - timedelta(minutes=5):
                last = now              # orologio spostato indietro (NTP)
            self.tick(last, now)
            last = now


# ---------------------------------------------------------------- sveglia dal telefono (Home Assistant)

def parse_ha_sveglia(stato_ora, stato_attiva):
    """Dagli helper di HA alla sveglia "Dal telefono".

    input_datetime solo ora ("07:30:00")      -> ogni giorno a quell'ora
    input_datetime con data ("2026-11-18 07:30:00") -> una volta sola
    input_boolean "off" (o assente)          -> sveglia disattivata
    """
    if not stato_ora or stato_ora in ("unknown", "unavailable"):
        return None
    testo = stato_ora.replace("T", " ").strip()
    data = None
    if " " in testo:
        data, testo = testo.split(" ", 1)
    hh, mm = testo.split(":")[:2]
    sv = {"id": "telefono", "nome": "Dal telefono", "attiva": stato_attiva in (None, "on"),
          "ora": int(hh), "minuto": int(mm), "giorni": [] if data else list(range(7))}
    if data:
        sv["data"] = date.fromisoformat(data).isoformat()
    return sv


class Telefono:
    """Ogni minuto legge gli helper di HA e pubblica la prossima sveglia come sensore."""

    def __init__(self, alarm):
        self.alarm = alarm
        self._pubblicata = None

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:
                log.warning("sveglia dal telefono: %s", e)
            time.sleep(60)

    def tick(self):
        a = self.alarm
        h, ha = a.ha_cfg, a.ha
        if not ha.configurato:
            return
        if h.get("sveglia_ora"):
            ids = [h["sveglia_ora"]] + ([h["sveglia_attiva"]] if h.get("sveglia_attiva") else [])
            stati = {s["id"]: s["stato"] for s in ha.stati(ids)}
            a.imposta_telefono(parse_ha_sveglia(stati.get(h["sveglia_ora"]),
                                                stati.get(h.get("sveglia_attiva")) if h.get("sveglia_attiva") else None))
        if h.get("pubblica_prossima", True):
            st = a.status()
            valore = st["prossima"]
            if valore != self._pubblicata:
                stato = datetime.fromisoformat(valore).astimezone().isoformat() if valore else "unknown"
                ha.imposta_stato("sensor.comodino_prossima_sveglia", stato, {
                    "device_class": "timestamp",
                    "friendly_name": "Comodino prossima sveglia",
                    "nome": st["prossima_nome"],
                })
                self._pubblicata = valore


# ---------------------------------------------------------------- server

def make_server(alarm, port):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for raw in self.rfile:
                try:
                    req = json.loads(raw)
                    cmd = req.get("cmd")
                    if cmd == "imposta":
                        alarm.configure(req)
                    elif cmd == "salva_sveglia":
                        alarm.salva_sveglia(req.get("sveglia") or {})
                    elif cmd == "elimina_sveglia":
                        alarm.elimina_sveglia(req.get("id"))
                    elif cmd == "attiva_sveglia":
                        alarm.attiva_sveglia(req.get("id"), req.get("attiva"))
                    elif cmd == "pisolino":
                        alarm.pisolino(req.get("minuti", 20))
                    elif cmd == "snooze":
                        alarm.snooze()
                    elif cmd == "stop":
                        alarm.stop()
                    elif cmd == "prova":
                        alarm.ring()
                    elif cmd == "ricarica":
                        alarm.reload()
                    elif cmd == "presa":
                        if not alarm.batt:
                            raise ValueError("gestione batteria non attiva")
                        res = alarm.batt.presa_manuale(bool(req.get("on")))
                        if not res["ok"]:
                            raise ValueError(res["errore"])
                    elif cmd != "stato":
                        raise ValueError(f"comando sconosciuto: {cmd}")
                    resp = {"ok": True, "stato": alarm.status()}
                except Exception as e:
                    resp = {"ok": False, "errore": str(e)}
                self.wfile.write((json.dumps(resp) + "\n").encode())

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    return srv


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    full = config.load()
    cfg = full["sveglia"]
    batt = BatteryManager(full)
    threading.Thread(target=batt.run, daemon=True, name="batteria").start()
    alarm = Alarm(cfg, full["homeassistant"], batt)
    threading.Thread(target=Telefono(alarm).run, daemon=True, name="telefono").start()
    srv = make_server(alarm, cfg["porta"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("in ascolto su 127.0.0.1:%s", cfg["porta"])
    alarm.run()


if __name__ == "__main__":
    main()
