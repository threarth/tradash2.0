"""
calls.py — registro di OGNI chiamata: rete, cache, API interne.
# feat (Blocco 0): la regola 1 resa non aggirabile.

Il difetto che questo modulo esiste per impedire: nel vecchio sistema un log
che mostrava solo la rete non permetteva di distinguere "il dato e' arrivato
dalla rete" da "era in cache" — che e' esattamente la domanda a cui serve
rispondere. Qui la provenienza e' un campo obbligatorio.

Uso:
    with calls.track("defeatbeta", "stock_prices", scope="AAPL") as chiamata:
        dati = leggi_da_qualche_parte()
        chiamata.from_cache()      # oppure chiamata.from_network()

`scope` e' il titolo quando la chiamata riguarda un titolo, e resta vuoto (o
vale `schema.GLOBAL_SCOPE`) per i dati che non appartengono a nessuno: la curva
dei Treasury, la lista dell'universo.

Chi dimentica di dichiarare la provenienza non viene zittito: la riga finisce
in tabella con `source = 'undeclared'` e un ERROR nel log. Un test verifica che
non ne esistano.
"""
import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime

from core.db import db_read, db_session

logger = logging.getLogger(__name__)

# Provenienza del dato. `UNDECLARED` non e' un'opzione legittima: e' la spia
# che un percorso di codice non ha dichiarato da dove ha preso il dato.
SOURCE_NETWORK = "network"
SOURCE_CACHE = "cache"
SOURCE_LOCAL = "local"
SOURCE_UNDECLARED = "undeclared"

STATUS_OK = "ok"
STATUS_ERROR = "error"

MILLISECONDS_PER_SECOND = 1000


class Call:
    """Una chiamata in corso. Chi la usa DEVE dichiararne la provenienza."""

    def __init__(self, provider: str, endpoint: str, scope: str | None, run_id: str | None):
        self.provider = provider
        self.endpoint = endpoint
        self.scope = scope
        self.run_id = run_id
        self.source = SOURCE_UNDECLARED
        self.status = STATUS_OK
        self.error_msg: str | None = None

    def from_network(self) -> None:
        """Il dato e' stato preso dalla rete."""
        self.source = SOURCE_NETWORK

    def from_cache(self) -> None:
        """Il dato era gia' in cache: nessun byte e' uscito."""
        self.source = SOURCE_CACHE

    def from_local(self) -> None:
        """Il dato viene dal nostro database, non da un fornitore esterno."""
        self.source = SOURCE_LOCAL


def _now_iso() -> str:
    """Istante corrente in ISO 8601 UTC, il formato usato da tutte le tabelle."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _persist(chiamata: Call, duration_ms: int) -> None:
    """Scrive la riga di log. Un errore qui non deve far fallire il lavoro vero."""
    try:
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO calls (provider, endpoint, scope, source, status,
                                   duration_ms, error_msg, run_id, called_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chiamata.provider, chiamata.endpoint, chiamata.scope, chiamata.source,
                 chiamata.status, duration_ms, chiamata.error_msg, chiamata.run_id, _now_iso()),
            )
    except Exception:
        logger.exception("[CHIAMATE] impossibile registrare %s:%s",
                         chiamata.provider, chiamata.endpoint)


@contextmanager
def track(provider: str, endpoint: str, scope: str | None = None, run_id: str | None = None):
    """Registra una chiamata dall'inizio alla fine, comunque vada.

    Se il blocco solleva, la riga viene scritta ugualmente con lo stato di
    errore e l'eccezione viene rilanciata: un fallimento silenzioso e' peggio
    di un fallimento rumoroso.
    """
    chiamata = Call(provider, endpoint, scope, run_id)
    inizio = time.perf_counter()
    try:
        yield chiamata
    except Exception as exc:
        chiamata.status = STATUS_ERROR
        chiamata.error_msg = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        durata_ms = int((time.perf_counter() - inizio) * MILLISECONDS_PER_SECOND)
        # Una chiamata FALLITA resta 'undeclared' senza colpa di nessuno: il
        # dato non e' mai arrivato, quindi non c'e' una provenienza da
        # dichiarare. L'allarme suona solo quando la chiamata e' andata a buon
        # fine e nessuno ha detto da dove veniva il dato — altrimenti la spia
        # si accende a ogni errore di rete e smette di voler dire qualcosa.
        if chiamata.source == SOURCE_UNDECLARED and chiamata.status == STATUS_OK:
            logger.error("[CHIAMATE] provenienza non dichiarata per %s:%s — vedi calls.track()",
                         provider, endpoint)
        _persist(chiamata, durata_ms)


def recent(limit: int, provider: str | None = None, run_id: str | None = None) -> list[dict]:
    """Ultime chiamate registrate, dalla piu' recente. Filtri opzionali."""
    condizioni: list[str] = []
    parametri: list[object] = []

    if provider:
        condizioni.append("provider = ?")
        parametri.append(provider)
    if run_id:
        condizioni.append("run_id = ?")
        parametri.append(run_id)

    dove = f"WHERE {' AND '.join(condizioni)}" if condizioni else ""
    parametri.append(limit)

    with db_read() as conn:
        righe = conn.execute(
            f"SELECT * FROM calls {dove} ORDER BY id DESC LIMIT ?", parametri
        ).fetchall()
    return [dict(r) for r in righe]


def summary() -> dict:
    """Quante chiamate per provenienza: la risposta a 'e' arrivato dalla rete o era in cache?'."""
    with db_read() as conn:
        righe = conn.execute("SELECT source, COUNT(*) AS n FROM calls GROUP BY source").fetchall()
    return {r["source"]: r["n"] for r in righe}


def undeclared_ok() -> int:
    """Quante chiamate RIUSCITE non hanno dichiarato da dove veniva il dato.

    E' il numero che segnala un difetto nostro, e deve restare zero. Le
    chiamate fallite non ci finiscono dentro apposta: una query interrotta a
    meta' non ha una provenienza da dichiarare, e contarla qui vorrebbe dire
    tenere la spia accesa per motivi legittimi finche' nessuno la guarda piu'.
    """
    with db_read() as conn:
        riga = conn.execute(
            "SELECT COUNT(*) AS n FROM calls WHERE source = ? AND status = ?",
            (SOURCE_UNDECLARED, STATUS_OK),
        ).fetchone()
    return riga["n"]
