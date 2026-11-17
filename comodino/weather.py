"""Meteo da Open-Meteo (gratuito, nessuna chiave API)."""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

API = "https://api.open-meteo.com/v1/forecast"

# Codici WMO -> (descrizione, icona giorno, icona notte)
WMO = {
    0: ("Sereno", "☀️", "🌙"),
    1: ("Poco nuvoloso", "🌤️", "🌙"),
    2: ("Parzialmente nuvoloso", "⛅", "☁️"),
    3: ("Coperto", "☁️", "☁️"),
    45: ("Nebbia", "🌫️", "🌫️"),
    48: ("Nebbia gelata", "🌫️", "🌫️"),
    51: ("Pioviggine leggera", "🌦️", "🌧️"),
    53: ("Pioviggine", "🌦️", "🌧️"),
    55: ("Pioviggine intensa", "🌧️", "🌧️"),
    56: ("Pioviggine gelata", "🌧️", "🌧️"),
    57: ("Pioviggine gelata", "🌧️", "🌧️"),
    61: ("Pioggia leggera", "🌦️", "🌧️"),
    63: ("Pioggia", "🌧️", "🌧️"),
    65: ("Pioggia forte", "🌧️", "🌧️"),
    66: ("Pioggia gelata", "🌧️", "🌧️"),
    67: ("Pioggia gelata forte", "🌧️", "🌧️"),
    71: ("Neve leggera", "🌨️", "🌨️"),
    73: ("Neve", "🌨️", "🌨️"),
    75: ("Neve forte", "❄️", "❄️"),
    77: ("Nevischio", "🌨️", "🌨️"),
    80: ("Rovesci leggeri", "🌦️", "🌧️"),
    81: ("Rovesci", "🌧️", "🌧️"),
    82: ("Rovesci violenti", "⛈️", "⛈️"),
    85: ("Rovesci di neve", "🌨️", "🌨️"),
    86: ("Rovesci di neve forti", "🌨️", "🌨️"),
    95: ("Temporale", "⛈️", "⛈️"),
    96: ("Temporale con grandine", "⛈️", "⛈️"),
    99: ("Temporale con grandine", "⛈️", "⛈️"),
}

GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]


def describe(code, is_day=True):
    desc, day, night = WMO.get(int(code), ("—", "❔", "❔"))
    return desc, (day if is_day else night)


AQ_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
DIREZIONI = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
POLLINI = ["alder_pollen", "birch_pollen", "grass_pollen", "mugwort_pollen",
           "olive_pollen", "ragweed_pollen"]


def _get(url, params, timeout):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "comodino/0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch(lat, lon, tz="Europe/Rome", timeout=15):
    data = _get(API, {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "forecast_days": 7,
        "past_days": 1,                 # serve "Ieri" nel layout Stazione
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,wind_speed_10m,wind_direction_10m,is_day,"
                   "pressure_msl,precipitation,uv_index,visibility",
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,sunrise,sunset",
        "minutely_15": "precipitation",   # per "pioggia tra 20 minuti"
        "forecast_minutely_15": 8,
    }, timeout)
    return parse(data)


def pioggia_imminente(m15, now, soglia=0.1):
    """Testo breve sulla pioggia dei prossimi 90 minuti (a passi di 15'), '' se niente."""
    tempi, valori = m15.get("time") or [], m15.get("precipitation") or []
    slot = [(datetime.fromisoformat(t), v or 0.0) for t, v in zip(tempi, valori)]
    # ogni valore è la pioggia dei 15 minuti che finiscono a quell'ora
    # il primo intervallo che finisce dopo "adesso" è quello in corso
    futuri = [(t, v) for t, v in slot if now <= t <= now + timedelta(minutes=105)]
    if not futuri:
        return ""

    def minuti(t):
        return max(5, int(round((t - now).total_seconds() / 60 / 5) * 5))

    if futuri[0][1] >= soglia:
        for t, v in futuri[1:]:
            if v < soglia:
                return f"Smette di piovere tra ~{minuti(t - timedelta(minutes=15))} min"
        return "Piove ora"
    for t, v in futuri[1:]:
        if v >= soglia:
            m = minuti(t - timedelta(minutes=15))
            if m <= 60:
                return f"Pioggia tra ~{m} min"
    return ""


def direzione(gradi):
    if gradi is None:
        return ""
    return DIREZIONI[int((gradi % 360) / 45 + 0.5) % 8]


