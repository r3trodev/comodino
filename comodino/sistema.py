"""Funzioni di sistema per il pannello: Wi-Fi (NetworkManager), IP, ora, riavvio."""
import os
import shutil
import socket
import subprocess

# Output dei comandi sempre in inglese: con il sistema in italiano nmcli risponde
# "sì"/"connesso" invece di "yes"/"connected" e il parsing fallirebbe.
_ENV = dict(os.environ, LC_ALL="C", LANG="C", LANGUAGE="C")


def _run(args, timeout=20):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_ENV)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", f"{args[0]} non disponibile"
    except subprocess.TimeoutExpired:
        return 124, "", "tempo scaduto"


def split_terse(line):
    """Divide una riga `nmcli -t` sui ':' non preceduti da backslash."""
    fields, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    fields.append("".join(cur))
    return fields


def parse_wifi_list(text):
    nets = {}
    for line in text.splitlines():
        f = split_terse(line)
        if len(f) < 4 or not f[1]:
            continue
        in_use, ssid, signal, security = f[0], f[1], f[2], f[3]
        try:
            sig = int(signal)
        except ValueError:
            sig = 0
        prev = nets.get(ssid)
        if prev is None or sig > prev["segnale"] or in_use == "*":
            nets[ssid] = {
                "ssid": ssid,
                "segnale": sig,
                "sicurezza": security if security not in ("", "--") else "aperta",
                "protetta": security not in ("", "--"),
                "attiva": in_use == "*" or (prev or {}).get("attiva", False),
            }
    return sorted(nets.values(), key=lambda n: (not n["attiva"], -n["segnale"]))


def wifi_scan():
    if not shutil.which("nmcli"):
        return {"ok": False, "errore": "NetworkManager (nmcli) non disponibile", "reti": []}
    code, out, err = _run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
                           "device", "wifi", "list", "--rescan", "yes"], timeout=40)
    if code != 0:
        return {"ok": False, "errore": err.strip() or "scansione fallita", "reti": []}
    return {"ok": True, "reti": parse_wifi_list(out)}


def profili_wifi(ssid):
    """UUID dei profili NetworkManager salvati per questa rete."""
    code, out, _ = _run(["nmcli", "-t", "-f", "UUID,TYPE", "connection", "show"], timeout=10)
    if code != 0:
        return []
    uuids = []
    for line in out.splitlines():
        f = split_terse(line)
        if len(f) >= 2 and f[1] == "802-11-wireless":
            c, s, _ = _run(["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", f[0]], timeout=10)
            if c == 0 and s.strip() == ssid:
                uuids.append(f[0])
    return uuids


def dimentica_rete(ssid):
    for uuid in profili_wifi(ssid):
        _run(["nmcli", "connection", "delete", "uuid", uuid], timeout=15)


def wifi_connect(ssid, password=""):
    # Un tentativo fallito lascia salvato un profilo con la password sbagliata:
    # nmcli lo riuserebbe ignorando quella nuova. Si riparte sempre da zero.
    dimentica_rete(ssid)
    args = ["nmcli", "--wait", "45", "device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    code, out, err = _run(args, timeout=60)
    if code == 0:
        return {"ok": True, "messaggio": f"Connesso a {ssid}"}
    dimentica_rete(ssid)          # niente profili "rotti" per il prossimo tentativo
    msg = (err or out).strip().replace("Error: ", "")
    if "Secrets were required" in msg or "802-11-wireless-security" in msg:
        msg = "Password errata"
    elif code == 124:
        msg = "Tempo scaduto: la rete non risponde"
    return {"ok": False, "errore": msg or "connessione fallita"}


def wifi_status():
    code, out, _ = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "device", "wifi"], timeout=10)
    if code == 0:
        for line in out.splitlines():
            f = split_terse(line)
            if len(f) >= 3 and f[0] == "yes":
                return {"connesso": True, "ssid": f[1], "segnale": int(f[2] or 0)}
    return {"connesso": False, "ssid": "", "segnale": 0}


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 53))     # nessun pacchetto inviato: serve solo a scegliere l'interfaccia
            return s.getsockname()[0]
    except OSError:
        return ""


def ntp_synced():
    code, out, _ = _run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], timeout=5)
    if code != 0:
        return None
    return out.strip() == "yes"


def reboot():
    _run(["systemctl", "reboot"], timeout=10)


def poweroff():
    _run(["systemctl", "poweroff"], timeout=10)
