"""Configurazione.

Due livelli:
  1. /etc/comodino/config.toml   -> valori di base, messi nella ISO in fase di build
  2. ~/.local/state/comodino/impostazioni.json -> modifiche fatte dal pannello
     (o dalla configurazione da PC); hanno la precedenza e sopravvivono ai riavvii.
"""
import copy
import json
import os
import sys
import tomllib
from pathlib import Path

DEFAULT = {
    "luogo": {"nome": "Roma", "lat": 41.89, "lon": 12.49, "fuso": "Europe/Rome"},
    "calendario": {"ics_urls": [], "giorni": 7, "aggiorna_min": 10},
    "meteo": {"aggiorna_min": 15},
    "schermo": {
        "rotazione": 0,                 # 0 | 90 | 180 | 270
        "tema": "notte",                # vedi qml/Temi.js
        "notte_stile": "rosso",         # rosso | ambra | grigio | giorno
        "retroilluminazione": "",       # vuoto = scelta automatica (es. intel_backlight)
        "layout": "classico",           # classico | stazione
        "notte_inizio": "22:30",
        "notte_fine": "06:30",
        "luminosita_giorno": 70,        # percento
        "luminosita_notte": 3,
        "risveglio_tocco_sec": 20,
        "alba_min": 20,                 # alba simulata: minuti prima della sveglia (0 = off)
    },
    "sveglia": {
        "porta": 47654,                 # solo 127.0.0.1
        "durata_max_min": 15,
        "snooze_min": 9,
        "suono": "",
        "volume_iniziale": 0.15,
        "volume_finale": 0.8,
        "rampa_sec": 60,
    },
    "homeassistant": {
        "url": "",                      # es. http://192.168.1.10:8123
        "token": "",                    # token di accesso a lunga durata
        "entita": [],                   # es. ["sensor.temperatura_camera", "light.comodino"]
        "anticipo_min": 15,             # evento "pre" N minuti prima della sveglia (0 = off)
        "sveglia_ora": "",              # sveglia dal telefono: es. "input_datetime.sveglia_comodino"
        "sveglia_attiva": "",           # es. "input_boolean.sveglia_comodino" (opzionale)
        "pubblica_prossima": True,      # sensor.comodino_prossima_sveglia
    },
    "clima": {                          # sensori di Home Assistant (entity_id), opzionali
        "interno_temp": "",             # es. "sensor.camera_temperatura"
        "interno_umidita": "",
        "esterno_temp": "",             # se vuoto: si usa la temperatura di Open-Meteo
        "esterno_umidita": "",
        "esterno_batteria": "",         # pila del termometro; vuoto = ricavata da esterno_temp (RFLink: *_bat)
        "fattore_muro": 0.7,            # rischio muffa: quanto è isolato l'angolo più freddo (0.5 pessimo, 0.8 buono)
    },
    "batteria": {
        "gestione": True,               # False = solo lettura
        "min": 40,                      # sotto: ricarica
        "max": 80,                      # sopra: smetti di caricare
        "allarme_min": 20,              # avviso a schermo se non si sta caricando
        "presa": "",                    # es. "switch.presa_comodino" (Home Assistant)
        "invia_ha": True,               # pubblica sensor.comodino_batteria su HA
    },
    "aggiornamenti": {
        "repo": "",                     # es. "utente/comodino" (GitHub)
        "token": "",                    # solo per repository privati
        "automatico": True,             # installa di notte (03:00-05:00), mai vicino a una sveglia
    },
    "allerte": {
        "zona": "",                     # area Meteoalarm (scelta dal pannello: Luogo → Zona allerte)
    },
    "terremoti": {                      # INGV, dati pubblici
        "attivi": True,
        "raggio_km": 100,
        "magnitudo_min": 3.0,
        "ore": 12,                      # per quante ore resta l'avviso
    },
    "proxmox": {
        "url": "",                      # es. "https://192.168.1.5:8006"
        "token_id": "",                 # es. "comodino@pve!comodino"
        "secret": "",                   # segreto del token (ruolo PVEAuditor: sola lettura)
        "fingerprint": "",              # SHA-256 del certificato (fissato al primo collegamento)
        "ignora": [],                   # ID di VM/container spenti apposta (non danno allarme)
    },
    "web": {"porta": 8080, "durata_min": 15},
}

_ROT = {"normal": 0, "0": 0, "90": 90, "180": 180, "270": 270}


def rotation_degrees(value):
    return _ROT.get(str(value).strip().lower(), 0)


def _candidates():
    env = os.environ.get("COMODINO_CONFIG")
    if env:
        yield Path(env)
    yield Path("/etc/comodino/config.toml")
    yield Path(__file__).resolve().parent.parent / "config.toml"


def config_path():
    for p in _candidates():
        if p.is_file():
            return p
    return None


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    d = Path(base) / "comodino"
    d.mkdir(parents=True, exist_ok=True)
    return d


def overrides_path():
    return state_dir() / "impostazioni.json"


def load_overrides():
    try:
        return json.loads(overrides_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def save_overrides(partial):
    """Unisce `partial` alle impostazioni salvate (scrittura atomica, solo per l'utente)."""
    data = _merge(load_overrides(), partial)
    p = overrides_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)        # contiene token e link privati
    except OSError:
        pass
    os.replace(tmp, p)
    return data


def load():
    cfg = copy.deepcopy(DEFAULT)
    p = config_path()
    if p:
        with open(p, "rb") as f:
            _merge(cfg, tomllib.load(f))
    _merge(cfg, load_overrides())
    cfg["schermo"]["rotazione"] = rotation_degrees(cfg["schermo"]["rotazione"])
    return cfg


if __name__ == "__main__":
    # Uso da shell: python3 -m comodino.config schermo.rotazione
    cfg = load()
    if len(sys.argv) > 1:
        val = cfg
        for part in sys.argv[1].split("."):
            val = val[part]
        print(val)
    else:
        print(config_path())
