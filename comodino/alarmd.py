"""Demone sveglia.

Gira come servizio systemd utente, indipendente dall'interfaccia: se la UI
si blocca o si riavvia, la sveglia suona comunque.

Protocollo: una riga JSON per richiesta su TCP 127.0.0.1:<porta>.
  {"cmd": "stato"}
  {"cmd": "imposta", "attiva": true, "ora": 7, "minuto": 0, "giorni": [0,1,2,3,4]}
  {"cmd": "snooze"} | {"cmd": "stop"} | {"cmd": "prova"} | {"cmd": "ricarica"}
  {"cmd": "presa", "on": true}   (test manuale della presa del caricatore)
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
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path

from . import config
from .batteria import BatteryManager
from .homeassistant import HomeAssistant

log = logging.getLogger("alarmd")

DEFAULT_STATE = {"attiva": False, "ora": 7, "minuto": 0,
                 "giorni": [0, 1, 2, 3, 4], "snooze_fino": None}


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

class Alarm:
    def __init__(self, cfg, ha_cfg=None, batt=None):
        self.cfg = cfg
        self.batt = batt
        self.ha = HomeAssistant((ha_cfg or {}).get("url"), (ha_cfg or {}).get("token"))
        self.anticipo = int((ha_cfg or {}).get("anticipo_min") or 0)
        self.lock = threading.RLock()
        self.path = config.state_dir() / "sveglia.json"
        self.state = dict(DEFAULT_STATE)
        try:
            self.state.update(json.loads(self.path.read_text()))
        except (FileNotFoundError, ValueError):
            pass
        sound = cfg["suono"]
        if not sound or not Path(sound).is_file():
            sound = config.state_dir() / "chime.wav"
            if not sound.exists():
                make_chime(sound)
        self.ringer = Ringer(sound, cfg)
        self.ring_started = None

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        os.replace(tmp, self.path)

    def snooze_until(self):
        s = self.state.get("snooze_fino")
        return datetime.fromisoformat(s) if s else None

    def next_scheduled_after(self, t):
        """Prossima sveglia programmata (senza snooze) strettamente dopo t."""
        st = self.state
        if st["attiva"] and st["giorni"]:
            for d in range(8):
                day = (t + timedelta(days=d)).date()
                if day.weekday() in st["giorni"]:
                    at = datetime.combine(day, dtime(st["ora"], st["minuto"]))
                    if at > t:
                        return at
        return None

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

    def notify(self, azione):
        if not self.ha.configurato:
            return
        dati = {"azione": azione, "ora": f"{self.state['ora']:02d}:{self.state['minuto']:02d}"}
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
            ha = full["homeassistant"]
            self.ha = HomeAssistant(ha.get("url"), ha.get("token"))
            self.anticipo = int(ha.get("anticipo_min") or 0)
        if self.batt:
            self.batt.configure(full)

    def status(self):
        with self.lock:
            nxt = self.next_after(datetime.now())
            return {**self.state,
                    "batteria": self.batt.stato if self.batt else {"presente": False},
                    "suona": self.ringer.active,
                    "prossima": nxt.isoformat(timespec="minutes") if nxt else None}

    def configure(self, data):
        with self.lock:
            for k in ("attiva", "ora", "minuto", "giorni"):
                if k in data:
                    self.state[k] = data[k]
            self.state["ora"] = int(self.state["ora"]) % 24
            self.state["minuto"] = int(self.state["minuto"]) % 60
            self.state["giorni"] = sorted({int(g) % 7 for g in self.state["giorni"]})
            self.state["snooze_fino"] = None
            self.save()

    def ring(self):
        with self.lock:
            log.info("sveglia!")
            self.ring_started = time.monotonic()
            self.ringer.start()
            self.notify("suona")

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
            self.state["snooze_fino"] = None
            self.save()

    def run(self):
        last = datetime.now()
        while True:
            time.sleep(1)
            now = datetime.now()
            if now < last - timedelta(minutes=5):
                last = now              # orologio spostato indietro (NTP)
            with self.lock:
                if self.pre_due(last, now):
                    self.notify("pre")
                nxt = self.next_after(last)
                if nxt and nxt <= now and not self.ringer.active:
                    if now - nxt < timedelta(minutes=30):   # non suonare per sveglie molto vecchie
                        self.state["snooze_fino"] = None
                        self.save()
                        self.ring()
                if (self.ringer.active and self.ring_started and
                        time.monotonic() - self.ring_started > self.cfg["durata_max_min"] * 60):
                    log.info("spegnimento automatico")
                    self.stop()
            last = now


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
    srv = make_server(alarm, cfg["porta"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("in ascolto su 127.0.0.1:%s", cfg["porta"])
    alarm.run()


if __name__ == "__main__":
    main()
