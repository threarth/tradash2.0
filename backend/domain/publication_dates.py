"""
publication_dates.py — quando un bilancio e' diventato PUBBLICO.
# feat (Blocco 7): copiato dal vecchio tradash, e reso puro.

## Il problema che risolve

Il motore point-in-time tronca le serie sulla `report_date`, cioe' la fine del
periodo economico. Ma un trimestre che chiude il 30 giugno viene depositato a
inizio agosto: un'analisi ricostruita al 15 luglio, troncando sulla fine
periodo, vede un bilancio che allora non esisteva. Sono ~40 giorni di futuro,
proprio nella finestra in cui il prezzo si muove di piu' — ed e' il look-ahead
piu' grave e meno visibile del sistema, perche' non produce nessun errore: solo
un backtest che sembra bravissimo.

## Cosa e' cambiato rispetto al vecchio tradash

Le date di deposito **gliele passa chi chiama**, in una mappa
`{fine_periodo: (data_deposito, fonte)}`. Prima se le andava a prendere da solo
e teneva una cache per ticker: comodo, ma faceva di un modulo di calcolo un
modulo che legge. Qui `domain/` non fa I/O — chi ha bisogno della mappa la
costruisce con `data/depositi.py`, che sa parlare con Defeatbeta.

## I due livelli, in quest'ordine

1. **Data di deposito REALE.** L'indice depositi Defeatbeta
   (`stock_sec_filing`) porta `report_date` e `filing_date` sulla stessa riga,
   con ~20 anni di storia e senza toccare sec.gov. Dove c'e', si usa quella.
   NON si usa `archived_documents`, che pure ha `filed_at`: quella tabella non
   ha una colonna con la fine del periodo, e una data di deposito senza il
   periodo a cui si riferisce non si puo' attaccare a nessuna riga di bilancio.
   Per gli stessi depositi l'indice porta entrambe le date, quindi non si perde
   niente.
2. **Ritardo prudente altrove.** Costanti versionate in `risk_thresholds`
   (gruppo `as_of`): 45 giorni per un trimestre, 75 per un annuale, gli
   estremi delle scadenze SEC per un filer non accelerato. Prudente qui
   significa *tardi*: meglio non vedere un dato che c'era, che vederne uno che
   non c'era.

## Cosa deve sempre uscire dal calcolo

**Quale dei due livelli e' stato usato.** Un backtest con date di deposito
reali e uno con ritardo stimato non sono confrontabili fra loro, e chi legge
un risultato deve poterlo sapere senza andare a indovinare.
"""
import logging
from datetime import date, datetime, timedelta

import config

logger = logging.getLogger(__name__)

# Da dove viene la data. `estimated` e' l'unica che non e' un fatto.
SOURCE_FILING_INDEX = "filing_index"
SOURCE_ESTIMATED = "estimated"

# I moduli annuali e trimestrali, americani ed esteri. Il 6-K non c'e': non e'
# un bilancio periodico e non ha una report_date confrontabile.
_ANNUAL_FORMS = ("10-K", "20-F", "40-F")
_QUARTERLY_FORMS = ("10-Q",)
_PERIODIC_FORMS = _ANNUAL_FORMS + _QUARTERLY_FORMS

# Mappa ticker -> {report_date: (filing_date, fonte)}, per la vita del processo.
# Non e' una cache di rete (quella sta sotto, in api_cache): serve a non
# ricostruire la stessa mappa per ognuna delle decine di serie che una singola
# analisi tronca.
def _as_iso(valore) -> str:
    """Data in ISO, accettando date, datetime o stringa."""
    if isinstance(valore, (date, datetime)):
        return valore.strftime("%Y-%m-%d")
    return str(valore)[:10]


def _nearest_known(report_iso: str, mappa: dict[str, tuple[str, str]],
                   tolerance_days: int) -> tuple[str, str] | None:
    """Deposito il cui periodo coincide con `report_iso`, entro la tolleranza.

    Le due fonti non si allineano sempre al giorno: un trimestre "chiuso il 28
    giugno" nei bilanci puo' comparire come 30 giugno nell'indice. Senza
    tolleranza si ricadrebbe sul ritardo stimato pur avendo il dato vero.
    """
    esatto = mappa.get(report_iso)
    if esatto is not None:
        return esatto
    try:
        target = datetime.strptime(report_iso, "%Y-%m-%d").date()
    except ValueError:
        return None

    migliore, distanza_minima = None, None
    for periodo, valore in mappa.items():
        try:
            candidato = datetime.strptime(periodo, "%Y-%m-%d").date()
        except ValueError:
            continue
        distanza = abs((candidato - target).days)
        if distanza <= tolerance_days and (distanza_minima is None or distanza < distanza_minima):
            migliore, distanza_minima = valore, distanza
    return migliore


