"""Retroilluminazione dello schermo (/sys/class/backlight).

- Sceglie il dispositivo giusto: prima i driver nativi ("raw", es. intel_backlight),
  poi "platform", per ultimi quelli ACPI ("firmware", es. acpi_video0) che sui
  tablet spesso esistono ma non fanno nulla.
- Scrive direttamente in sysfs (permessi dalla regola udev); se non può, usa
  systemd-logind (SetBrightness), che lo consente all'utente della sessione attiva.
- Non nasconde gli errori: `stato()` dice cosa sta succedendo, per la diagnostica.
"""
import subprocess
from pathlib import Path

BASE = Path("/sys/class/backlight")
PRIORITA = {"raw": 0, "platform": 1, "firmware": 2}


def _r(p, default=""):
    try:
        return Path(p).read_text().strip()
    except OSError:
        return default


def _int(p):
    try:
        return int(_r(p))
    except ValueError:
        return None


def dispositivi(base=BASE):
    out = []
    base = Path(base)
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        mx = _int(d / "max_brightness")
        if not mx:
            continue
        out.append({"nome": d.name, "tipo": _r(d / "type", "?"), "max": mx,
                    "valore": _int(d / "brightness")})
    out.sort(key=lambda x: (PRIORITA.get(x["tipo"], 3), x["nome"]))
    return out


def logind_set(nome, valore):
    """Imposta la luminosità tramite systemd-logind (sessione attiva)."""
    try:
        r = subprocess.run(
            ["busctl", "call", "org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
             "org.freedesktop.login1.Session", "SetBrightness", "ssu", "backlight", nome, str(int(valore))],
            capture_output=True, text=True, timeout=3)
        return r.returncode == 0, r.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


class Backlight:
    def __init__(self, preferito="", base=BASE, logind=logind_set):
        self.base = Path(base)
        self.logind = logind
        self.current = None
        self.metodo = ""
        self.errore = ""
        self.scegli(preferito)

    def scegli(self, preferito=""):
        devs = dispositivi(self.base)
        self.elenco = devs
        scelto = next((d for d in devs if d["nome"] == preferito), None) if preferito else None
        scelto = scelto or (devs[0] if devs else None)
        self.dev = self.base / scelto["nome"] if scelto else None
        self.current = None
        self.errore = "" if self.dev else "nessun dispositivo di retroilluminazione nel kernel"

    def set(self, percent, force=False):
        if not self.dev or (percent == self.current and not force):
            return
        mx = _int(self.dev / "max_brightness") or 1
        val = max(1, round(mx * max(1, min(100, percent)) / 100))
        try:
            (self.dev / "brightness").write_text(str(val))
            self.metodo = "sysfs"
        except OSError as e:
            ok, err = self.logind(self.dev.name, val)
            if not ok:
                self.errore = f"scrittura negata ({e.strerror or e}); logind: {err or 'non disponibile'}"
                return
            self.metodo = "logind"
        self.current = percent
        self.errore = ""

    def stato(self):
        return {
            "dispositivo": self.dev.name if self.dev else "",
            "tipo": _r(self.dev / "type") if self.dev else "",
            "valore": _int(self.dev / "brightness") if self.dev else None,
            "max": _int(self.dev / "max_brightness") if self.dev else None,
            "percentuale": self.current,
            "metodo": self.metodo,
            "errore": self.errore,
            "alternative": [d["nome"] for d in self.elenco],
        }
