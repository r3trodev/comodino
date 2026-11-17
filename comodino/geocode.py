"""Ricerca località (geocoding Open-Meteo, gratuito, senza chiave)."""
import json
import urllib.parse
import urllib.request

API = "https://geocoding-api.open-meteo.com/v1/search"


def parse(data):
    out = []
    for r in data.get("results") or []:
        dettaglio = ", ".join(x for x in (r.get("admin2"), r.get("admin1"), r.get("country")) if x)
        out.append({
            "nome": r["name"],
            "dettaglio": dettaglio,
            "lat": round(float(r["latitude"]), 4),
            "lon": round(float(r["longitude"]), 4),
            "fuso": r.get("timezone") or "Europe/Rome",
        })
    return out


def cerca(testo, timeout=15):
    testo = (testo or "").strip()
    if len(testo) < 2:
        return {"ok": False, "errore": "Scrivi almeno 2 lettere", "risultati": []}
    q = urllib.parse.urlencode({"name": testo, "count": 8, "language": "it", "format": "json"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "comodino/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = parse(json.load(r))
    if not res:
        return {"ok": False, "errore": "Nessuna località trovata", "risultati": []}
    return {"ok": True, "risultati": res}
