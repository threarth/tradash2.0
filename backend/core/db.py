"""
db.py — accesso a SQLite con transazione esplicita.
# feat (Blocco 0): unico punto di connessione al database.

Ogni scrittura passa da `db_session()`, che apre una transazione e fa rollback
se qualcosa solleva. Nessun percorso di codice apre connessioni per conto suo.
"""
import logging
import sqlite3
from contextlib import contextmanager

import config

logger = logging.getLogger(__name__)


def connect() -> sqlite3.Connection:
    """Apre una connessione con le impostazioni standard del progetto.

    `row_factory` a `sqlite3.Row` per leggere le colonne per nome; chiavi
    esterne attive, perche' un vincolo dichiarato e non applicato e' peggio di
    un vincolo assente.
    """
    conn = sqlite3.connect(
        config.DB_PATH,
        timeout=config.SQLITE_TIMEOUT_S,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session():
    """Transazione esplicita: commit se tutto va bene, rollback se solleva.

    Uso:
        with db_session() as conn:
            conn.execute("INSERT INTO ...", (...))
    """
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("[DB] transazione annullata, rollback eseguito")
        raise
    finally:
        conn.close()


@contextmanager
def db_read():
    """Connessione di sola lettura: nessun commit, nessuna transazione da chiudere."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
