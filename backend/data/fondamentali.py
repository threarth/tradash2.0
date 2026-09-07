"""
fondamentali.py — i bilanci recenti di TUTTO l'universo, in tabella.
# feat: lo screening smette di essere solo di prezzo.

## Il buco che chiude

L'universo sapeva com'e' andato il prezzo e nient'altro: anagrafica,
capitalizzazione, ultima chiusura, volume. Cosi' lo scanner poteva cercare solo
per prezzo, e i sei segnali del rilevatore spin-off — tre dei quali guardano
margine, ricavi ed EPS — erano calcolabili soltanto sui ventisette titoli di una
lista venuta da fuori.

Due imbuti che non si parlavano: uno arrivava a undicimila titoli e sapeva poco,
l'altro sapeva la cosa giusta e arrivava a ventisette.

## Cosa c'e' dentro

Tre voci per trimestre — ricavi, margine lordo, EPS diluito — per gli ultimi
otto trimestri di ogni titolo, **con la data in cui quel trimestre e' stato
depositato**. Quella data non e' un ornamento: senza, ogni ricostruzione a una
data passata vedrebbe bilanci che allora non erano pubblici, ed e' il
look-ahead piu' grave e meno visibile che ci sia.

## La copertura si dichiara, non si riempie

Misurato l'08/09/2026: i ricavi ci sono per 11.530 simboli, l'EPS per 9.721, il
margine lordo per **7.708** — le banche il margine lordo non lo riportano
affatto. Non e' una lacuna da tappare: e' una copertura da dire, perche' un
filtro sul margine su un titolo finanziario non torna vuoto, torna assente.
"""
import logging
import queue
import threading
from datetime import UTC, datetime

from core import freshness, registry
from core.db import db_read, db_session
from core.schema import GLOBAL_SCOPE
from core.tipi import python_puro
from data import defeatbeta

logger = logging.getLogger(__name__)

JOB_KIND = "ingestion"
JOB_LABEL = "fondamentali dell'universo"

# I passi del lavoro, per la barra: leggere, scrivere, segnare la freschezza.
PASSI_COSTRUZIONE = 3

# Quanto si aspetta che il thread consegni il proprio run_id.
ATTESA_AVVIO_S = 5.0


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _riga(record: dict, istante: str) -> tuple:
    """Una riga della tabella, coi tipi di Python e non quelli di pandas."""
    periodo = python_puro(record.get("report_date"))
    deposito = python_puro(record.get("filing_date"))
    return (
        str(record["symbol"]).upper(),
        str(periodo)[:10],
        str(record["voce"]),
        python_puro(record.get("valore")),
        str(deposito)[:10] if deposito else None,
        istante,
    )


def _scrivi(frame) -> int:
    """Riscrive la tabella per intero. Ritorna quante righe sono entrate.

    Si svuota e si riempie invece di aggiornare riga per riga: e' una vista
    derivata, e una vista che si aggiorna a pezzi puo' restare a meta' fra due
    versioni della sorgente senza che nessuno se ne accorga.
    """
    istante = _adesso()
    righe = [_riga(record, istante) for record in frame.to_dict("records")]

    with db_session() as conn:
        conn.execute("DELETE FROM universe_fondamentali")
        conn.executemany(
            "INSERT OR REPLACE INTO universe_fondamentali "
            "(symbol, report_date, voce, valore, filing_date, built_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            righe,
        )
    return len(righe)


def _costruisci(consegna: queue.Queue | None = None) -> dict:
    """Il lavoro vero: legge, scrive, segna la freschezza. Sta nel registro."""
    with registry.job(JOB_KIND, JOB_LABEL, total=PASSI_COSTRUZIONE) as lavoro:
        if consegna is not None:
            consegna.put(lavoro.run_id)

        lettura = defeatbeta.fondamentali_universo(run_id=lavoro.run_id)
        if not lettura.available:
            lavoro.advance(detail=f"non disponibili: {lettura.reason}")
            return {"scritte": 0, "reason": lettura.reason, "action": lettura.action}

        lavoro.advance(detail=f"lette {len(lettura.frame)} righe")
        scritte = _scrivi(lettura.frame)
        lavoro.advance(detail=f"scritte {scritte} righe")
        freshness.mark_fetched_global(defeatbeta.CATEGORY_FONDAMENTALI)
        lavoro.advance(detail="freschezza aggiornata")

    logger.info("[FONDAMENTALI] %d righe in tabella", scritte)
    return {"scritte": scritte, "reason": None, "action": None}


