"""
fondamentali.py — i bilanci e lo storico mensile di TUTTO l'universo.
# feat: lo screening smette di essere solo di prezzo, e diventa rigiocabile.

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

## E la seconda tabella: le chiusure di fine mese

Sta qui e non altrove perche' e' la stessa idea applicata ai prezzi: **una
lettura globale al posto di undicimila letture per titolo**. Serve a rigiocare
un criterio all'indietro — «se lo avessi acceso ogni mese degli ultimi anni,
cosa avrebbe trovato, e come sarebbe andata?» — e senza di lei quel rigioco
sarebbe un lavoro da ore.

Mensile e non giornaliera: un rigioco guarda i mesi, e la giornaliera sarebbe
venti volte piu' grande per una precisione che nessuno userebbe.

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


# --- la seconda derivazione: le chiusure di fine mese ------------------------

JOB_LABEL_PREZZI = "storico mensile dell'universo"


def _scrivi_prezzi(frame) -> int:
    """Riscrive lo storico mensile per intero. Come i bilanci: si svuota e si
    riempie, perche' una vista aggiornata a pezzi puo' restare a meta' fra due
    versioni della sorgente senza che nessuno se ne accorga."""
    istante = _adesso()
    righe = [(str(r["symbol"]).upper(), str(r["mese"]),
              float(python_puro(r["chiusura"])), istante)
             for r in frame.to_dict("records")
             if python_puro(r.get("chiusura")) is not None]

    with db_session() as conn:
        conn.execute("DELETE FROM universe_prezzi_mensili")
        conn.executemany(
            "INSERT OR REPLACE INTO universe_prezzi_mensili "
            "(symbol, mese, chiusura, built_at) VALUES (?, ?, ?, ?)",
            righe,
        )
    return len(righe)


def _costruisci_prezzi(consegna: queue.Queue | None = None) -> dict:
    """Legge e scrive lo storico mensile. Sta nel registro, si ferma."""
    with registry.job(JOB_KIND, JOB_LABEL_PREZZI, total=PASSI_COSTRUZIONE) as lavoro:
        if consegna is not None:
            consegna.put(lavoro.run_id)

        lettura = defeatbeta.prezzi_mensili_universo(run_id=lavoro.run_id)
        if not lettura.available:
            lavoro.advance(detail=f"non disponibile: {lettura.reason}")
            return {"scritte": 0, "reason": lettura.reason, "action": lettura.action}

        lavoro.advance(detail=f"lette {len(lettura.frame)} chiusure")
        scritte = _scrivi_prezzi(lettura.frame)
        lavoro.advance(detail=f"scritte {scritte} chiusure")
        freshness.mark_fetched_global(defeatbeta.CATEGORY_PREZZI_MENSILI)
        lavoro.advance(detail="freschezza aggiornata")

    logger.info("[FONDAMENTALI] storico mensile: %d righe", scritte)
    return {"scritte": scritte, "reason": None, "action": None}


def costruisci_prezzi_in_background() -> str:
    """Avvia la derivazione dello storico mensile e ritorna il run_id."""
    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_costruisci_prezzi, args=(consegna,),
                     name="prezzi-mensili", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def chiusure_mensili(simboli: list[str] | None = None) -> dict[str, dict[str, float]]:
    """`{simbolo: {mese: chiusura}}`. Senza elenco, tutto l'universo.

    Si legge in blocco perche' chi rigioca ha bisogno di tutti insieme: una
    query per titolo sarebbe la N+1 che rende lento un lavoro che dev'essere
    aritmetica locale.
    """
    with db_read() as conn:
        if simboli:
            segnaposti = ", ".join("?" for _ in simboli)
            righe = conn.execute(
                f"SELECT symbol, mese, chiusura FROM universe_prezzi_mensili "
                f"WHERE symbol IN ({segnaposti}) ORDER BY symbol, mese",
                [s.strip().upper() for s in simboli],
            ).fetchall()
        else:
            righe = conn.execute(
                "SELECT symbol, mese, chiusura FROM universe_prezzi_mensili "
                "ORDER BY symbol, mese"
            ).fetchall()

    per_simbolo: dict[str, dict[str, float]] = {}
    for riga in righe:
        per_simbolo.setdefault(riga["symbol"], {})[riga["mese"]] = riga["chiusura"]
    return per_simbolo


def stato_prezzi() -> dict:
    """Quanto copre lo storico mensile, e da quando."""
    with db_read() as conn:
        riga = conn.execute(
            "SELECT COUNT(*) AS righe, COUNT(DISTINCT symbol) AS titoli, "
            "MIN(mese) AS dal, MAX(mese) AS al, MAX(built_at) AS costruito_il "
            "FROM universe_prezzi_mensili"
        ).fetchone()

    if not riga["righe"]:
        return {"available": False, "titoli": 0,
                "reason": "lo storico mensile non e' mai stato derivato",
                "action": "premi «Deriva lo storico»: e' una lettura sola, "
                          "circa un minuto"}

    serve, motivo = freshness.should_fetch_global(defeatbeta.CATEGORY_PREZZI_MENSILI)
    return {"available": True, "righe": riga["righe"], "titoli": riga["titoli"],
            "dal": riga["dal"], "al": riga["al"],
            "costruito_il": riga["costruito_il"],
            "da_riderivare": serve, "reason": motivo}
