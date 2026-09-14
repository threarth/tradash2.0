"""
schema.py — applica lo schema dichiarato in schema.sql.
# feat (Blocco 0, rivisto): niente migrazioni, un solo file di schema.

`ensure_schema()` gira a ogni avvio ed e' idempotente: tutte le istruzioni in
schema.sql sono `IF NOT EXISTS`, quindi su un database gia' a posto non fa
nulla e non costa niente.

`rebuild()` invece e' distruttivo e serve durante lo sviluppo: cancella le
tabelle e le ricrea. Non viene mai chiamato in automatico — solo da `manage.py`
e solo dopo una conferma battuta a mano.
"""
import logging
import sqlite3
from pathlib import Path

from core.db import db_read, db_session

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Ambito da usare per i dati che non appartengono a un titolo: la curva dei
# Treasury, la lista dell'universo. Il prefisso '@' non puo' essere un ticker.
GLOBAL_SCOPE = "@global"


def _schema_sql() -> str:
    """Legge lo schema dal file. Un errore qui deve fermare l'avvio, non passare."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema non trovato: {SCHEMA_PATH}")
    return SCHEMA_PATH.read_text(encoding="utf-8")


class SchemaDaRicostruire(RuntimeError):
    """Lo schema dichiarato non combacia con le tabelle che esistono.

    Qui non ci sono migrazioni per scelta: quando una tabella cambia forma —
    una colonna rinominata, una aggiunta — la procedura e' ricostruire il
    database, che e' una vista. Questo errore esiste per dirlo con parole
    proprie invece di lasciare passare un messaggio di SQLite che nomina una
    colonna e non spiega cosa farne.
    """


def ensure_schema() -> None:
    """Applica lo schema. Idempotente: si puo' chiamare a ogni avvio."""
    try:
        with db_session() as conn:
            conn.executescript(_schema_sql())
    except sqlite3.OperationalError as exc:
        raise SchemaDaRicostruire(
            f"lo schema in {SCHEMA_PATH.name} non combacia con il database "
            f"({exc}). Qui non ci sono migrazioni: ricostruisci con "
            f"`python manage.py rebuild`. La watchlist non si perde, sta in un file."
        ) from exc
    logger.info("[SCHEMA] applicato da %s", SCHEMA_PATH.name)


def tables() -> list[str]:
    """Le tabelle esistenti adesso nel database, in ordine alfabetico.

    Solo tabelle: le viste stanno in `views()`. Chi conta le righe di ogni
    tabella non deve ritrovarsi a contare due volte le stesse, una dalla
    tabella e una dalla vista che ci sta sopra.
    """
    return _oggetti_di_tipo("table")


def views() -> list[str]:
    """Le viste esistenti adesso nel database, in ordine alfabetico.

    Esistono da quando `universe` e' diventata l'unione di due tabelle che si
    rinfrescano a ritmi diversi. Il motivo per cui questa funzione c'e' e' che
    `rebuild()` cancellava solo cio' che `tables()` elencava: una vista sarebbe
    rimasta in piedi a puntare tabelle appena distrutte, e il guasto sarebbe
    comparso alla prima interrogazione invece che qui.
    """
    return _oggetti_di_tipo("view")


def _oggetti_di_tipo(tipo: str) -> list[str]:
    """I nomi degli oggetti di un tipo, saltando quelli interni di SQLite."""
    with db_read() as conn:
        righe = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ? "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name",
            (tipo,),
        ).fetchall()
    return [r["name"] for r in righe]


def rebuild(confirmed: bool = False) -> list[str]:
    """DISTRUTTIVO: cancella tutte le tabelle e le ricrea da schema.sql.

    Richiede `confirmed=True`: un'operazione che perde dati non deve poter
    partire per sbaglio da una chiamata dimenticata. Ritorna le tabelle
    cancellate.
    """
    if not confirmed:
        raise ValueError("rebuild() cancella tutti i dati: chiamalo con confirmed=True")

    viste = views()
    da_cancellare = tables()
    with db_session() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        # Prima le viste: una vista che sopravvive alle tabelle su cui poggia
        # non da' errore adesso, lo da' alla prima lettura — e li' sembra un
        # guasto dei dati invece che una ricostruzione lasciata a meta'.
        for vista in viste:
            conn.execute(f"DROP VIEW IF EXISTS {vista}")
        for tabella in da_cancellare:
            conn.execute(f"DROP TABLE IF EXISTS {tabella}")
        conn.executescript(_schema_sql())

    logger.warning("[SCHEMA] database ricostruito, cancellate %d tabelle (%s) "
                   "e %d viste (%s)",
                   len(da_cancellare), ", ".join(da_cancellare) or "nessuna",
                   len(viste), ", ".join(viste) or "nessuna")
    return da_cancellare