def livello_aqi(v):
    """Indice europeo della qualità dell'aria."""
    if v is None:
        return "—"
    for soglia, nome in ((20, "Buona"), (40, "Discreta"), (60, "Moderata"),
                         (80, "Scadente"), (100, "Molto scadente")):
        if v <= soglia:
            return nome
    return "Pessima"


def livello_polline(v):
    if v is None:
        return "—"
    if v < 10:
        return "Basso"
    if v < 50:
        return "Medio"
    return "Alto"


def parse_aria(data):
    cur = data.get("current", {})
    aqi = cur.get("european_aqi")
    pm25 = cur.get("pm2_5")
    pollini = [cur.get(k) for k in POLLINI if cur.get(k) is not None]
    pol = max(pollini) if pollini else None
    return {
        "aqi": round(aqi) if aqi is not None else None,
        "aqi_testo": livello_aqi(aqi),
        "pm25": round(pm25) if pm25 is not None else None,
        "polline": livello_polline(pol),
    }


def aria(lat, lon, tz="Europe/Rome", timeout=15):
    """Qualità dell'aria e pollini (i pollini solo in Europa e in stagione)."""
    return parse_aria(_get(AQ_API, {
        "latitude": lat, "longitude": lon, "timezone": tz,
        "current": "european_aqi,pm2_5," + ",".join(POLLINI),
    }, timeout))


def _r(v, nd=0):
    if v is None:
        return None
    return round(v, nd) if nd else round(v)


def parse(data, now=None):
    """Riduce la risposta Open-Meteo a ciò che serve all'interfaccia."""
    now = now or datetime.now()
    cur = data["current"]
    desc, icon = describe(cur["weather_code"], cur.get("is_day", 1))
    vis = cur.get("visibility")
    out = {
        "temp": round(cur["temperature_2m"]),
        "temp_decimale": _r(cur["temperature_2m"], 1),
        "percepita": round(cur["apparent_temperature"]),
        "umidita": round(cur["relative_humidity_2m"]),
        "vento": round(cur["wind_speed_10m"]),
        "direzione": direzione(cur.get("wind_direction_10m")),
        "direzione_gradi": _r(cur.get("wind_direction_10m")),
        "pressione": _r(cur.get("pressure_msl")),
        "pioggia_mm": _r(cur.get("precipitation"), 1),
        "uv": _r(cur.get("uv_index"), 1),
        "visibilita_km": (None if vis is None else (">10" if vis >= 10000 else str(round(vis / 1000, 1)))),
        "descrizione": desc,
        "icona": icon,
        "ore": [],
        "giorni": [],          # layout classico: da oggi, 4 giorni
        "settimana": [],       # layout Stazione: da ieri, 7 giorni
        "alba": "",
        "tramonto": "",
        "aggiornato": now.strftime("%H:%M"),
    }

    h = data["hourly"]
    start_hour = now.replace(minute=0, second=0, microsecond=0)
    for i, t in enumerate(h["time"]):
        ts = datetime.fromisoformat(t)
        if ts <= start_hour:
            continue
        _, ic = describe(h["weather_code"][i], h["is_day"][i])
        pop = h["precipitation_probability"][i]
        out["ore"].append({
            "ora": ts.strftime("%H"),
            "temp": round(h["temperature_2m"][i]),
            "icona": ic,
            "pioggia": pop if pop is not None else 0,
        })
        if len(out["ore"]) >= 6:
            break

    out["pioggia_imminente"] = pioggia_imminente(data.get("minutely_15") or {}, now)

    d = data["daily"]
    oggi = now.date()
    for i, t in enumerate(d["time"]):
        day = datetime.fromisoformat(t).date()
        delta = (day - oggi).days
        if delta < -1:
            continue
        _, ic = describe(d["weather_code"][i], True)
        pop = d["precipitation_probability_max"][i]
        g = {
            "nome": {-1: "Ieri", 0: "Oggi"}.get(delta, GIORNI[day.weekday()]),
            "min": round(d["temperature_2m_min"][i]),
            "max": round(d["temperature_2m_max"][i]),
            "icona": ic,
            "pioggia": pop if pop is not None else 0,
            "passato": delta < 0,
        }
        if len(out["settimana"]) < 7:
            out["settimana"].append(g)
        if delta >= 0 and len(out["giorni"]) < 4:
            out["giorni"].append(g)
        if delta == 0 and d.get("sunrise"):
            out["alba"] = d["sunrise"][i][-5:]
            out["tramonto"] = d["sunset"][i][-5:]
    return out
