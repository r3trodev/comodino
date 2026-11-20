"""Client minimo per l'API REST di Home Assistant."""
import json
import re
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request

ATTIVABILI = {"light", "switch", "input_boolean", "fan", "automation", "script"}


class HomeAssistant:
    def __init__(self, url, token):
        self.url = (url or "").strip().rstrip("/")
        self.token = (token or "").strip()

    @property
    def configurato(self):
        return bool(self.url and self.token)

    def _req(self, method, path, data=None, timeout=8):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.url + path, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError("token non valido (401)") from None
            if e.code == 404:
                raise RuntimeError("non trovato (404)") from None
            raise RuntimeError(f"errore HTTP {e.code}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"non raggiungibile ({e.reason})") from None

    def verifica(self):
        if not self.configurato:
            return {"ok": None, "dettaglio": "non configurato"}
        try:
            cfg = self._req("GET", "/api/config")
            return {"ok": True, "dettaglio": f"connesso, versione {cfg.get('version', '?')}"}
        except Exception as e:
            return {"ok": False, "dettaglio": str(e)}

    def stati(self, entity_ids):
        out = []
        for eid in entity_ids:
            dom = eid.split(".", 1)[0]
            try:
                s = self._req("GET", "/api/states/" + urllib.parse.quote(eid))
                a = s.get("attributes", {})
                out.append({
                    "id": eid,
                    "nome": a.get("friendly_name", eid),
                    "stato": s.get("state", "?"),
                    "unita": a.get("unit_of_measurement", ""),
                    "attivabile": dom in ATTIVABILI,
                    # last_reported cambia a ogni lettura anche se il valore è uguale (HA 2024.3+)
                    "aggiornato": s.get("last_reported") or s.get("last_updated") or "",
                })
            except Exception:
                out.append({"id": eid, "nome": eid, "stato": "?", "unita": "", "attivabile": False})
        return out

    def toggle(self, entity_id):
        dom = entity_id.split(".", 1)[0]
        if dom not in ATTIVABILI:
            return
        servizio = "trigger" if dom == "automation" else ("turn_on" if dom == "script" else "toggle")
        self._req("POST", f"/api/services/{dom}/{servizio}", {"entity_id": entity_id})

    def accendi(self, entity_id, on):
        dom = entity_id.split(".", 1)[0]
        self._req("POST", f"/api/services/{dom}/{'turn_on' if on else 'turn_off'}", {"entity_id": entity_id})

    def imposta_stato(self, entity_id, stato, attributi):
        self._req("POST", f"/api/states/{entity_id}", {"state": stato, "attributes": attributi})

    def prese(self):
        """Interruttori (switch.*) disponibili: candidati per la presa del caricatore."""
        out = []
        for s in self._req("GET", "/api/states", timeout=15) or []:
            eid = s.get("entity_id", "")
            if eid.startswith("switch."):
                out.append({"id": eid, "nome": s.get("attributes", {}).get("friendly_name", eid),
                            "stato": s.get("state", "")})
        return sorted(out, key=lambda x: x["nome"].lower())

    def evento(self, tipo, dati):
        self._req("POST", f"/api/events/{tipo}", dati)


# ---------------------------------------------------------------- sensori di temperatura

VECCHIO_DOPO_MIN = 60        # nessuna lettura da più di un'ora: il sensore non trasmette


def entita_clima(c):
    """{chiave: entity_id} dei sensori da leggere. La pila del termometro di fuori, se non
    indicata, si ricava dal sensore di temperatura (RFLink: sensor.xiron_0801_temp -> _bat)."""
    ids = {k: v for k, v in c.items() if v and k in (
        "interno_temp", "interno_umidita", "esterno_temp", "esterno_umidita", "esterno_batteria")}
    if not ids.get("esterno_batteria"):
        m = re.fullmatch(r"(sensor\.[\w]+)_temp", ids.get("esterno_temp", ""))
        if m:
            ids["esterno_batteria"] = m.group(1) + "_bat"
    return ids


def pila_scarica(stato):
    s = str(stato).strip().lower()
    if s in ("low", "on", "true", "scarica"):
        return True
    try:
        return float(s) <= 15
    except ValueError:
        return False


def _eta_min(quando, adesso):
    try:
        t = datetime.fromisoformat(quando.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return (adesso - t).total_seconds() / 60


def clima_da_stati(c, stati, adesso=None):
    """{'interno': {temp, umidita}, 'esterno': {temp, umidita, pila_scarica?, vecchio?}}."""
    adesso = adesso or datetime.now(timezone.utc)
    ids = entita_clima(c)
    per_id = {s["id"]: s for s in stati}
    out = {}
    for luogo in ("interno", "esterno"):
        val = {}
        for grandezza in ("temp", "umidita"):
            s = per_id.get(ids.get(f"{luogo}_{grandezza}"))
            if not s:
                continue
            try:
                v = float(s["stato"])
            except (TypeError, ValueError):
                continue
            eta = _eta_min(s.get("aggiornato"), adesso)
            if eta is not None and eta > VECCHIO_DOPO_MIN:
                val["vecchio"] = True
                continue
            val[grandezza] = round(v, 1) if grandezza == "temp" else round(v)
        if luogo == "esterno":
            b = per_id.get(ids.get("esterno_batteria"))
            if b and pila_scarica(b["stato"]):
                val["pila_scarica"] = True
        if val:
            out[luogo] = val
    return out
