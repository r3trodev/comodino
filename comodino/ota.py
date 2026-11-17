"""Aggiornamenti via rete (GitHub Releases), firmati con Ed25519.

Una release su GitHub contiene due file:
    comodino-X.Y.Z.tar.gz       (comodino/, system/, VERSION)
    comodino-X.Y.Z.tar.gz.sig   (firma Ed25519 grezza del .tar.gz, 64 byte)

Sul tablet:
  1. si legge l'ultima release dall'API di GitHub;
  2. si scarica il pacchetto (con limite di dimensione) e la firma;
  3. si verifica la firma con la chiave pubblica in /etc/comodino/ota.pub
     (di root: l'utente kiosk non può sostituirla);
  4. si estrae in modo sicuro (niente percorsi assoluti, "..", link o device);
  5. VERSION dentro il pacchetto (firmato) deve coincidere col tag ed essere più
     nuova di quella in uso: niente downgrade con vecchi pacchetti firmati;
  6. prova di avvio: il codice nuovo deve compilare e il demone sveglia importarsi;
  7. cambio atomico del link "attuale"; la versione di prima resta come "precedente".

Si aggiorna solo l'applicazione (cartella comodino/): pacchetti di sistema e file
in /etc restano quelli della ISO.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from . import __version__

LIMITE_BYTE = 30 * 1024 * 1024
NOME = re.compile(r"^comodino-(\d+\.\d+\.\d+)\.tar\.gz$")


def base_dir():
    b = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(b) / "comodino"


def chiave_pubblica():
    for p in (os.environ.get("COMODINO_OTA_PUB"), "/etc/comodino/ota.pub",
              Path(__file__).resolve().parent.parent / "system" / "ota.pub"):
        if p and Path(p).is_file():
            return Path(p)
    return None


def versione(s):
    """'v0.9.1' -> (0, 9, 1)"""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (s or "").strip())
    if not m:
        raise ValueError(f"versione non valida: {s!r}")
    return tuple(int(x) for x in m.groups())


# ------------------------------------------------------------------ GitHub
def _richiesta(url, token="", accept="application/vnd.github+json"):
    h = {"User-Agent": "comodino-ota", "Accept": accept}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=h)


def parse_release(data):
    tag = data.get("tag_name", "")
    v = ".".join(map(str, versione(tag)))
    assets = {a["name"]: a for a in data.get("assets", [])}
    pacchetto = f"comodino-{v}.tar.gz"
    if pacchetto not in assets or pacchetto + ".sig" not in assets:
        raise ValueError(f"la release {tag} non contiene {pacchetto} e {pacchetto}.sig")
    a = assets[pacchetto]
    return {
        "versione": v,
        "tag": tag,
        "note": (data.get("body") or "").strip()[:1500],
        "data": (data.get("published_at") or "")[:10],
        "url": a["browser_download_url"],
        "url_firma": assets[pacchetto + ".sig"]["browser_download_url"],
        "api_url": a.get("url", ""),
        "api_url_firma": assets[pacchetto + ".sig"].get("url", ""),
        "dimensione": a.get("size", 0),
    }


def ultima_release(repo, token="", timeout=15):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo or ""):
        raise ValueError("repository non configurato (formato: utente/progetto)")
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    with urllib.request.urlopen(_richiesta(url, token), timeout=timeout) as r:
        return parse_release(json.load(r))


class _SenzaTokenSuAltriHost(urllib.request.HTTPRedirectHandler):
    """Al reindirizzamento verso lo storage di GitHub il token non va inoltrato."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        nuova = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nuova is not None and urllib.parse.urlparse(newurl).hostname != urllib.parse.urlparse(req.full_url).hostname:
            nuova.remove_header("Authorization")
        return nuova


def scarica(url, dest, token="", limite=LIMITE_BYTE, timeout=60):
    # repo privato: URL dell'API con token e Accept octet-stream; pubblico: link diretto
    req = _richiesta(url, token, accept="application/octet-stream")
    apri = urllib.request.build_opener(_SenzaTokenSuAltriHost()).open
    n = 0
    with apri(req, timeout=timeout) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            n += len(chunk)
            if n > limite:
                raise ValueError("file troppo grande")
            f.write(chunk)
    return n


# ------------------------------------------------------------------ firma
def verifica_firma(file, firma, chiave):
    """True se la firma Ed25519 è valida. Usa openssl; in mancanza, python3-cryptography."""
    if chiave is None or not Path(chiave).is_file():
        raise ValueError("chiave pubblica di aggiornamento mancante (/etc/comodino/ota.pub)")
    if Path(firma).stat().st_size != 64:
        return False
    if shutil.which("openssl"):
        r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(chiave),
                            "-rawin", "-in", str(file), "-sigfile", str(firma)],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
    except ImportError:
        raise RuntimeError("né openssl né python3-cryptography disponibili") from None
    k = load_pem_public_key(Path(chiave).read_bytes())
    try:
        k.verify(Path(firma).read_bytes(), Path(file).read_bytes())
        return True
    except InvalidSignature:
        return False


