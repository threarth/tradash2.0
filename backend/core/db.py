"""
db.py — accesso a SQLite con transazione esplicita.
# feat (Blocco 0): unico punto di connessione al database.

Ogni scrittura passa da `db_session()`, che apre una transazione e fa rollback
se qualcosa solleva. Nessun percorso di codice apre connessioni per conto suo.

Il database sta in modalita' WAL: senza, il server che tiene il file aperto
blocca `manage.py check` lanciato da un altro terminale. Verificato con due
processi in parallelo — in WAL il secondo scrive, fuori da WAL aspetta e scade.
"""
import logging
import os
import sqlite3
from contextlib import contextmanager

import config

logger = logging.getLogger(__name__)

# Variabile che pytest valorizza durante ogni test. Serve solo a riconoscere
# che stiamo girando dentro la suite: nessun ramo di comportamento dipende da
# lei, solo il rifiuto qui sotto.
PYTEST_MARKER_ENV = "PYTEST_CURRENT_TEST"


def _refuse_production_db_under_test() -> None:
    """Impedisce alla suite di aprire il database dell'uso reale.

    Il difetto che questo controllo esiste per impedire: la vecchia suite
    scriveva sul database vero e ne ha cancellato dati reali. La difesa non
    puo' essere l'attenzione di chi scrive il prossimo test.
    """
    if PYTEST_MARKER_ENV not in os.environ:
        return
    if config.DB_PATH == config.PRODUCTION_DB_PATH:
        raise RuntimeError(
            f"la suite sta cercando di aprire il database dell'uso reale "
            f"({config.PRODUCTION_DB_PATH}). Imposta TRADASH2_DB su un file "
            f"temporaneo prima di importare config."
        )


def connect() -> sqlite3.Connection:
    """Apre una connessione con le impostazioni standard del progetto.

    `row_factory` a `sqlite3.Row` per leggere le colonne per nome; chiavi
    esterne attive, perche' un vincolo dichiarato e non applicato e' peggio di
    un vincolo assente; WAL per non bloccare chi legge mentre qualcuno scrive.

    `synchronous = NORMAL` e' l'accoppiata consigliata con WAL: al peggio si
    perdono le ultime scritture in caso di spegnimento brutale della macchina,
    e qui le ultime scritture sono righe di log ricostruibili.
    """
    _refuse_production_db_under_test()
    conn = sqlite3.connect(
        config.DB_PATH,
        timeout=config.SQLITE_TIMEOUT_S,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
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
