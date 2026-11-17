#!/bin/sh
# Avviato dal login automatico su tty1: lancia cage (compositor kiosk Wayland).
export PYTHONPATH=/opt/comodino
export QT_QPA_PLATFORM=wayland
export QT_QUICK_CONTROLS_STYLE=Basic
export QT_IM_MODULE=qtvirtualkeyboard
export XDG_SESSION_TYPE=wayland
# -s: consente comunque Ctrl+Alt+F2 per una console di manutenzione
exec cage -s -- /opt/comodino/system/session.sh