def costruisci_in_background() -> str:
    """Avvia la costruzione in un thread e ritorna il run_id.

    Come l'universo: una lettura da un minuto non puo' stare appesa a una
    richiesta HTTP, e un lavoro che non si vede non si puo' fermare.
    """
    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_costruisci, args=(consegna,),
                     name="fondamentali", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def voci_di(simbolo: str) -> dict[str, dict[str, float]]:
    """I bilanci di un titolo come `{voce: {periodo: valore}}`.

    E' la stessa forma che produce `prospetti.tabella()`, cosi' i segnali del
    rilevatore funzionano identici sia sul titolo letto uno a uno sia su quello
    preso dalla tabella dell'universo.
    """
    with db_read() as conn:
        righe = conn.execute(
            "SELECT voce, report_date, valore FROM universe_fondamentali "
            "WHERE symbol = ? AND valore IS NOT NULL",
            (simbolo.strip().upper(),),
        ).fetchall()

    voci: dict[str, dict[str, float]] = {}
    for riga in righe:
        voci.setdefault(riga["voce"], {})[riga["report_date"]] = riga["valore"]
    return voci


def depositi_di(simbolo: str) -> dict[str, tuple[str, str]]:
    """`{fine_periodo: (data_deposito, fonte)}`, nella forma che vuole il dominio.

    Solo i periodi che una data di deposito ce l'hanno davvero: per gli altri
    `publication_dates` ricade da solo sul ritardo prudente, e lo dichiara.
    """
    with db_read() as conn:
        righe = conn.execute(
            "SELECT DISTINCT report_date, filing_date FROM universe_fondamentali "
            "WHERE symbol = ? AND filing_date IS NOT NULL",
            (simbolo.strip().upper(),),
        ).fetchall()
    return {r["report_date"]: (r["filing_date"], "filing_index") for r in righe}


def stato() -> dict:
    """Quanto copre la tabella, e da quando. Mai un None muto."""
    with db_read() as conn:
        riga = conn.execute("""
            SELECT COUNT(*) AS righe,
                   COUNT(DISTINCT symbol) AS titoli,
                   MAX(built_at) AS costruita_il,
                   SUM(CASE WHEN filing_date IS NOT NULL THEN 1 ELSE 0 END) AS con_deposito
            FROM universe_fondamentali
        """).fetchone()
        per_voce = conn.execute(
            "SELECT voce, COUNT(DISTINCT symbol) AS titoli "
            "FROM universe_fondamentali WHERE valore IS NOT NULL GROUP BY voce"
        ).fetchall()

    if not riga["righe"]:
        return {"available": False, "titoli": 0,
                "reason": "i fondamentali dell'universo non sono mai stati derivati",
                "action": "premi «Deriva i fondamentali»: e' una lettura sola, "
                          "circa un minuto"}

    serve, motivo = freshness.should_fetch_global(defeatbeta.CATEGORY_FONDAMENTALI)
    return {
        "available": True,
        "righe": riga["righe"],
        "titoli": riga["titoli"],
        "costruita_il": riga["costruita_il"],
        "eta_s": freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_FONDAMENTALI),
        "da_riderivare": serve,
        "reason": motivo,
        # La copertura per voce non e' un dettaglio: il margine lordo manca a
        # migliaia di titoli — le banche non lo riportano — e un filtro sul
        # margine li' non torna vuoto, torna assente.
        "copertura": {r["voce"]: r["titoli"] for r in per_voce},
        "con_data_di_deposito": riga["con_deposito"],
    }
