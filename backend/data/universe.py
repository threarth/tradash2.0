"""
universe.py — l'universo dei titoli: derivato, non dichiarato.
# feat (Blocco 2): costruzione tracciata e fermabile, lettura con il motivo.

Il vecchio tradash teneva la lista dei titoli in 17 JSON statici, piu' quattro
universi virtuali e una migrazione dedicata: invecchiavano da soli e nessuno
sapeva piu' da dove venissero. Qui la lista e' una **vista ricostruibile** —
si deriva da Defeatbeta con un lavoro che si vede e si ferma, e si conserva in
SQLite perche' le domande che le si fanno ("i titoli del settore X sopra questa
capitalizzazione") sono domande da SQL su 11.256 righe.

Due cose che questo modulo dichiara invece di nascondere:

* **la costruzione e' cara la prima volta**: 214 s e circa 443 MB, perche' il
  parquet dei prezzi va letto tutto per sapere l'ultima chiusura di ogni
  titolo. Dopo, dalla cache dei byte, 7,85 s. Per questo non parte da sola
  all'apertura di una pagina (regola 2) e per questo si puo' fermare a meta';
* **la copertura non e' piena**: al 29/08/2026 manca il settore al 5,6% dei
  titoli, l'industria al 12,8%, i dipendenti al 31,7%, la capitalizzazione al
  23,4%. Quei titoli entrano lo stesso, con la casella vuota, e `stato()` dice
  quanti sono. Tenere solo le righe complete li farebbe sparire in silenzio.
"""
import logging
import queue
import threading
from datetime import UTC, datetime

import pandas as pd

import config
from core import freshness, registry
from core.db import db_read, db_session
from core.schema import GLOBAL_SCOPE
from data import defeatbeta

logger = logging.getLogger(__name__)

# Come compare nel registro dei lavori.
JOB_KIND = "universe"
JOB_LABEL = "costruzione universo"

# I passi del lavoro, per la barra di avanzamento: derivare, scrivere, marcare.
PASSI_COSTRUZIONE = 3

# Ogni quanto la sentinella controlla se e' stato chiesto lo Stop.
INTERVALLO_CONTROLLO_STOP_S = 0.25

# Quanto si aspetta che il lavoro dichiari il proprio run_id, avviandolo in un
# thread. Se scade, il chiamante ha un errore invece di un identificativo finto.
ATTESA_AVVIO_S = 5.0

# Le colonne dell'universo, nell'ordine in cui stanno in tabella.
COLONNE = (
    "symbol", "sector", "industry", "company_country", "employees",
    "shares_outstanding", "market_cap", "last_close", "last_close_date",
    "avg_volume_30d",
)

# Le colonne di cui si misura la copertura: quelle che possono mancare.
COLONNE_CON_BUCHI = (
    "sector", "industry", "company_country", "employees",
    "shares_outstanding", "market_cap", "last_close", "avg_volume_30d",
)

ACTION_UNIVERSO_VUOTO = "costruisci l'universo con POST /api/universe/build"


