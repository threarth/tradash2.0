"""
Migrazioni versionate e idempotenti.
# feat (Blocco 0): lo schema si cambia solo con uno script tracciato, mai a mano.

`run_all()` applica in ordine le migrazioni non ancora registrate in
`schema_migrations`. Ogni migrazione e' idempotente: rieseguirla non rompe
nulla.
"""
import logging

from core.db import db_session
from core.migrations import migration_v1

logger = logging.getLogger(__name__)

# Ordine di applicazione. Le nuove migrazioni si aggiungono in fondo, mai in mezzo.
MIGRATIONS = [
    migration_v1,
]


def _ensure_registry(conn) -> None:
    """Crea la tabella che tiene traccia delle migrazioni gia' applicate."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            applied_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def run_all() -> list[str]:
    """Applica le migrazioni mancanti. Ritorna i nomi di quelle applicate ora."""
    applicate: list[str] = []
    with db_session() as conn:
        _ensure_registry(conn)
        gia_fatte = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}

        for modulo in MIGRATIONS:
            if modulo.VERSION in gia_fatte:
                continue

            modulo.apply(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (modulo.VERSION, modulo.NAME),
            )
            applicate.append(modulo.NAME)
            logger.info("[MIGRAZIONE] applicata v%s (%s)", modulo.VERSION, modulo.NAME)

    return applicate
