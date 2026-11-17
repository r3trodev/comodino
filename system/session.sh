#!/bin/sh
# Gira dentro cage e tiene viva l'interfaccia: se va in crash si riavvia da sola.
# Usa la versione aggiornata (~/.local/share/comodino/attuale) se c'è, altrimenti
# quella della ISO (/opt/comodino). Se una versione nuova va in crash 3 volte di
# fila appena avviata, torna da sola alla precedente.
BASE="$HOME/.local/share/comodino"
ATT="$BASE/attuale"
PREC="$BASE/precedente"
fallimenti=0

while true; do
    if [ -f "$ATT/comodino/__init__.py" ]; then
        export PYTHONPATH="$ATT"
    else
        export PYTHONPATH=/opt/comodino
    fi
    inizio=$(date +%s)
    python3 -m comodino.ui
    if [ $(( $(date +%s) - inizio )) -lt 30 ]; then
        fallimenti=$((fallimenti + 1))
    else
        fallimenti=0
    fi
    if [ "$fallimenti" -ge 3 ] && [ -L "$ATT" ]; then
        if [ -L "$PREC" ]; then
            ln -sfn "$(readlink "$PREC")" "$ATT"
            rm -f "$PREC"
        else
            rm -f "$ATT"
        fi
        logger -t comodino "aggiornamento difettoso: ripristinata la versione precedente"
        systemctl --user restart comodino-alarmd
        fallimenti=0
    fi
    sleep 2
done
