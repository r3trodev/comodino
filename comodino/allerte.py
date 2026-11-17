"""Allerte meteo ufficiali da Meteoalarm (feed per l'Italia, formato CAP in JSON).

La zona si sceglie dall'elenco delle aree presenti nel feed (nomi ufficiali),
così non bisogna indovinare come si chiama: vedi `zone()`.
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-italy"
LIVELLI = {2: ("gialla", "#d29922"), 3: ("arancione", "#db6d28"), 4: ("rossa", "#f85149")}
TIPI = {1: "Vento", 2: "Neve e ghiaccio", 3: "Temporali", 4: "Nebbia", 5: "Caldo", 6: "Freddo",
        7: "Mareggiate", 8: "Incendi", 9: "Valanghe", 10: "Pioggia", 12: "Alluvioni", 13: "Pioggia e alluvioni"}


def fetch(timeout=20):
    req = urllib.request.Request(URL, headers={"User-Agent": "comodino/0.9", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _numero(valore):
    """'3; orange; Severe' -> 3"""
    try:
        return int(str(valore).split(";")[0].strip())
    except ValueError:
        return 0


def _data(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def _quando(d):
    d = d.astimezone()
    return f"{GIORNI[d.weekday()]} {d:%H:%M}"


def _info(alert):
    infos = alert.get("info") or []
    for i in infos:
        if str(i.get("language", "")).lower().startswith("it"):
            return i
    return infos[0] if infos else {}


def zone(data):
    out = set()
    for w in data.get("warnings", []):
        for i in (w.get("alert") or {}).get("info") or []:
            for a in i.get("area") or []:
                if a.get("areaDesc"):
                    out.add(a["areaDesc"].strip())
    return sorted(out, key=str.casefold)


def parse(data, zona, now=None):
    """Allerte attive (o che iniziano entro 24 ore) per la zona scelta."""
    if not zona:
        return []
    now = now or datetime.now(timezone.utc)
    z = zona.casefold()
    trovate = {}
    for w in data.get("warnings", []):
        alert = w.get("alert") or {}
        if alert.get("msgType") == "Cancel":
            continue
        info = _info(alert)
        aree = [a.get("areaDesc", "") for a in info.get("area") or []]
        if not any(z in a.casefold() for a in aree):
            continue
        par = {p.get("valueName"): p.get("value") for p in info.get("parameter") or []}
        livello = _numero(par.get("awareness_level"))
        if livello < 2:
            continue
        inizio, fine = _data(info.get("onset") or info.get("effective")), _data(info.get("expires"))
        if fine and fine < now:
            continue
        if inizio and inizio > now + timedelta(hours=24):
            continue
        tipo = TIPI.get(_numero(par.get("awareness_type")), info.get("event", "Allerta"))
        chiave = (tipo, livello)
        if chiave in trovate:
            continue
        nome, colore = LIVELLI.get(livello, ("rossa", "#f85149"))
        trovate[chiave] = {
            "livello": livello,
            "colore": colore,
            "testo": f"Allerta {nome}: {tipo}",
            "dettaglio": (info.get("headline") or info.get("event") or "").strip()[:160],
            "dalle": _quando(inizio) if inizio else "",
            "alle": _quando(fine) if fine else "",
            "in_corso": not inizio or inizio <= now,
        }
    return sorted(trovate.values(), key=lambda a: (-a["livello"], not a["in_corso"]))
