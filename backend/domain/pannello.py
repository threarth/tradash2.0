"""
pannello.py — le serie delle metriche ridotte a cio' che si legge.
# feat (Blocco 8): matematica pura, nessuna lettura.

Le metriche di Defeatbeta arrivano come serie storiche: `ttm_pe` da solo ha
6.875 righe, una per giorno di borsa. Mandarle intere a un modello sarebbe
pagare decine di migliaia di token per un numero che si guarda alla fine.

Qui ogni serie diventa tre cose: **quanto vale adesso**, **quanto valeva un
anno fa**, e **come si muove**. Piu' il confronto col settore quando esiste.

La compressione non e' un dettaglio di costo: un modello che riceve seimila
righe le riassume da solo, male e senza dirlo. Meglio decidere noi cosa conta.
"""
from core.tipi import python_puro

# Quanto indietro si guarda per dire "come si muove": un anno, che su una serie
# trimestrale sono quattro punti e su una giornaliera circa 252.
PUNTI_ANNO_TRIMESTRALE = 4
PUNTI_ANNO_GIORNALIERO = 252

# Oltre questa lunghezza la serie e' giornaliera, non trimestrale.
SOGLIA_SERIE_GIORNALIERA = 100

# Quanto deve cambiare un valore perche' sia un movimento e non rumore.
SOGLIA_MOVIMENTO = 0.05


def _valore(riga: dict, colonne: list[str]) -> tuple[str | None, float | None]:
    """Il numero che conta in una riga, e come si chiama.

    Le tabelle della libreria portano i valori intermedi accanto al risultato:
    `roe` ha utile, patrimonio e ROE. Il risultato e' l'ULTIMA colonna
    numerica, che e' anche la convenzione con cui sono scritte.
    """
    numeriche = [c for c in colonne
                 if isinstance(riga.get(c), (int, float)) and not isinstance(riga.get(c), bool)]
    if not numeriche:
        return None, None
    nome = numeriche[-1]
    return nome, float(riga[nome])


def comprimi(righe: list[dict], colonne: list[str]) -> dict | None:
    """Una serie ridotta a valore attuale, valore di un anno fa, movimento.

    Ritorna `None` se non c'e' niente da comprimere: una serie vuota non e' un
    valore pari a zero.
    """
    if not righe:
        return None

    nome, adesso = _valore(righe[-1], colonne)
    if adesso is None:
        return None

    passo = (PUNTI_ANNO_GIORNALIERO if len(righe) > SOGLIA_SERIE_GIORNALIERA
             else PUNTI_ANNO_TRIMESTRALE)
    prima = None
    if len(righe) > passo:
        _, prima = _valore(righe[-1 - passo], colonne)

    variazione = None
    if prima not in (None, 0):
        variazione = (adesso - prima) / abs(prima)

    return {
        "misura": nome,
        "adesso": round(adesso, 4),
        "un_anno_fa": None if prima is None else round(prima, 4),
        "variazione": None if variazione is None else round(variazione, 4),
        "movimento": _movimento(variazione),
        "punti": len(righe),
        "ultima_data": python_puro(righe[-1].get("report_date")),
    }


def _movimento(variazione: float | None) -> str:
    """Come si muove, in una parola. `None` quando non c'e' un anno di storia."""
    if variazione is None:
        return "non confrontabile"
    if variazione > SOGLIA_MOVIMENTO:
        return "in aumento"
    if variazione < -SOGLIA_MOVIMENTO:
        return "in calo"
    return "stabile"


def confronta(titolo: dict | None, settore: dict | None) -> dict | None:
    """Il titolo accanto alla sua industria, e di quanto si discosta.

    E' la domanda che il vecchio sistema non sapeva rispondere per undici
    ticker su diciotto: "questo numero e' alto?" non ha senso da solo.
    """
    if titolo is None or settore is None:
        return titolo

    scarto = None
    if settore["adesso"]:
        scarto = (titolo["adesso"] - settore["adesso"]) / abs(settore["adesso"])

    return {**titolo,
            "settore": settore["adesso"],
            "scarto_dal_settore": None if scarto is None else round(scarto, 4),
            "sopra_il_settore": None if scarto is None else scarto > 0}
