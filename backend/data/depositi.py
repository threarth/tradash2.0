"""
depositi.py — le date in cui un bilancio e' stato depositato alla SEC.
# feat (Blocco 7): il pezzo che legge, tenuto fuori dal calcolo.

`domain/publication_dates.py` sa dire quando un periodo e' diventato pubblico,
ma non sa leggere niente: la mappa gliela passa questo modulo, che parla con
Defeatbeta attraverso il punto unico.

E' la stessa divisione che tiene `domain/` senza I/O — con un vantaggio
misurabile: il calcolo si prova con una mappa scritta a mano, senza rete.
"""
import logging

from core.tipi import python_puro
from data import defeatbeta
from domain import publication_dates

logger = logging.getLogger(__name__)

# I moduli periodici: sono gli unici che hanno una fine periodo da attaccare a
# una riga di bilancio. Un 8-K non chiude nessun trimestre.
FORME_ANNUALI = ("10-K", "20-F", "40-F")
FORME_TRIMESTRALI = ("10-Q",)
FORME_PERIODICHE = FORME_ANNUALI + FORME_TRIMESTRALI


def mappa(simbolo: str, run_id: str | None = None) -> dict[str, tuple[str, str]]:
    """`{fine_periodo: (data_deposito, fonte)}` per un titolo.

    Un periodo puo' comparire piu' volte — deposito originale e rettifiche
    successive: vince il PRIMO, perche' e' quello che ha reso pubblico il dato.
    Una rettifica non retrodata la notizia.

    Un titolo senza depositi non e' un errore: ritorna una mappa vuota, e chi
    calcola ricadra' sul ritardo stimato dichiarandolo.
    """
    lettura = defeatbeta.sec_filings(simbolo, run_id=run_id)
    if not lettura.available:
        logger.info("[DEPOSITI] nessun deposito per %s: %s", simbolo, lettura.reason)
        return {}

    trovate: dict[str, tuple[str, str]] = {}
    for _, riga in lettura.frame.iterrows():
        if riga.get("form_type") not in FORME_PERIODICHE:
            continue
        periodo = python_puro(riga.get("report_date"))
        deposito = python_puro(riga.get("filing_date"))
        if not periodo or not deposito:
            continue

        chiave, valore = str(periodo)[:10], str(deposito)[:10]
        precedente = trovate.get(chiave)
        if precedente is None or valore < precedente[0]:
            trovate[chiave] = (valore, publication_dates.SOURCE_FILING_INDEX)

    return trovate
