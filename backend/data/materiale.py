"""
materiale.py — il materiale che le analisi leggono, e che nessuna possiede.
# feat (Blocco 8): estratto da analisi.py quando la qualitativa ha chiesto le stesse cose.

Il pannello di metriche col confronto di settore, i cinque segnali di rischio,
il contesto del titolo, la lettura del JSON che torna dal modello: sono di
tutte le analisi, non della fondamentale che per prima li ha usati.

Stanno qui e non in `analisi.py` per una ragione pratica: la qualitativa e' un
modulo suo — quattro fasi sono troppe per stare dentro il registro dei metodi —
e se avesse dovuto importarle da li' avremmo avuto due moduli che si importano
a vicenda.
"""
import json
import logging
from pathlib import Path

from core.tipi import python_puro
from data import defeatbeta, depositi
from domain import pannello, prospetti, publication_dates, segnali

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Le metriche del pannello, e la loro gemella di settore dove esiste. Il
# confronto vale quanto il numero: "ROE del 15%" non si legge da solo.
PANNELLO_FONDAMENTALE = {
    "roe": "industry_roe",
    "roic": "industry_roic",
    "quarterly_gross_margin": "industry_quarterly_gross_margin",
    "quarterly_net_margin": "industry_quarterly_net_margin",
    "quarterly_operating_margin": None,
    "quarterly_revenue_yoy_growth": None,
    "net_debt_ttm": None,
    "debt_to_equity": None,
    "ttm_pe": None,
}


class AnalisiError(ValueError):
    """Un metodo non si puo' eseguire: manca la fonte, o il metodo non esiste."""


def contesto(simbolo: str, run_id: str | None) -> str:
    """Chi e' questo titolo, in due righe. Serve al modello per inquadrare."""
    profilo = defeatbeta.profile(simbolo, run_id=run_id)
    if not profilo.available:
        return f"{simbolo} — nessun profilo disponibile: {profilo.reason}"

    riga = profilo.frame.iloc[0]
    return (f"{simbolo} — settore {riga.get('sector')}, industria "
            f"{riga.get('industry')}, paese {riga.get('country')}")


def prompt(nome: str, **pezzi) -> str:
    """Compone un prompt dal suo file. I segnaposti si sostituiscono a mano,
    perche' il testo contiene graffe di esempio JSON che `format` interpreterebbe."""
    testo = (PROMPT_DIR / f"{nome}.txt").read_text(encoding="utf-8")
    for chiave, valore in pezzi.items():
        testo = testo.replace(f"{{{chiave}}}", valore)
    return testo


def leggi_json(testo: str) -> dict:
    """Il JSON dentro la risposta del modello, o un errore che lo dice.

    Un modello puo' incorniciare il JSON in un blocco di codice: si cerca fra
    la prima graffa e l'ultima invece di pretendere una risposta pulita.
    """
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio < 0 or fine <= inizio:
        raise AnalisiError("il modello non ha risposto con un JSON")
    try:
        return json.loads(testo[inizio:fine + 1])
    except json.JSONDecodeError as exc:
        raise AnalisiError(f"il JSON del modello non e' leggibile: {exc}") from exc


def _metrica_compressa(simbolo: str, nome: str, run_id: str | None) -> dict | None:
    """Una metrica ridotta ai tre numeri che si leggono. `None` se non c'e'.

    Una metrica che manca non ferma il pannello: le altre otto continuano a
    dire quello che sanno, e la sua assenza finisce fra i dati mancanti.
    """
    try:
        lettura = defeatbeta.metrica(simbolo, nome, run_id=run_id)
    except defeatbeta.DefeatbetaUnavailable:
        logger.warning("[ANALISI] metrica %s non disponibile per %s", nome, simbolo)
        return None

    if not lettura.available:
        return None

    colonne = [c for c in lettura.frame.columns if c != "symbol"]
    righe = [{c: python_puro(r[c]) for c in colonne} for _, r in lettura.frame.iterrows()]
    return pannello.comprimi(righe, colonne)


def pannello_metriche(simbolo: str, run_id: str | None) -> tuple[dict, list[str]]:
    """Tutte le metriche del pannello, col settore accanto. E cosa non c'era."""
    misure, mancanti = {}, []

    for nome, gemella in PANNELLO_FONDAMENTALE.items():
        titolo = _metrica_compressa(simbolo, nome, run_id)
        if titolo is None:
            mancanti.append(nome)
            continue
        settore = _metrica_compressa(simbolo, gemella, run_id) if gemella else None
        misure[nome] = pannello.confronta(titolo, settore)

    return misure, mancanti


def segnali_fondamentali(simbolo: str, run_id: str | None,
                         quando: str | None = None) -> dict:
    """I cinque segnali di rischio, dagli stessi bilanci della scheda.

    Con `quando` si ricostruiscono sui soli bilanci che a quella data erano gia'
    stati DEPOSITATI — non su quelli il cui periodo era chiuso. Un trimestre che
    finisce il 31 gennaio diventa pubblico a fine febbraio, e usarlo prima e'
    guardare il futuro.

    La risposta porta sempre `base_del_taglio`: dice se il taglio poggia su date
    di deposito reali o su un ritardo stimato. Due ricostruzioni fatte sulle une
    e sulle altre non sono confrontabili, e chi legge deve poterlo sapere senza
    andare a indovinare.
    """
    lettura = defeatbeta.statements(simbolo, run_id=run_id)
    if not lettura.available:
        raise AnalisiError(f"nessun bilancio per {simbolo}: {lettura.reason}")

    tutti = prospetti.periodi(lettura.frame)
    mappa = depositi.mappa(simbolo, run_id) if quando else {}
    visibili = None if quando is None else [
        p for p in tutti if publication_dates.was_public(mappa, p, quando, True)
    ]

    tabelle = {
        nome: prospetti.tabella(lettura.frame, nome, prospetti.TRIMESTRALE, visibili)
        for nome in prospetti.PROSPETTI
    }
    return {
        **segnali.tutti(tabelle),
        "as_of": quando,
        "periodi_totali": len(tutti),
        "periodi_visibili": len(tutti) if visibili is None else len(visibili),
        "base_del_taglio": None if quando is None else publication_dates.truncation_basis(
            mappa, visibili, True),
    }
