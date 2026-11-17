#!/bin/sh
# Avvia il demone sveglia con la versione aggiornata, ma SOLO se si importa senza
# errori: altrimenti usa quella della ISO. La sveglia deve suonare sempre.
ATT="$HOME/.local/share/comodino/attuale"
if [ -f "$ATT/comodino/__init__.py" ] && \
   PYTHONPATH="$ATT" timeout 60 python3 -c "import comodino.alarmd" 2>/dev/null; then
    export PYTHONPATH="$ATT"
else
    export PYTHONPATH=/opt/comodino
fi
exec python3 -m comodino.alarmd
