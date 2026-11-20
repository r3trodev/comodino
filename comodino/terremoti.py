"""Terremoti vicini dall'INGV (servizio FDSN pubblico, formato testo)."""
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://webservices.ingv.it/fdsnws/event/1/query"


def distanza_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fetch(lat, lon, raggio_km, mag_min, ore, adesso=None, timeout=20):
    adesso = adesso or datetime.now(timezone.utc)
    q = urllib.parse.urlencode({
        "starttime": (adesso - timedelta(hours=ore)).strftime("%Y-%m-%dT%H:%M:%S"),
        "lat": f"{lat:.4f}", "lon": f"{lon:.4f}", "maxradiuskm": int(raggio_km),
        "minmag": mag_min, "orderby": "time", "format": "text", "limit": 50,
    })
    req = urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "comodino/0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status == 204:          # nessun evento
                return ""
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (204, 404):         # alcuni server rispondono 404 se non c'è nulla
            return ""
        raise


def _ora(s):
    d = datetime.fromisoformat(s.strip().replace("Z", ""))
    return d.replace(tzinfo=timezone.utc)


def parse(testo, lat, lon, adesso=None):
    """Eventi dal più recente: {id, ora, mag, km, luogo, prof, ore_fa, forte}."""
    adesso = adesso or datetime.now(timezone.utc)
    out = []
    for riga in testo.splitlines():
        if not riga.strip() or riga.startswith("#"):
            continue
        c = riga.split("|")
        if len(c) < 13:
            continue
        try:
            quando = _ora(c[1])
            elat, elon, prof, mag = float(c[2]), float(c[3]), float(c[4]), float(c[10])
        except ValueError:
            continue
        km = distanza_km(lat, lon, elat, elon)
        out.append({
            "id": c[0],
            "ora": quando.astimezone().strftime("%H:%M"),
            "giorno": quando.astimezone().strftime("%d/%m"),
            "mag": round(mag, 1),
            "km": round(km),
            "luogo": c[12].strip(),
            "prof": round(prof),
            "ore_fa": round((adesso - quando).total_seconds() / 3600, 1),
            # sentito bene o potenzialmente dannoso nella zona
            "forte": mag >= 4.5 or (mag >= 3.5 and km <= 50),
        })
    out.sort(key=lambda e: e["ore_fa"])
    return out


def avviso(eventi):
    """Il più importante (forte prima, poi il più recente), o None."""
    if not eventi:
        return None
    e = max(eventi, key=lambda e: (e["forte"], e["mag"] >= 4, -e["ore_fa"]))
    return {"testo": f"🌍 Terremoto M{e['mag']} a {e['km']} km · {e['luogo']} · {e['ora']}",
            "colore": "#f85149" if e["forte"] else "#d29922", "forte": e["forte"]}
