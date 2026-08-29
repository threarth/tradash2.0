"""
migration_v1.py — schema iniziale del Blocco 0.
# feat: le tre tabelle che rendono la regola 1 non aggirabile.

- `jobs`  : ogni lavoro batch o singolo, con il suo esito. Gestibile e fermabile.
- `calls` : ogni chiamata di rete, di cache o di API, con `source` che dice
            SEMPRE da dove e' arrivato il dato.
- `freshness` : quando una categoria di dato e' stata presa l'ultima volta,
            per simbolo. E' il gate interrogato prima di andare in rete.
"""
VERSION = 1
NAME = "schema_iniziale_osservabilita"


def apply(conn) -> None:
    """Crea le tabelle del Blocco 0. Idempotente."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            run_id       TEXT    PRIMARY KEY,
            kind         TEXT    NOT NULL,
            label        TEXT    NOT NULL,
            status       TEXT    NOT NULL,
            total        INTEGER,
            done         INTEGER NOT NULL DEFAULT 0,
            detail       TEXT,
            started_at   TEXT    NOT NULL,
            ended_at     TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status, started_at DESC)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calls (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            provider     TEXT    NOT NULL,
            endpoint     TEXT    NOT NULL,
            symbol       TEXT,
            source       TEXT    NOT NULL,
            status       TEXT    NOT NULL,
            duration_ms  INTEGER NOT NULL,
            error_msg    TEXT,
            run_id       TEXT,
            called_at    TEXT    NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_called_at ON calls (called_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_run_id ON calls (run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_source ON calls (source)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS freshness (
            symbol       TEXT    NOT NULL,
            category     TEXT    NOT NULL,
            fetched_at   TEXT    NOT NULL,
            PRIMARY KEY (symbol, category)
        )
        """
    )
