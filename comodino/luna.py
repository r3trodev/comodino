"""Fase lunare calcolata (nessuna rete): età della luna dal novilunio di riferimento."""
import math
from datetime import datetime, timezone

SINODICO = 29.530588853                                   # giorni
NOVILUNIO = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
NOMI = ["Luna nuova", "Luna crescente", "Primo quarto", "Gibbosa crescente",
        "Luna piena", "Gibbosa calante", "Ultimo quarto", "Luna calante"]
ICONE = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]


def fase(quando=None):
    quando = quando or datetime.now(timezone.utc)
    if quando.tzinfo is None:
        quando = quando.astimezone()
    eta = ((quando - NOVILUNIO).total_seconds() / 86400) % SINODICO
    frazione = eta / SINODICO
    i = int(frazione * 8 + 0.5) % 8
    return {
        "nome": NOMI[i],
        "icona": ICONE[i],
        "illuminazione": round((1 - math.cos(2 * math.pi * frazione)) / 2 * 100),
        "eta_giorni": round(eta, 1),
    }
