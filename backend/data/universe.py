"""
universe.py — l'universo dei titoli: derivato, non dichiarato.
# feat (Blocco 2): costruzione tracciata e fermabile, lettura con il motivo.

Il vecchio tradash teneva la lista dei titoli in 17 JSON statici, piu' quattro
universi virtuali e una migrazione dedicata: invecchiavano da soli e nessuno
sapeva piu' da dove venissero. Qui la lista e' una **vista ricostruibile** —
si deriva da Defeatbeta con un lavoro che si vede e si ferma, e si conserva in
SQLite perche' le domande che le si fanno ("i titoli del settore X sopra questa
capitalizzazione") sono domande da SQL su 11.256 righe.

## Due meta', non una

Era un lavoro solo, e rileggeva 540 MB per rinfrescare anche cio' che non era
cambiato. Misurato il 14/09/2026, un processo per meta', a cache calda:

    anagrafica   nome, settore, industria, paese,        95 MB    2,7 s    238 MB
                 dipendenti, azioni in circolazione
    mercato      ultima chiusura, sua data,             445 MB    6,6 s  3.076 MB
                 volume medio a 30 sedute,
                 chiusura di 252 sedute fa

La chiusura di un anno fa e' stata aggiunta il 18/09/2026 **dentro la stessa
passata**, e non con una lettura sua: il costo di questa meta' e' attraversare
36,7 milioni di righe, e una colonna in piu' presa dalla finestra gia' aperta
non aggiunge niente, mentre una seconda query lo raddoppierebbe. Serve alla
forza relativa al settore, che ha bisogno della variazione a un anno di TUTTI i
titoli insieme per farne una mediana per settore — per un titolo solo il
giornaliero si legge a richiesta, per undicimila no.

La meta' mercato e' il 99% della memoria e l'82% dello scaricamento. Adesso
sono due lavori con due freschezze: l'anagrafica ogni due settimane, il mercato
ogni giorno. Chi oggi non deve filtrare per capitalizzazione non paga i 3 GB.

Altre due cose che questo modulo dichiara invece di nascondere:

* **il mercato ha bisogno dell'anagrafica**, e se manca lo dice con il motivo e
  l'azione invece di scrivere zero righe in silenzio (regola 5). I prezzi
  coprono 12.289 simboli e l'anagrafica 11.351, ma si sovrappongono solo su
  11.283: 1.006 quotazioni non entrano perche' il titolo non ha profilo, e 68
  titoli restano senza prezzo, visibili con le caselle vuote;
* **la copertura non e' piena**: al 29/08/2026 manca il settore al 5,6% dei
  titoli, l'industria al 12,8%, i dipendenti al 31,7%, la capitalizzazione al
  23,4%. Quei titoli entrano lo stesso, con la casella vuota, e `stato()` dice
  quanti sono. Tenere solo le righe complete li farebbe sparire in silenzio.
"""
import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

import config
from core import freshness, registry
from core.db import db_read, db_session
from core.schema import GLOBAL_SCOPE
from core.tipi import python_puro
from data import defeatbeta

logger = logging.getLogger(__name__)

# Come compaiono nel registro dei lavori. Due, perche' due sono i lavori: chi
# guarda la pagina delle operazioni deve vedere QUALE meta' sta girando.
JOB_KIND_ANAGRAFICA = "universe_anagrafica"
JOB_LABEL_ANAGRAFICA = "universo: anagrafica"
JOB_KIND_MERCATO = "universe_mercato"
JOB_LABEL_MERCATO = "universo: dati di mercato"

# I passi di ogni lavoro, per la barra di avanzamento: derivare, scrivere, marcare.
PASSI_COSTRUZIONE = 3

# Ogni quanto la sentinella controlla se e' stato chiesto lo Stop.
INTERVALLO_CONTROLLO_STOP_S = 0.25

# Quanto si aspetta che il lavoro dichiari il proprio run_id, avviandolo in un
# thread. Se scade, il chiamante ha un errore invece di un identificativo finto.
ATTESA_AVVIO_S = 5.0

