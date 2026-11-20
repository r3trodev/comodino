"""Rischio di muffa e condensa in casa.

La muffa non nasce nell'aria della stanza ma sui punti più freddi dei muri (angoli,
spigoli, dietro gli armadi), dove l'umidità relativa è più alta. Si stima la temperatura
di quel punto con il fattore di temperatura superficiale (fRsi, UNI EN ISO 13788):

    T_muro = T_fuori + fRsi * (T_dentro - T_fuori)

e si calcola l'umidità relativa che l'aria della stanza avrebbe a contatto con il muro.
Sopra l'80% per qualche giorno la muffa cresce; al 100% (muro sotto il punto di
rugiada) l'acqua condensa.
"""
import math


def pressione_vapore(t):
    """Pressione di vapore saturo (hPa), formula di Magnus."""
    return 6.112 * math.exp(17.62 * t / (243.12 + t))


def punto_rugiada(t, ur):
    g = math.log(max(ur, 1) / 100) + 17.62 * t / (243.12 + t)
    return 243.12 * g / (17.62 - g)


def umidita_assoluta(t, ur):
    """Grammi di vapore per metro cubo d'aria."""
    return 216.7 * (ur / 100 * pressione_vapore(t)) / (273.15 + t)


def rischio(t_dentro, ur_dentro, t_fuori, fattore=0.7):
    """None se mancano i dati, altrimenti {livello, testo, rugiada, muro, ur_muro}.

    livello: ok | attenzione | rischio | condensa
    """
    if t_dentro is None or ur_dentro is None or t_fuori is None:
        return None
    muro = t_fuori + fattore * (t_dentro - t_fuori)
    ur_muro = 100 * ur_dentro / 100 * pressione_vapore(t_dentro) / pressione_vapore(muro)
    rugiada = punto_rugiada(t_dentro, ur_dentro)
    if ur_muro >= 100:
        livello, testo = "condensa", "condensa sui muri freddi"
    elif ur_muro >= 80:
        livello, testo = "rischio", "rischio muffa"
    elif ur_muro >= 70:
        livello, testo = "attenzione", "muffa: arieggia"
    else:
        livello, testo = "ok", "muffa: nessun rischio"
    return {"livello": livello, "testo": testo, "rugiada": round(rugiada, 1),
            "muro": round(muro, 1), "ur_muro": min(100, round(ur_muro))}
