"""Stato del server Proxmox (nodi, VM, container) via API, in sola lettura.

Sicurezza:
  - token API con ruolo PVEAuditor (può solo leggere);
  - il certificato di Proxmox è autofirmato: invece di disattivare il controllo TLS,
    se ne fissa l'impronta SHA-256 al primo collegamento (confermato dall'utente) e
    poi si rifiuta qualunque certificato diverso;
  - il token viaggia solo dopo che l'impronta è stata verificata.
"""
import hashlib
import http.client
import json
import ssl
from urllib.parse import urlparse


class CertificatoDaConfermare(Exception):
    def __init__(self, impronta):
        super().__init__(f"certificato da confermare: {impronta}")
        self.impronta = impronta


def formatta(hexstr):
    h = hexstr.replace(":", "").strip().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


class Proxmox:
    def __init__(self, url, token_id, secret, fingerprint="", timeout=8):
        u = urlparse(url if "://" in (url or "") else f"https://{url}")
        self.host, self.port = u.hostname, u.port or 8006
        self.token_id, self.secret = (token_id or "").strip(), (secret or "").strip()
        self.fingerprint = (fingerprint or "").replace(":", "").strip().lower()
        self.timeout = timeout

    @property
    def configurato(self):
        return bool(self.host and self.token_id and self.secret)

    def _connessione(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE          # la verifica la fa l'impronta qui sotto
        conn = http.client.HTTPSConnection(self.host, self.port, context=ctx, timeout=self.timeout)
        conn.connect()
        impronta = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
        if not self.fingerprint:
            conn.close()
            raise CertificatoDaConfermare(formatta(impronta))
        if impronta != self.fingerprint:
            conn.close()
            raise ValueError("ATTENZIONE: il certificato del server è cambiato. Collegamento rifiutato "
                             f"(nuovo: {formatta(impronta)[:23]}…). Se l'hai rinnovato tu, confermalo di nuovo.")
        return conn

    def impronta_attuale(self):
        """Impronta del certificato presentato ora dal server (per la conferma)."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(self.host, self.port, context=ctx, timeout=self.timeout)
        try:
            conn.connect()
            return formatta(hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest())
        finally:
            conn.close()

    def get(self, path):
        conn = self._connessione()
        try:
            conn.request("GET", "/api2/json" + path,
                         headers={"Authorization": f"PVEAPIToken={self.token_id}={self.secret}"})
            r = conn.getresponse()
            body = r.read()
            if r.status == 401:
                raise ValueError("token non valido (401)")
            if r.status == 403:
                raise ValueError("permessi insufficienti (403): al token serve il ruolo PVEAuditor su /")
            if r.status != 200:
                raise ValueError(f"errore HTTP {r.status}")
            return json.loads(body)["data"]
        finally:
            conn.close()

    def stato(self):
        return riassunto(self.get("/cluster/resources"))


def _pct(x):
    return round((x or 0) * 100)


def _gb(b):
    return round((b or 0) / 1024 ** 3, 1)


def _durata(s):
    s = int(s or 0)
    g, h = s // 86400, (s % 86400) // 3600
    return f"{g}g {h}h" if g else f"{h}h {(s % 3600) // 60}m"


def riassunto(risorse):
    nodi, vm = [], []
    for r in risorse:
        if r.get("type") == "node":
            nodi.append({"nome": r.get("node", "?"), "attivo": r.get("status") == "online",
                         "cpu": _pct(r.get("cpu")), "ram": f"{_gb(r.get('mem'))}/{_gb(r.get('maxmem'))} GB",
                         "uptime": _durata(r.get("uptime"))})
        elif r.get("type") in ("qemu", "lxc"):
            vm.append({"id": r.get("vmid"), "nome": r.get("name") or str(r.get("vmid")),
                       "tipo": "VM" if r["type"] == "qemu" else "CT",
                       "attiva": r.get("status") == "running",
                       "cpu": _pct(r.get("cpu")), "ram": f"{_gb(r.get('mem'))}/{_gb(r.get('maxmem'))} GB",
                       "uptime": _durata(r.get("uptime")) if r.get("status") == "running" else ""})
    vm.sort(key=lambda x: x["id"] or 0)
    return {"nodi": nodi, "vm": vm,
            "attive": sum(v["attiva"] for v in vm), "totale": len(vm)}


def nuove_fermate(prima, adesso):
    """Nomi delle VM che erano accese e ora sono ferme."""
    era = {v["id"]: v["attiva"] for v in prima}
    return [v["nome"] for v in adesso if not v["attiva"] and era.get(v["id"])]
