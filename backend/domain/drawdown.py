"""
drawdown.py — quanto e' sceso, da quanto, e quanto ha recuperato.
# feat (Blocco 9): il `good_drawdown` che nel vecchio sistema era un servizio.

Nel vecchio tradash `good_drawdown` era un metodo di analisi LLM che leggeva
uno snapshot prodotto dal GD Monitor — il servizio che scandagliava da solo, e
che qui non esiste. Tolto il monitor, quel metodo restava senza dato.

Il concetto torna come **feature tecnica deterministica**: profondita', durata e
recupero calcolati dai prezzi. Niente LLM, niente servizio che gira per conto
suo, e una risposta finalmente verificabile alla domanda "basato su cosa?".

Matematica pura: entrano dei prezzi, escono dei numeri.
"""

# Sotto questa soglia un "drawdown" e' rumore di mercato, non una discesa.
PROFONDITA_MINIMA = 0.05


def _massimo_progressivo(chiusure: list[float]) -> list[float]:
    """Il massimo visto fino a ogni giorno: la linea da cui si misura la discesa."""
    massimi, corrente = [], float("-inf")
    for valore in chiusure:
        corrente = max(corrente, valore)
        massimi.append(corrente)
    return massimi


def serie_drawdown(chiusure: list[float]) -> list[float]:
    """Per ogni giorno, quanto si e' sotto il massimo precedente. Sempre <= 0."""
    massimi = _massimo_progressivo(chiusure)
    return [
        0.0 if massimo <= 0 else (valore - massimo) / massimo
        for valore, massimo in zip(chiusure, massimi, strict=True)
    ]


def profilo(chiusure: list[float]) -> dict | None:
    """Il drawdown corrente: quanto sotto il massimo, da quando, quanto recuperato.

    Ritorna `None` se non ci sono abbastanza prezzi per dire qualcosa: e' un
    dato che manca, non un drawdown pari a zero — e i due si leggono in modo
    molto diverso.
    """
    if not chiusure or len(chiusure) < 2:
        return None

    discese = serie_drawdown(chiusure)
    massimi = _massimo_progressivo(chiusure)

    attuale = discese[-1]
    picco = max(chiusure)
    minimo = min(chiusure)

    # Da quando dura: si risale finche' si era ancora al massimo. Il giorno del
    # massimo non fa parte della discesa, quindi si conta da quello dopo.
    giorni_sotto = 0
    for valore in reversed(discese):
        if valore >= 0:
            break
        giorni_sotto += 1

    # Il fondo toccato DENTRO la discesa in corso, non nella storia intera: un
    # crollo di dieci anni fa non dice niente su quanto si e' recuperato oggi.
    fondo = min(discese[-giorni_sotto:]) if giorni_sotto else 0.0
    recupero = 0.0 if fondo >= 0 else (attuale - fondo) / abs(fondo)

    return {
        "profondita_attuale": round(attuale, 4),
        "profondita_massima": round(fondo, 4),
        "giorni_sotto_il_massimo": giorni_sotto,
        "recupero_dal_fondo": round(min(max(recupero, 0.0), 1.0), 4),
        "massimo_di_riferimento": round(massimi[-1], 4),
        "massimo_storico": round(picco, 4),
        "minimo_storico": round(minimo, 4),
        "e_un_drawdown": abs(attuale) >= PROFONDITA_MINIMA,
    }