def publication_date(depositi: dict, report_date, is_quarterly: bool = True) -> tuple[str, str]:
    """(data ISO in cui il periodo e' diventato pubblico, fonte della data).

    La fonte fa parte del risultato, non e' un dettaglio: `estimated` significa
    che quella data e' una nostra assunzione prudente, non un fatto.
    """
    report_iso = _as_iso(report_date)
    trovato = _nearest_known(report_iso, depositi or {},
                             config.AS_OF_TOLLERANZA_PERIODO_GIORNI)
    if trovato is not None:
        return trovato

    giorni = (config.AS_OF_RITARDO_TRIMESTRALE_GIORNI if is_quarterly
              else config.AS_OF_RITARDO_ANNUALE_GIORNI)
    try:
        stimata = datetime.strptime(report_iso, "%Y-%m-%d").date() + timedelta(days=giorni)
    except ValueError:
        # Fine periodo illeggibile: si dichiara ignoto invece di inventare una
        # data. Il chiamante lo trattera' come "non ancora pubblico".
        return report_iso, SOURCE_ESTIMATED
    return stimata.strftime("%Y-%m-%d"), SOURCE_ESTIMATED


def was_public(depositi: dict, report_date, as_of, is_quarterly: bool = True) -> bool:
    """True se quel periodo era gia' stato depositato alla data `as_of`."""
    pubblicazione, _ = publication_date(depositi, report_date, is_quarterly)
    return pubblicazione <= _as_iso(as_of)


def sources_used(depositi: dict, report_dates, is_quarterly: bool = True) -> dict[str, int]:
    """Quante date vengono da ciascuna fonte, per dichiararlo nell'output.

    Un risultato costruito su date di deposito reali e uno costruito su ritardi
    stimati non sono confrontabili fra loro.
    """
    conteggio: dict[str, int] = {}
    for report in report_dates:
        _, fonte = publication_date(depositi, report, is_quarterly)
        conteggio[fonte] = conteggio.get(fonte, 0) + 1
    return conteggio


# Le due fonti mescolate: alcuni periodi hanno la data di deposito reale e
# altri no. E' il caso piu' comune sui ticker con storia lunga, dove l'indice
# copre gli ultimi ~20 anni ma non i bilanci piu' vecchi.
SOURCE_MIXED = "mixed"

_BASIS_NOTES = {
    SOURCE_FILING_INDEX: "date di deposito reali dall'indice SEC",
    SOURCE_ESTIMATED: "nessuna data di deposito reale: il taglio temporale "
                      "poggia interamente su un ritardo stimato",
    SOURCE_MIXED: "parte dei periodi ha la data di deposito reale, il resto "
                  "un ritardo stimato",
}


def truncation_basis(depositi: dict, report_dates, is_quarterly: bool = True) -> dict:
    """Su cosa poggia un troncamento point-in-time: fatti o stima.

    E' la funzione che rende esigibile la regola in cima a questo modulo — un
    risultato costruito su date di deposito reali e uno costruito su ritardi
    stimati non sono confrontabili, e chi legge deve poterlo sapere senza
    andare a indovinare. `sources_used` contava gia' le fonti, ma il conteggio
    non arrivava a nessun risultato: la regola era scritta e non applicata.

    `source` e' la lettura sintetica: `filing_index` se ogni periodo ha la sua
    data vera, `estimated` se nessuno ce l'ha, `mixed` in mezzo. `None` quando
    non c'e' nemmeno un periodo su cui pronunciarsi — che non e' "affidabile",
    e' "non pervenuto".
    """
    conteggio = sources_used(depositi, report_dates, is_quarterly)
    reali = conteggio.get(SOURCE_FILING_INDEX, 0)
    stimate = conteggio.get(SOURCE_ESTIMATED, 0)
    totale = reali + stimate

    if totale == 0:
        prevalente = None
    elif stimate == 0:
        prevalente = SOURCE_FILING_INDEX
    elif reali == 0:
        prevalente = SOURCE_ESTIMATED
    else:
        prevalente = SOURCE_MIXED

    return {
        "source":            prevalente,
        "periods":           totale,
        "real_periods":      reali,
        "estimated_periods": stimate,
        "counts":            conteggio,
        "note": _BASIS_NOTES.get(prevalente) if prevalente else
                "nessun periodo su cui pronunciarsi",
    }
