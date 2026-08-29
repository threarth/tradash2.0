-- schema.sql — lo schema completo di tradash2.0, dichiarato in un posto solo.
-- feat (Blocco 0, rivisto): niente migrazioni. Questo file E' lo schema.
--
-- Il vecchio tradash aveva 109 migrazioni versionate. Servono quando c'e' un
-- database in produzione che non si puo' perdere; qui il database e' una vista
-- ricostruibile, quindi si dichiara lo schema e basta. Aggiungere una tabella
-- significa scrivere il CREATE qui sotto: al prossimo avvio c'e'.
--
-- Tre scelte trasversali:
--   * STRICT   — SQLite applica davvero i tipi. Senza, una stringa entra in una
--                colonna INTEGER senza un lamento.
--   * CHECK    — le colonne con valori enumerati li elencano. Uno stato
--                inventato non entra in tabella, invece di comparire in un
--                grafico sei mesi dopo.
--   * "scope"  — non "symbol": non tutto e' per titolo. La curva dei Treasury e
--                la lista dell'universo sono globali, e una chiave che inizia
--                per '@' non puo' collidere con un ticker.

-- ---------------------------------------------------------------------------
-- OSSERVABILITA' — le tabelle che rendono la regola 1 non aggirabile
-- ---------------------------------------------------------------------------

-- Ogni lavoro batch o singolo. Chi non e' qui dentro non si puo' fermare.
CREATE TABLE IF NOT EXISTS jobs (
    run_id      TEXT    NOT NULL PRIMARY KEY,
    kind        TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN ('running', 'done', 'stopped', 'failed')),
    total       INTEGER          CHECK (total IS NULL OR total >= 0),
    done        INTEGER NOT NULL DEFAULT 0 CHECK (done >= 0),
    detail      TEXT,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status, started_at DESC);

-- Ogni chiamata: rete, cache, database locale. `source` non e' opzionale:
-- distinguere "arrivato dalla rete" da "era in cache" e' la domanda per cui
-- questa tabella esiste. 'undeclared' e' ammesso apposta, per rendere VISIBILE
-- chi ha dimenticato di dichiararlo invece di lasciare la riga fuori dal log.
CREATE TABLE IF NOT EXISTS calls (
    id          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    provider    TEXT    NOT NULL,
    endpoint    TEXT    NOT NULL,
    scope       TEXT,
    source      TEXT    NOT NULL CHECK (source IN ('network', 'cache', 'local', 'undeclared')),
    status      TEXT    NOT NULL CHECK (status IN ('ok', 'error')),
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    error_msg   TEXT,
    run_id      TEXT             REFERENCES jobs (run_id) ON DELETE SET NULL,
    called_at   TEXT    NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_calls_called_at ON calls (called_at DESC);
CREATE INDEX IF NOT EXISTS idx_calls_run_id    ON calls (run_id);
CREATE INDEX IF NOT EXISTS idx_calls_source    ON calls (source);

-- Quando una categoria di dato e' stata presa l'ultima volta. E' il gate
-- interrogato PRIMA di andare in rete, e si chiede per (ambito, categoria):
-- il prezzo di AAPL e il profilo di AAPL invecchiano a velocita' diverse.
CREATE TABLE IF NOT EXISTS freshness (
    scope       TEXT NOT NULL,
    category    TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (scope, category)
) STRICT;
