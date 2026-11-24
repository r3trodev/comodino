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
                try:
                    s = self._req("GET", "/api/states/" + urllib.parse.quote(eid))
                except Exception as e:      # HA lento o occupato (es. poca RAM): riprova una volta
                    if "(401)" in str(e) or "(404)" in str(e):
                        raise
                    s = self._req("GET", "/api/states/" + urllib.parse.quote(eid), timeout=15)
                a = s.get("attributes", {})
                out.append({
                    "id": eid,
                    "nome": a.get("friendly_name", eid),
                    "stato": s.get("state", "?"),
                    "unita": a.get("unit_of_measurement", ""),
                    "attivabile": dom in ATTIVABILI,
                    # last_reported cambia a ogni lettura; last_updated solo se il valore cambia
                    "riportato": s.get("last_reported") or "",
                    "aggiornato": s.get("last_updated") or "",
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
VECCHIO_SENZA_REPORT_MIN = 6 * 60   # HA senza last_reported: si sa solo quando il valore è cambiato


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


def _eta_sensore(s, adesso):
    """(minuti dall'ultima lettura certa, la data è affidabile?).

    last_updated cambia solo quando cambia il valore. last_reported, in teoria, a ogni
    lettura: ma con RFLink, se il valore è identico, HA spesso non lo aggiorna (resta uguale a
    last_updated). Ci si fida di last_reported solo quando è PIÙ RECENTE di last_updated,
    cioè quando si vede che HA lo aggiorna davvero anche senza cambi di valore.
    """
    rip = _eta_min(s.get("riportato"), adesso)
    agg = _eta_min(s.get("aggiornato"), adesso)
    if rip is not None and agg is not None and rip < agg - 0.05:
        return rip, True
    eta = rip if rip is not None else agg
    return eta, False


def clima_da_stati(c, stati, adesso=None):
    """{'interno': {temp, umidita}, 'esterno': {temp, umidita, pila_scarica?, vecchio?}}.

    Un termometro è "muto" solo se NESSUNO dei suoi sensori (temperatura, umidità, pila) ha
    dato segni di vita di recente: temperatura e umidità arrivano nello stesso pacchetto, e una
    temperatura ferma per ore non deve far sembrare spento il termometro.
    """
    adesso = adesso or datetime.now(timezone.utc)
    ids = entita_clima(c)
    per_id = {s["id"]: s for s in stati}
    out = {}
    for luogo in ("interno", "esterno"):
        chiavi = [f"{luogo}_temp", f"{luogo}_umidita"] + (["esterno_batteria"] if luogo == "esterno" else [])
        sensori = [per_id[ids[k]] for k in chiavi if ids.get(k) in per_id]
        ultime, preciso = [], False
        for s in sensori:
            eta, affidabile = _eta_sensore(s, adesso)
            if eta is not None:
                ultime.append(eta)
                preciso = preciso or affidabile
        limite = VECCHIO_DOPO_MIN if preciso else VECCHIO_SENZA_REPORT_MIN
        if ultime and min(ultime) > limite:
            out[luogo] = {"vecchio": True}
            continue
        val = {}
        for grandezza in ("temp", "umidita"):
            s = per_id.get(ids.get(f"{luogo}_{grandezza}"))
            if not s:
                continue
            try:
                v = float(s["stato"])
            except (TypeError, ValueError):
                continue
            val[grandezza] = round(v, 1) if grandezza == "temp" else round(v)
        if luogo == "esterno":
            b = per_id.get(ids.get("esterno_batteria"))
            if b and pila_scarica(b["stato"]):
                val["pila_scarica"] = True
        if val:
            out[luogo] = val
    return out


TIENI_ULTIMA_S = 15 * 60     # se HA non risponde per un momento, si tiene l'ultima lettura buona


def unisci_clima(nuovo, visti, adesso):
    """Copre i "buchi" dovuti a HA che non risponde: per ogni luogo assente nella lettura
    nuova si riusa l'ultima lettura buona, se ha meno di 15 minuti. Un termometro dichiarato
    "vecchio" (muto davvero) non viene coperto. Restituisce (dati, visti aggiornati)."""
    dati, visti = dict(nuovo), dict(visti)
    for luogo in ("interno", "esterno"):
        v = dati.get(luogo)
        if v and not v.get("vecchio") and v.get("temp") is not None:
            visti[luogo] = (adesso, v)
        elif not v and luogo in visti and adesso - visti[luogo][0] < TIENI_ULTIMA_S:
            dati[luogo] = visti[luogo][1]
    return dati, visti
