"""
prospetti.py — i bilanci in forma lunga diventano una tabella per periodo.
# feat (Blocco 7): matematica pura, nessuna lettura.

Defeatbeta serve i bilanci in forma lunga: una riga per (data, voce, tipo,
periodicita'). Per guardarli servono le colonne — un periodo per colonna, una
voce per riga — e per confrontarli serve sapere QUALI periodi si possono
guardare a una certa data.

Il taglio temporale non e' un dettaglio di presentazione: e' la differenza fra
ricostruire cosa si sapeva allora e guardare il futuro fingendo di non farlo.

Unica dipendenza fuori da pandas: la conversione dei tipi, che sta in `core`
perche' serviva gia' a tre moduli diversi. Non e' I/O, e' aritmetica dei tipi.
"""
import pandas as pd

from core.tipi import python_puro

# Le colonne che Defeatbeta usa nella forma lunga.
COLONNA_PERIODO = "report_date"
COLONNA_VOCE = "item_name"
COLONNA_VALORE = "item_value"
COLONNA_TIPO = "finance_type"
COLONNA_PERIODICITA = "period_type"

# I tre prospetti, coi nomi che usa il dataset.
CONTO_ECONOMICO = "income_statement"
STATO_PATRIMONIALE = "balance_sheet"
RENDICONTO = "cash_flow"
PROSPETTI = (CONTO_ECONOMICO, STATO_PATRIMONIALE, RENDICONTO)

TRIMESTRALE = "quarterly"
ANNUALE = "annual"

# Il dataset usa "TTM" come periodo: non e' una data, e un confronto con una
# data lo tratterebbe come una stringa qualsiasi finendo dove capita.
PERIODO_TTM = "TTM"


def periodi(frame: pd.DataFrame) -> list[str]:
    """I periodi presenti, dal piu' recente. Il TTM resta fuori: non e' una data."""
    if frame is None or frame.empty:
        return []
    grezzi = {str(v)[:10] for v in frame[COLONNA_PERIODO].dropna().unique()}
    return sorted((p for p in grezzi if p != PERIODO_TTM), reverse=True)


def tabella(frame: pd.DataFrame, prospetto: str, periodicita: str = TRIMESTRALE,
            periodi_ammessi: list[str] | None = None) -> dict:
    """Un prospetto come `{voce: {periodo: valore}}`, coi periodi ammessi soltanto.

    `periodi_ammessi` e' il taglio temporale: chi lo passa ha gia' deciso cosa
    era pubblico a una certa data. Passare `None` significa "tutto", ed e'
    legittimo solo quando si guarda l'oggi.
    """
    if frame is None or frame.empty:
        return {"voci": {}, "periodi": []}

    scelte = frame[
        (frame[COLONNA_TIPO] == prospetto) & (frame[COLONNA_PERIODICITA] == periodicita)
    ]
    if scelte.empty:
        return {"voci": {}, "periodi": []}

    voci: dict[str, dict[str, float]] = {}
    visti: set[str] = set()
    for _, riga in scelte.iterrows():
        periodo = str(riga[COLONNA_PERIODO])[:10]
        if periodo == PERIODO_TTM:
            continue
        if periodi_ammessi is not None and periodo not in periodi_ammessi:
            continue
        valore = python_puro(riga[COLONNA_VALORE])
        if valore is None:      # la voce non c'e' per quel periodo
            continue
        voci.setdefault(str(riga[COLONNA_VOCE]), {})[periodo] = float(valore)
        visti.add(periodo)

    return {"voci": voci, "periodi": sorted(visti, reverse=True)}