# Le colonne di ciascuna meta', nell'ordine in cui stanno in tabella.
COLONNE_ANAGRAFICA = (
    "symbol", "name", "sector", "industry", "company_country", "employees",
    "shares_outstanding",
)
COLONNE_MERCATO = ("symbol", "last_close", "last_close_date", "avg_volume_30d",
                   "close_1a_fa", "data_1a_fa")

# Le colonne di cui si misura la copertura: quelle che possono mancare. Sono
# della VISTA, non di una tabella, perche' e' la vista che si mostra.
COLONNE_CON_BUCHI = (
    "name", "sector", "industry", "company_country", "employees",
    "shares_outstanding", "market_cap", "last_close", "avg_volume_30d",
)

ACTION_UNIVERSO_VUOTO = "costruisci l'anagrafica con POST /api/universe/anagrafica"
MOTIVO_SENZA_ANAGRAFICA = (
    "i dati di mercato si appoggiano all'anagrafica, che non e' mai stata "
    "costruita: senza, non si saprebbe di quali titoli tenere il prezzo"
)


def _adesso() -> str:
    """Istante corrente in ISO 8601 UTC, come tutte le altre tabelle."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _riga_anagrafica(record: dict) -> tuple:
    """Una riga dell'anagrafica pronta per l'INSERT, coi tipi giusti."""
    pulito = {colonna: python_puro(record.get(colonna)) for colonna in COLONNE_ANAGRAFICA}
    dipendenti = pulito["employees"]
    return (
        str(pulito["symbol"]), pulito["name"],
        pulito["sector"], pulito["industry"], pulito["company_country"],
        int(dipendenti) if dipendenti is not None else None,
        pulito["shares_outstanding"],
    )


def _riga_mercato(record: dict) -> tuple:
    """Una riga dei dati di mercato pronta per l'INSERT, coi tipi giusti."""
    pulito = {colonna: python_puro(record.get(colonna)) for colonna in COLONNE_MERCATO}
    return (str(pulito["symbol"]), pulito["last_close"],
            pulito["last_close_date"], pulito["avg_volume_30d"],
            pulito["close_1a_fa"], pulito["data_1a_fa"])


def _insert(tabella: str, colonne: tuple[str, ...]) -> str:
    """L'INSERT di una delle due meta'. I nomi vengono da qui, mai da fuori."""
    segnaposti = ", ".join("?" * (len(colonne) + 1))
    return (f"INSERT INTO {tabella} ({', '.join(colonne)}, built_at) "
            f"VALUES ({segnaposti})")


def _scrivi_anagrafica(frame: pd.DataFrame) -> dict:
    """Aggiorna l'anagrafica, conservando i prezzi dei titoli che restano.

    NON e' un DELETE seguito da un INSERT, e la differenza conta: la chiave di
    `universe_mercato` punta qui con ON DELETE CASCADE, quindi svuotare la
    tabella cancellerebbe anche tutti i prezzi. Ogni due settimane si
    resterebbe senza dati di mercato fino al giorno dopo.

    Quindi: si aggiorna chi c'e', si aggiunge chi e' nuovo, e si cancella solo
    chi e' davvero sparito dal dataset — e per quelli il prezzo se ne va con
    loro, che e' giusto.
    """
    istante = _adesso()
    righe = [(*_riga_anagrafica(record), istante) for record in frame.to_dict("records")]
    aggiornamenti = ", ".join(f"{c} = excluded.{c}" for c in COLONNE_ANAGRAFICA[1:])

    with db_session() as conn:
        conn.executemany(
            f"{_insert('universe_anagrafica', COLONNE_ANAGRAFICA)} "
            f"ON CONFLICT (symbol) DO UPDATE SET {aggiornamenti}, built_at = excluded.built_at",
            righe,
        )
        spariti = _cancella_spariti(conn, [r[0] for r in righe])

    return {"scritti": len(righe), "spariti": spariti}


