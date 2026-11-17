#!/usr/bin/env python3
"""Strumento per i rilasci firmati di Comodino (da usare sul PC).

    pip install cryptography

    python tools/ota.py chiavi        # una volta sola: crea la coppia di chiavi
    python tools/ota.py pacchetto     # crea dist/comodino-X.Y.Z.tar.gz e .sig
    python tools/ota.py verifica dist/comodino-X.Y.Z.tar.gz

La chiave privata (secrets/ota_privata.pem) è cifrata con una passphrase e NON va
mai su GitHub (secrets/ è escluso da git). La pubblica (system/ota.pub) sì: finisce
nella ISO e sul tablet in /etc/comodino/ota.pub.
"""
import argparse
import getpass
import gzip
import io
import re
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRIVATA = REPO / "secrets" / "ota_privata.pem"
PUBBLICA = REPO / "system" / "ota.pub"
DIST = REPO / "dist"


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return serialization, Ed25519PrivateKey
    except ImportError:
        sys.exit("Serve il pacchetto 'cryptography':  pip install cryptography")


def versione_progetto():
    testo = (REPO / "comodino" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', testo)
    if not m:
        sys.exit("versione non trovata in comodino/__init__.py")
    return m.group(1)


def cmd_chiavi(_):
    serialization, Ed25519PrivateKey = _crypto()
    if PRIVATA.exists():
        sys.exit(f"Esiste già {PRIVATA}: non la sovrascrivo (perderesti la possibilità di aggiornare i tablet).")
    pw = getpass.getpass("Passphrase per la chiave privata (min 12 caratteri): ")
    if len(pw) < 12 or pw != getpass.getpass("Ripeti la passphrase: "):
        sys.exit("Passphrase troppo corta o diversa.")
    k = Ed25519PrivateKey.generate()
    PRIVATA.parent.mkdir(exist_ok=True)
    PRIVATA.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.BestAvailableEncryption(pw.encode())))
    PUBBLICA.write_bytes(k.public_key().public_bytes(serialization.Encoding.PEM,
                                                     serialization.PublicFormat.SubjectPublicKeyInfo))
    print(f"Chiave privata: {PRIVATA}  (fanne un backup, offline)")
    print(f"Chiave pubblica: {PUBBLICA}  (va su GitHub e nella ISO)")


def _filtro(ti):
    if "__pycache__" in ti.name or ti.name.endswith(".pyc"):
        return None
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    ti.mtime = 0                         # pacchetto riproducibile
    ti.mode = 0o755 if (ti.isdir() or ti.name.endswith(".sh")) else 0o644
    return ti


def crea_tar(dest, ver):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as t:
        for cartella in ("comodino", "system"):
            t.add(REPO / cartella, arcname=cartella, filter=_filtro)
        info = tarfile.TarInfo("VERSION")
        dati = (ver + "\n").encode()
        info.size, info.mode = len(dati), 0o644
        t.addfile(info, io.BytesIO(dati))
    with open(dest, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as gz:
        gz.write(raw.getvalue())


def firma(file, privata=PRIVATA, passphrase=None):
    serialization, _ = _crypto()
    pw = passphrase if passphrase is not None else getpass.getpass("Passphrase della chiave privata: ")
    k = serialization.load_pem_private_key(Path(privata).read_bytes(), password=pw.encode())
    sig = Path(str(file) + ".sig")
    sig.write_bytes(k.sign(Path(file).read_bytes()))
    return sig


def cmd_pacchetto(args):
    if not PRIVATA.exists():
        sys.exit("Manca la chiave privata: esegui prima  python tools/ota.py chiavi")
    ver = versione_progetto()
    DIST.mkdir(exist_ok=True)
    pac = DIST / f"comodino-{ver}.tar.gz"
    crea_tar(pac, ver)
    sig = firma(pac)
    print(f"Creati:\n  {pac}\n  {sig}\n")
    print("Pubblica la release (tag = versione), per esempio con GitHub CLI:")
    print(f'  gh release create v{ver} "{pac}" "{sig}" --title "Comodino {ver}" --notes "Novità…"')
    print("oppure su github.com → Releases → Draft a new release, caricando i due file.")


def cmd_verifica(args):
    serialization, _ = _crypto()
    from cryptography.exceptions import InvalidSignature
    pub = serialization.load_pem_public_key(PUBBLICA.read_bytes())
    try:
        pub.verify(Path(args.file + ".sig").read_bytes(), Path(args.file).read_bytes())
        print("Firma valida.")
    except InvalidSignature:
        sys.exit("FIRMA NON VALIDA")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("chiavi").set_defaults(f=cmd_chiavi)
    sub.add_parser("pacchetto").set_defaults(f=cmd_pacchetto)
    v = sub.add_parser("verifica")
    v.add_argument("file")
    v.set_defaults(f=cmd_verifica)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
