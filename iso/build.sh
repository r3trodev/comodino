#!/bin/bash
# Genera la ISO di Comodino. Da eseguire come root su Debian (VM su Proxmox, WSL2 Debian, ...).
#   sudo ./build.sh          build completa
#   sudo ./build.sh clean    ripulisce tutto
set -euo pipefail
cd "$(dirname "$0")"
REPO=$(cd .. && pwd)

[ "$(id -u)" -eq 0 ] || { echo "Esegui come root: sudo ./build.sh"; exit 1; }

if [ "${1:-}" = "clean" ]; then
    lb clean --purge
    rm -rf config/includes.chroot
    exit 0
fi

# --- dipendenze dell'host di build
NEEDED="live-build grub-common grub-efi-amd64-bin xorriso mtools dosfstools debian-archive-keyring"
MISSING=""
for p in $NEEDED; do dpkg -s "$p" >/dev/null 2>&1 || MISSING="$MISSING $p"; done
if [ -n "$MISSING" ]; then
    echo ">> Installo:$MISSING"
    apt-get update && apt-get install -y $MISSING
fi

[ -f "$REPO/config.toml" ] || {
    echo "Manca config.toml: copia config.example.toml in config.toml e compilalo (coordinate, link iCal)."
    exit 1
}

# --- copia app e file di sistema nell'albero della chroot
INC=config/includes.chroot
rm -rf "$INC"
install -d "$INC/opt/comodino" "$INC/etc/comodino"
cp -r "$REPO/comodino" "$REPO/system" "$INC/opt/comodino/"
find "$INC/opt/comodino" -name '__pycache__' -prune -exec rm -rf {} +
install -m 640 "$REPO/config.toml" "$INC/etc/comodino/config.toml"
install -D -m 644 "$REPO/system/comodino-alarmd.service" "$INC/etc/systemd/user/comodino-alarmd.service"
install -D -m 644 "$REPO/system/99-comodino-backlight.rules" "$INC/etc/udev/rules.d/99-comodino-backlight.rules"
install -D -m 644 "$REPO/system/getty-autologin.conf" "$INC/etc/systemd/system/getty@tty1.service.d/autologin.conf"
install -D -m 644 "$REPO/system/sshd-comodino.conf" "$INC/etc/ssh/sshd_config.d/comodino.conf"
install -D -m 644 "$REPO/system/50-comodino.rules" "$INC/etc/polkit-1/rules.d/50-comodino.rules"
install -D -m 644 "$REPO/system/99-comodino-efi" "$INC/etc/apt/apt.conf.d/99-comodino-efi"
if [ -f "$REPO/system/ota.pub" ]; then
    install -m 644 "$REPO/system/ota.pub" "$INC/etc/comodino/ota.pub"
    echo ">> Aggiornamenti firmati: chiave pubblica inclusa"
else
    echo "!! system/ota.pub mancante: gli aggiornamenti via GitHub non saranno attivi (python tools/ota.py chiavi)"
fi

# --- segreti opzionali (cartella secrets/ esclusa da git)
if [ -f "$REPO/secrets/wifi.nmconnection" ]; then
    install -D -m 600 "$REPO/secrets/wifi.nmconnection" "$INC/etc/NetworkManager/system-connections/casa.nmconnection"
    echo ">> Wi-Fi preconfigurato"
fi
if [ -f "$REPO/secrets/authorized_keys" ]; then
    install -m 644 "$REPO/secrets/authorized_keys" "$INC/etc/comodino/authorized_keys"
    echo ">> SSH con chiave abilitato"
fi

# --- build
lb clean
lb config
lb build

# --- fatto
ISO=$(ls -1 *.iso | head -n1)
echo ">> ISO pronta: $ISO"