def _cancella_spariti(conn, simboli: list[str]) -> int:
    """Toglie dall'anagrafica i titoli che il dataset non elenca piu'.

    Passa da una tabella temporanea invece che da un `NOT IN (?, ?, ...)` con
    undicimila segnaposti: SQLite un tetto al numero di variabili ce l'ha, e
    costruirci contro un elenco che cresce col dataset e' un guasto rimandato.
    """
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS simboli_vivi (symbol TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM simboli_vivi")
    conn.executemany("INSERT OR IGNORE INTO simboli_vivi (symbol) VALUES (?)",
                     [(s,) for s in simboli])
    cursore = conn.execute(
        "DELETE FROM universe_anagrafica "
        "WHERE symbol NOT IN (SELECT symbol FROM simboli_vivi)"
    )
    return cursore.rowcount


def _scrivi_mercato(frame: pd.DataFrame) -> dict:
    """Sostituisce i dati di mercato in una transazione sola (regola 22).

    Qui il DELETE totale va bene: nessuno punta a questa tabella, e i prezzi o
    ci sono tutti della stessa lettura o non ci sono.

    Si tengono solo i simboli che hanno un'anagrafica. Gli altri — 1.006 alla
    ricostruzione del 14/09/2026 — non sono un errore: sono titoli che Defeatbeta
    quota ma di cui non pubblica il profilo, e conservarne il prezzo vorrebbe
    dire una riga che nessuna pagina mostrera' mai.
    """
    noti = _simboli_anagrafica()
    istante = _adesso()
    tutti = frame.to_dict("records")
    righe = [(*_riga_mercato(record), istante) for record in tutti
             if str(python_puro(record.get("symbol"))) in noti]

    with db_session() as conn:
        conn.execute("DELETE FROM universe_mercato")
        conn.executemany(_insert("universe_mercato", COLONNE_MERCATO), righe)

    return {"scritti": len(righe), "senza_anagrafica": len(tutti) - len(righe)}


def _simboli_anagrafica() -> set[str]:
    """I simboli che hanno un'anagrafica. Vuoto significa: non costruita."""
    with db_read() as conn:
        return {r["symbol"] for r in
                conn.execute("SELECT symbol FROM universe_anagrafica").fetchall()}


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


@dataclass(frozen=True)
class _Meta:
    """Una delle due meta' dell'universo: come si chiama, cosa legge, dove scrive.

    Esiste per non scrivere due volte lo stesso lavoro: i passi sono identici —
    guarda la freschezza, deriva restando fermabile, scrivi, marca — e cambiano
    soltanto il nome, la categoria, la lettura e la scrittura (regola 19).
    """

    kind: str
    label: str
    category: str
    leggi: Callable[..., object]
    scrivi: Callable[[pd.DataFrame], dict]
    # Cosa impedisce a questo lavoro di partire, o None se niente lo impedisce.
    impedimento: Callable[[], str | None]


def _niente_impedisce() -> str | None:
    """L'anagrafica non dipende da nessuno: puo' sempre partire."""
    return None


def _serve_anagrafica() -> str | None:
    """Il mercato senza anagrafica non saprebbe di chi tenere il prezzo."""
    return None if _simboli_anagrafica() else MOTIVO_SENZA_ANAGRAFICA


# Le due letture si chiamano attraverso una delega invece di finire dentro
# `_Meta` come riferimento diretto. Non e' cerimonia: un riferimento preso qui
# resterebbe quello del momento dell'import, e chi sostituisce la lettura per
# misurare il resto della catena si ritroverebbe la funzione vera lo stesso.
def _leggi_anagrafica(run_id: str | None = None):
    """Chiede l'anagrafica al punto unico di accesso a Defeatbeta."""
    return defeatbeta.anagrafica_universo(run_id=run_id)


def _leggi_mercato(run_id: str | None = None):
    """Chiede i dati di mercato al punto unico di accesso a Defeatbeta."""
    return defeatbeta.mercato_universo(run_id=run_id)


ANAGRAFICA = _Meta(
    kind=JOB_KIND_ANAGRAFICA, label=JOB_LABEL_ANAGRAFICA,
    category=defeatbeta.CATEGORY_ANAGRAFICA,
    leggi=_leggi_anagrafica, scrivi=_scrivi_anagrafica,
    impedimento=_niente_impedisce,
)

MERCATO = _Meta(
    kind=JOB_KIND_MERCATO, label=JOB_LABEL_MERCATO,
    category=defeatbeta.CATEGORY_MERCATO,
    leggi=_leggi_mercato, scrivi=_scrivi_mercato,
    impedimento=_serve_anagrafica,
)

META_PER_NOME = {"anagrafica": ANAGRAFICA, "mercato": MERCATO}


def _deriva(lavoro, meta: _Meta) -> pd.DataFrame:
    """Chiede la derivazione a Defeatbeta, restando fermabile per tutta la query."""
    finito = threading.Event()
    sentinella = threading.Thread(target=_sorveglia_stop, args=(lavoro, finito), daemon=True)
    sentinella.start()
    try:
        return meta.leggi(run_id=lavoro.run_id).frame
    except defeatbeta.DefeatbetaUnavailable:
        # Una query interrotta da noi non e' un guasto del provider: e' uno stop.
        if lavoro.stop_requested():
            raise registry.JobStopped(f"{meta.label}: costruzione fermata su richiesta") from None
        raise
    finally:
        finito.set()


def _costruisci(meta: _Meta, force: bool, consegna: queue.Queue | None = None) -> dict:
    """Il lavoro vero e proprio. Sta dentro `registry.job`, quindi si vede e si ferma.

    Ritorna sempre un esito esplicito, anche quando viene fermato: `registry.job`
    assorbe `JobStopped` e l'esecuzione riprende dopo il blocco, dove l'esito
    conserva il motivo con cui era stato preparato (regola 17, mai un `None`
    silenzioso).
    """
    esito = {"run_id": None, "meta": meta.kind, "costruito": False, "titoli": 0,
             "motivo": "fermato prima di completare"}

    with registry.job(meta.kind, meta.label, total=PASSI_COSTRUZIONE) as lavoro:
        esito["run_id"] = lavoro.run_id
        if consegna is not None:
            consegna.put(lavoro.run_id)

        impedimento = meta.impedimento()
        if impedimento:
            lavoro.detail = impedimento
            logger.warning("[UNIVERSO] %s non parte — %s", meta.kind, impedimento)
            esito.update({"motivo": impedimento, "action": ACTION_UNIVERSO_VUOTO})
            return esito

        serve, motivo = freshness.should_fetch_global(meta.category)
        if not serve and not force:
            lavoro.detail = f"saltato: {motivo}"
            logger.info("[UNIVERSO] %s non ricostruita — %s", meta.kind, motivo)
            esito["motivo"] = motivo
            return esito

        frame = _deriva(lavoro, meta)
        lavoro.advance(detail=f"derivate {len(frame)} righe")

        scritto = meta.scrivi(frame)
        lavoro.advance(detail=f"scritti {scritto['scritti']} titoli")

        freshness.mark_fetched_global(meta.category)
        lavoro.advance(detail="freschezza aggiornata")
        logger.info("[UNIVERSO] %s ricostruita: %s", meta.kind, scritto)
        esito.update({"costruito": True, "titoli": scritto["scritti"],
                      "motivo": "ricostruita", **scritto})

    return esito


def build_anagrafica(force: bool = False) -> dict:
    """Costruisce l'anagrafica qui e ora, aspettando che finisca."""
    return _costruisci(ANAGRAFICA, force)


def build_mercato(force: bool = False) -> dict:
    """Costruisce i dati di mercato qui e ora, aspettando che finisca."""
    return _costruisci(MERCATO, force)


def build_in_background(quale: str, force: bool = False) -> str:
    """Avvia una delle due meta' in un thread e ritorna il run_id per fermarla.

    Serve alla route: il mercato dura minuti la prima volta, e una richiesta
    HTTP che resta appesa tutto quel tempo e' un'altra forma di lavoro che non
    si puo' fermare.
    """
    meta = META_PER_NOME[quale]
    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(
        target=_costruisci, args=(meta, force, consegna),
        name=f"universo-{quale}", daemon=True,
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
        # Si cerca nel simbolo E nel nome: chi cerca "nvidia" non sta cercando
        # un ticker, e chi cerca "NVDA" non sta scrivendo un nome. Il simbolo
        # dall'inizio, il nome ovunque — "Corporation" non aiuta nessuno a
        # trovare NVIDIA, ma "vidia" si'.
        cercato = search.strip()
        condizioni.append("(symbol LIKE ? OR name LIKE ? COLLATE NOCASE)")
        parametri.extend([f"{cercato.upper()}%", f"%{cercato}%"])

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


def riga(simbolo: str) -> dict | None:
    """Cio' che l'universo sa di UN titolo, o None se non lo conosce.

    Serve all'anteprima che compare passando il mouse su un simbolo: e' una
    lettura da una tabella locale, non da Defeatbeta, quindi costa quanto una
    query per chiave e si puo' fare al volo mentre si scorre un elenco.
    """
    with db_read() as conn:
        trovata = conn.execute(
            "SELECT * FROM universe WHERE symbol = ?", (simbolo.strip().upper(),)
        ).fetchone()
    return dict(trovata) if trovata else None


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


def _eta(meta: _Meta, costruita_il: str | None) -> dict:
    """L'eta' di UNA meta': quando e' stata costruita e se e' ora di rifarla.

    Sta a parte perche' adesso ce ne sono due, e la regola 3 vuole che ognuna
    risponda per se': dire "l'universo e' fresco" quando il settore e' di due
    settimane fa e il prezzo di stanotte sarebbe una media fra due verita'.
    """
    serve, motivo = freshness.should_fetch_global(meta.category)
    return {
        "costruita_il": costruita_il,
        "eta_s": freshness.age_seconds(GLOBAL_SCOPE, meta.category),
        "da_ricostruire": serve,
        "reason": motivo,
    }


def _prezzi_vecchi(conn) -> int:
    """Quanti titoli mostrano una chiusura piu' vecchia della soglia."""
    return conn.execute(
        "SELECT COUNT(*) AS n FROM universe "
        "WHERE last_close_date IS NULL OR last_close_date < date('now', ?)",
        (f"-{config.UNIVERSE_STALE_PRICE_DAYS} days",),
    ).fetchone()["n"]


def stato() -> dict:
    """Cosa c'e' nell'universo, quanto e' vecchia OGNI META', e cosa gli manca.

    Regola 5: un universo mai costruito non e' una lista vuota, e' un `available`
    a falso con scritto perche' e cosa fare.

    Le due eta' restano separate fino in fondo, anche nella risposta: sono due
    lavori distinti e chi guarda deve poter vedere che l'anagrafica e' a posto
    mentre i prezzi sono di ieri — che e' esattamente il caso normale.
    """
    with db_read() as conn:
        totale = conn.execute("SELECT COUNT(*) AS n FROM universe_anagrafica").fetchone()["n"]
        if totale == 0:
            return {
                "available": False, "titoli": 0,
                "reason": "l'anagrafica dell'universo non e' mai stata costruita",
                "action": ACTION_UNIVERSO_VUOTO,
            }
        con_prezzo = conn.execute("SELECT COUNT(*) AS n FROM universe_mercato").fetchone()["n"]
        date = conn.execute(
            "SELECT (SELECT MAX(built_at) FROM universe_anagrafica) AS anagrafica, "
            "       (SELECT MAX(built_at) FROM universe_mercato)    AS mercato"
        ).fetchone()
        vecchi = _prezzi_vecchi(conn)
        copertura = _copertura(conn, totale)
        capitalizzazione = _capitalizzazione(conn)

    return {
        "available": True,
        "titoli": totale,
        "titoli_con_prezzo": con_prezzo,
        "anagrafica": _eta(ANAGRAFICA, date["anagrafica"]),
        "mercato": {**_eta(MERCATO, date["mercato"]), "titoli": con_prezzo},
        "copertura": copertura,
        "capitalizzazione": capitalizzazione,
        "prezzo_vecchio": {"titoli": vecchi,
                           "oltre_giorni": config.UNIVERSE_STALE_PRICE_DAYS},
    }