# ------------------------------------------------------------------ estrazione
def estrai(tar_path, dest):
    """Estrazione prudente: solo file e cartelle normali dentro dest."""
    dest = Path(dest)
    dest.mkdir(parents=True)
    with tarfile.open(tar_path, "r:gz") as t:
        membri = t.getmembers()
        for m in membri:
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"percorso non ammesso nel pacchetto: {m.name}")
            if not (m.isfile() or m.isdir()):
                raise ValueError(f"tipo di file non ammesso nel pacchetto: {m.name}")
        t.extractall(dest, members=membri, filter="data")
    if not (dest / "comodino" / "__init__.py").is_file() or not (dest / "VERSION").is_file():
        raise ValueError("pacchetto incompleto (mancano comodino/ o VERSION)")
    return (dest / "VERSION").read_text().strip()


def prova_avvio(cartella):
    """Il codice nuovo deve compilare e il demone sveglia deve importarsi (senza Qt)."""
    env = dict(os.environ, PYTHONPATH=str(cartella))
    for cmd in ([sys.executable, "-m", "compileall", "-q", str(Path(cartella) / "comodino")],
                [sys.executable, "-c", "import comodino.alarmd, comodino.weather, comodino.icsparse"]):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env, cwd=str(cartella))
        if r.returncode != 0:
            raise RuntimeError("prova di avvio fallita: " + (r.stderr or r.stdout).strip()[-300:])


# ------------------------------------------------------------------ versioni installate
def _link(nome):
    return base_dir() / nome


def _punta(link, target):
    tmp = link.with_name(link.name + ".nuovo")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, link)            # cambio atomico


def stato_locale():
    att, prec = _link("attuale"), _link("precedente")
    return {
        "versione": __version__,
        "da_aggiornamento": att.is_symlink(),
        "precedente": os.readlink(prec).rsplit("/", 1)[-1] if prec.is_symlink() else
                      ("versione della ISO" if att.is_symlink() else ""),
    }


def installa(info, token="", corrente=__version__, chiave=None):
    """Scarica, verifica e attiva la release `info`. Restituisce la versione installata."""
    if versione(info["versione"]) <= versione(corrente):
        raise ValueError(f"la versione {info['versione']} non è più nuova di {corrente}")
    chiave = chiave or chiave_pubblica()
    base = base_dir()
    vers = base / "versioni"
    vers.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        tmp = Path(tmp)
        pac, sig = tmp / "pacchetto.tar.gz", tmp / "pacchetto.sig"
        privato = bool(token and info.get("api_url"))
        scarica(info["api_url"] if privato else info["url"], pac, token if privato else "")
        scarica(info["api_url_firma"] if privato else info["url_firma"], sig,
                token if privato else "", limite=1024)
        if not verifica_firma(pac, sig, chiave):
            raise ValueError("FIRMA NON VALIDA: aggiornamento rifiutato")
        dentro = estrai(pac, tmp / "estratto")
        if dentro != info["versione"]:
            raise ValueError(f"il pacchetto contiene la versione {dentro}, non {info['versione']}")
        prova_avvio(tmp / "estratto")
        finale = vers / info["versione"]
        if finale.exists():
            shutil.rmtree(finale)
        (tmp / "estratto").rename(finale)

    att, prec = _link("attuale"), _link("precedente")
    if att.is_symlink():
        _punta(prec, os.readlink(att))
    elif prec.is_symlink():
        prec.unlink()                # la precedente è la versione della ISO
    _punta(att, str(finale))
    _pulisci()
    return info["versione"]


def ripristina():
    """Torna alla versione precedente (o a quella della ISO)."""
    att, prec = _link("attuale"), _link("precedente")
    if prec.is_symlink():
        _punta(att, os.readlink(prec))
        prec.unlink()
        return os.readlink(att).rsplit("/", 1)[-1]
    if att.is_symlink():
        att.unlink()
        return "versione della ISO"
    raise ValueError("non c'è una versione precedente")


def _pulisci():
    """Tiene solo la versione attuale e la precedente."""
    tenere = {os.path.realpath(_link(n)) for n in ("attuale", "precedente") if _link(n).is_symlink()}
    vers = base_dir() / "versioni"
    for d in vers.iterdir() if vers.is_dir() else []:
        if os.path.realpath(d) not in tenere:
            shutil.rmtree(d, ignore_errors=True)