def _adesso() -> str:
    """Istante corrente in ISO 8601 UTC, come tutte le altre tabelle."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _pulisci(valore):
    """Da tipi pandas/numpy a tipi Python, e da 'non disponibile' a None.

    SQLite non sa cosa farsene di un `numpy.float64`, e uno STRICT lo rifiuta:
    la conversione va fatta qui, non sperando che passi.

    Una stringa vuota diventa None, e non e' un dettaglio: nel profilo di
    Defeatbeta il settore manca 635 volte come NULL e **886 volte come stringa
    vuota**. Tenendole distinte, un `IS NULL` conta 635 buchi su 1.521 e la
    copertura dichiarata risulta il doppio di quella vera — un buco silenzioso
    prodotto proprio dal codice che doveva dichiararli.
    """
    if valore is None or pd.isna(valore):
        return None
    if isinstance(valore, str):
        pulito = valore.strip()
        return pulito if pulito else None
    if hasattr(valore, "item"):
        return valore.item()
    return valore


def _riga(record: dict) -> tuple:
    """Una riga dell'universo pronta per l'INSERT, coi tipi giusti."""
    pulito = {colonna: _pulisci(record.get(colonna)) for colonna in COLONNE}
    dipendenti = pulito["employees"]
    return (
        str(pulito["symbol"]),
        pulito["sector"], pulito["industry"], pulito["company_country"],
        int(dipendenti) if dipendenti is not None else None,
        pulito["shares_outstanding"], pulito["market_cap"], pulito["last_close"],
        pulito["last_close_date"], pulito["avg_volume_30d"],
    )


def _scrivi(frame: pd.DataFrame) -> int:
    """Sostituisce l'universo in una transazione sola: o c'e' tutto, o niente.

    Regola 22: cancellare e reinserire fuori da una transazione lascerebbe, in
    caso di errore a meta', un universo dimezzato che sembra completo.
    """
    istante = _adesso()
    righe = [(*_riga(record), istante) for record in frame.to_dict("records")]

    with db_session() as conn:
        conn.execute("DELETE FROM universe")
        conn.executemany(
            f"INSERT INTO universe ({', '.join(COLONNE)}, built_at) "
            f"VALUES ({', '.join('?' * (len(COLONNE) + 1))})",
            righe,
        )
    return len(righe)


def _sorveglia_stop(lavoro, finito: threading.Event) -> None:
    """Traduce lo Stop del registro in un'interruzione della query in corso.

    La derivazione e' una query sola da minuti: spezzarla in pezzi per poterla
    fermare avrebbe voluto dire rileggere piu' volte lo stesso parquet. DuckDB
    sa interrompersi, e questa sentinella e' il filo fra il pulsante e il motore.
    """
    while not finito.wait(INTERVALLO_CONTROLLO_STOP_S):
        if lavoro.stop_requested():
            defeatbeta.interrupt()
            return


def _deriva(lavoro) -> pd.DataFrame:
    """Chiede la derivazione a Defeatbeta, restando fermabile per tutta la query."""
    finito = threading.Event()
    sentinella = threading.Thread(target=_sorveglia_stop, args=(lavoro, finito), daemon=True)
    sentinella.start()
    try:
        return defeatbeta.universe(run_id=lavoro.run_id).frame
    except defeatbeta.DefeatbetaUnavailable:
        # Una query interrotta da noi non e' un guasto del provider: e' uno stop.
        if lavoro.stop_requested():
            raise registry.JobStopped("universo: costruzione fermata su richiesta") from None
        raise
    finally:
        finito.set()


def _costruisci(force: bool, consegna: queue.Queue | None = None) -> dict:
    """Il lavoro vero e proprio. Sta dentro `registry.job`, quindi si vede e si ferma.

    Ritorna sempre un esito esplicito, anche quando viene fermato: `registry.job`
    assorbe `JobStopped` e l'esecuzione riprende dopo il blocco, dove l'esito
    conserva il motivo con cui era stato preparato (regola 17, mai un `None`
    silenzioso).
    """
    esito = {"run_id": None, "costruito": False, "titoli": 0,
             "motivo": "fermato prima di completare"}

    with registry.job(JOB_KIND, JOB_LABEL, total=PASSI_COSTRUZIONE) as lavoro:
        esito["run_id"] = lavoro.run_id
        if consegna is not None:
            consegna.put(lavoro.run_id)

        serve, motivo = freshness.should_fetch_global(defeatbeta.CATEGORY_UNIVERSE)
        if not serve and not force:
            lavoro.detail = f"saltato: {motivo}"
            logger.info("[UNIVERSO] non ricostruito — %s", motivo)
            esito["motivo"] = motivo
            return esito

        frame = _deriva(lavoro)
        lavoro.advance(detail=f"derivati {len(frame)} titoli")

        scritti = _scrivi(frame)
        lavoro.advance(detail=f"scritti {scritti} titoli")

        freshness.mark_fetched_global(defeatbeta.CATEGORY_UNIVERSE)
        lavoro.advance(detail="freschezza aggiornata")
        logger.info("[UNIVERSO] ricostruito: %d titoli", scritti)
        esito.update({"costruito": True, "titoli": scritti, "motivo": "ricostruito"})

    return esito


def build(force: bool = False) -> dict:
    """Costruisce l'universo qui e ora, aspettando che finisca."""
    return _costruisci(force)


def build_in_background(force: bool = False) -> str:
    """Avvia la costruzione in un thread e ritorna il run_id con cui fermarla.

    Serve alla route: la prima costruzione dura minuti, e una richiesta HTTP
    che resta appesa tutto quel tempo e' un'altra forma di lavoro che non si
    puo' fermare.
    """
    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(
        target=_costruisci, args=(force, consegna), name="universo", daemon=True
    ).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def _dove(sector, industry, min_market_cap, search) -> tuple[str, list]:
    """Compone i filtri come condizioni parametrizzate, mai concatenando valori."""
    condizioni: list[str] = []
    parametri: list = []

    if sector:
        condizioni.append("sector = ?")
        parametri.append(sector)
    if industry:
        condizioni.append("industry = ?")
        parametri.append(industry)
    if min_market_cap is not None:
        condizioni.append("market_cap >= ?")
        parametri.append(float(min_market_cap))
    if search:
        condizioni.append("symbol LIKE ?")
        parametri.append(f"{search.strip().upper()}%")

    return (f"WHERE {' AND '.join(condizioni)}" if condizioni else ""), parametri


