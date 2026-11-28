#!/bin/sh
# Avviato dal login automatico su tty1: lancia il compositor kiosk Wayland.
# labwc se c'è (supporta lo spegnimento del display di notte), altrimenti cage.
# La configurazione di labwc viene dalla versione aggiornata (OTA) se presente; il
# ciclo dell'interfaccia (session.sh) resta quello della ISO, che fa da rete di sicurezza.
export PYTHONPATH=/opt/comodino
export QT_QPA_PLATFORM=wayland
export QT_QUICK_CONTROLS_STYLE=Basic
export QT_IM_MODULE=qtvirtualkeyboard
export XDG_SESSION_TYPE=wayland

SYS="$HOME/.local/share/comodino/attuale/system"
[ -f "$SYS/labwc/rc.xml" ] || SYS=/opt/comodino/system

if command -v labwc >/dev/null 2>&1 && [ -f "$SYS/labwc/rc.xml" ]; then
    ICONE="$HOME/.local/share/icons"
    [ -d "$ICONE/comodino-vuoto" ] || python3 "$SYS/cursore_vuoto.py" "$ICONE" || true
    export XCURSOR_PATH="$ICONE:/usr/share/icons"
    export XCURSOR_THEME=comodino-vuoto
    export XCURSOR_SIZE=24
    exec labwc -C "$SYS/labwc" -S /opt/comodino/system/session.sh
fi
# -s: consente comunque Ctrl+Alt+F2 per una console di manutenzione
exec cage -s -- /opt/comodino/system/session.sh
