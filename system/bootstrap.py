"""Attiva gli aggiornamenti via GitHub su un tablet già installato. Da root, UNA volta:

python3 -c "R='utente/comodino';import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/'+R+'/main/system/bootstrap.py').read())"

Scarica l'ultima release, aggiorna /opt/comodino (app e script di sistema),
installa la chiave pubblica in /etc/comodino/ota.pub e imposta il repository.
Questa prima volta ci si fida di GitHub (HTTPS); dagli aggiornamenti successivi
ogni pacchetto deve essere firmato con la tua chiave.
"""
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

repo = globals().get("R") or os.environ.get("COMODINO_REPO", "")
if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
    raise SystemExit("Imposta il repository: R='utente/progetto'")
if os.geteuid() != 0:
    raise SystemExit("Va eseguito come root.")

OPT = Path("/opt/comodino")


def get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "comodino-bootstrap", "Accept": accept})
    return urllib.request.urlopen(req, timeout=60)


print(f">> Cerco l'ultima release di {repo}…")
rel = json.load(get(f"https://api.github.com/repos/{repo}/releases/latest"))
asset = next(a for a in rel["assets"] if re.fullmatch(r"comodino-\d+\.\d+\.\d+\.tar\.gz", a["name"]))
print(f">> Scarico {asset['name']}…")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    pac = tmp / "p.tar.gz"
    with get(asset["browser_download_url"], "application/octet-stream") as r, open(pac, "wb") as f:
        shutil.copyfileobj(r, f)
    out = tmp / "x"
    out.mkdir()
    with tarfile.open(pac) as t:
        for m in t.getmembers():
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts or not (m.isfile() or m.isdir()):
                raise SystemExit(f"pacchetto sospetto: {m.name}")
        t.extractall(out, filter="data")
    if not (out / "system" / "ota.pub").is_file():
        raise SystemExit("la release non contiene system/ota.pub")

    # copia di sicurezza della versione attuale
    bak = Path(f"/opt/comodino.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copytree(OPT, bak, symlinks=True)
    print(f">> Copia di sicurezza in {bak}")
    for d in ("comodino", "system"):
        shutil.rmtree(OPT / d, ignore_errors=True)
        shutil.copytree(out / d, OPT / d)

S = OPT / "system"
for sh in S.glob("*.sh"):
    sh.chmod(0o755)
copie = {
    "ota.pub": "/etc/comodino/ota.pub",
    "comodino-alarmd.service": "/etc/systemd/user/comodino-alarmd.service",
    "99-comodino-backlight.rules": "/etc/udev/rules.d/99-comodino-backlight.rules",
    "50-comodino.rules": "/etc/polkit-1/rules.d/50-comodino.rules",
    "99-comodino-efi": "/etc/apt/apt.conf.d/99-comodino-efi",
}
for src, dst in copie.items():
    if (S / src).is_file():
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(S / src, dst)
        os.chmod(dst, 0o644)

cfg = Path("/etc/comodino/config.toml")
testo = cfg.read_text() if cfg.exists() else ""
if "[aggiornamenti]" not in testo:
    cfg.write_text(testo.rstrip() + f'\n\n[aggiornamenti]\nrepo = "{repo}"\n')
subprocess.run(["python3", "-m", "compileall", "-q", str(OPT)], check=False)
print(f">> Fatto: Comodino {rel.get('tag_name')} installato, aggiornamenti attivi.")
print(">> Riavvia il tablet con:  reboot")