def rows(sector: str | None = None, industry: str | None = None,
         min_market_cap: float | None = None, search: str | None = None,
         limit: int = config.UNIVERSE_PAGE_LIMIT_DEFAULT) -> list[dict]:
    """I titoli dell'universo, dai piu' capitalizzati. Filtri tutti facoltativi."""
    if not 1 <= limit <= config.UNIVERSE_PAGE_LIMIT_MAX:
        raise ValueError(
            f"limit deve stare fra 1 e {config.UNIVERSE_PAGE_LIMIT_MAX}, ricevuto {limit}"
        )

    dove, parametri = _dove(sector, industry, min_market_cap, search)
    with db_read() as conn:
        righe = conn.execute(
            f"SELECT * FROM universe {dove} "
            f"ORDER BY market_cap DESC NULLS LAST, symbol LIMIT ?",
            [*parametri, limit],
        ).fetchall()
    return [dict(r) for r in righe]


def _copertura(conn, totale: int) -> dict:
    """Quanti titoli hanno la casella vuota, colonna per colonna."""
    conteggi = ", ".join(
        f"SUM(CASE WHEN {colonna} IS NULL THEN 1 ELSE 0 END) AS {colonna}"
        for colonna in COLONNE_CON_BUCHI
    )
    riga = conn.execute(f"SELECT {conteggi} FROM universe").fetchone()
    return {
        colonna: {"mancanti": riga[colonna],
                  "percentuale": round(100 * riga[colonna] / totale, 1)}
        for colonna in COLONNE_CON_BUCHI
    }


def _capitalizzazione(conn) -> dict:
    """Perche' una capitalizzazione manca — che non e' la stessa cosa di "manca".

    `market_cap` e' ultima chiusura per azioni in circolazione: se manca uno dei
    due fattori il prodotto non esiste. Dire "non derivabile, mancano le azioni
    in circolazione" e' un'informazione; dire "manca al 23,4%" fa sembrare un
    guasto quello che per un ETF e' la normalita'.
    """
    riga = conn.execute(
        "SELECT COUNT(*) AS mancanti, "
        "SUM(CASE WHEN last_close IS NULL THEN 1 ELSE 0 END) AS senza_prezzo, "
        "SUM(CASE WHEN shares_outstanding IS NULL THEN 1 ELSE 0 END) AS senza_azioni "
        "FROM universe WHERE market_cap IS NULL"
    ).fetchone()
    return {
        "non_derivabile": riga["mancanti"],
        "perche_manca_il_prezzo": riga["senza_prezzo"] or 0,
        "perche_mancano_le_azioni": riga["senza_azioni"] or 0,
    }


def stato() -> dict:
    """Cosa c'e' nell'universo, quanto e' vecchio, e cosa gli manca.

    Regola 5: un universo mai costruito non e' una lista vuota, e' un `available`
    a falso con scritto perche' e cosa fare.
    """
    with db_read() as conn:
        totale = conn.execute("SELECT COUNT(*) AS n FROM universe").fetchone()["n"]
        if totale == 0:
            return {
                "available": False, "titoli": 0,
                "reason": "l'universo non e' mai stato costruito",
                "action": ACTION_UNIVERSO_VUOTO,
            }
        costruito_il = conn.execute("SELECT MAX(built_at) AS q FROM universe").fetchone()["q"]
        vecchi = conn.execute(
            "SELECT COUNT(*) AS n FROM universe "
            "WHERE last_close_date IS NULL OR last_close_date < date('now', ?)",
            (f"-{config.UNIVERSE_STALE_PRICE_DAYS} days",),
        ).fetchone()["n"]
        copertura = _copertura(conn, totale)
        capitalizzazione = _capitalizzazione(conn)

    serve, motivo = freshness.should_fetch_global(defeatbeta.CATEGORY_UNIVERSE)
    return {
        "available": True, "titoli": totale, "costruito_il": costruito_il,
        "eta_s": freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_UNIVERSE),
        "da_ricostruire": serve, "reason": motivo,
        "copertura": copertura,
        "capitalizzazione": capitalizzazione,
        "prezzo_vecchio": {"titoli": vecchi,
                           "oltre_giorni": config.UNIVERSE_STALE_PRICE_DAYS},
    }
