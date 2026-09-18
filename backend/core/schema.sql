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

-- ---------------------------------------------------------------------------
-- UNIVERSO — la lista dei titoli, derivata e non dichiarata
-- ---------------------------------------------------------------------------

-- L'elenco dei titoli con cui si puo' lavorare, derivato da Defeatbeta e non
-- da JSON statici: il vecchio tradash ne aveva 17, piu' quattro universi
-- virtuali e una migrazione dedicata, e invecchiavano da soli. Qui e' una
-- vista ricostruibile: si cancella e si rifa' con un lavoro tracciato.
--
-- Sta in SQLite e non si rilegge dai parquet a ogni domanda perche' le domande
-- sono "dammi i titoli del settore X sopra questa capitalizzazione", e su
-- 11.000 righe SQLite risponde in millisecondi mentre la derivazione richiede
-- di rileggere per intero il parquet dei prezzi.
--
-- ## Perche' sono DUE tabelle e non una
--
-- Erano una sola, e le sue colonne invecchiavano a velocita' diverse di tre
-- ordini di grandezza: `sector` cambia quasi mai, `last_close` ogni giorno. Con
-- un solo `built_at` ricevevano lo stesso verdetto di freschezza — che e'
-- proprio cio' che la regola 3 vieta, ed e' la famiglia del difetto che mostro'
-- SNDK a 1782 quando valeva 1487.
--
-- Misurato il 14/09/2026, un processo per meta', a cache calda:
--
--   anagrafica (profilo, azioni, calendario, nomi)    95 MB     2,7 s    238 MB
--   mercato    (solo il parquet dei prezzi)          445 MB     6,6 s  3.076 MB
--
-- La meta' mercato e' il 99% della memoria e l'82% dello scaricamento. Tenerle
-- insieme voleva dire pagare tutto ogni volta per rinfrescare quattro colonne
-- su undici.
--
-- I campi che possono mancare restano NULL e si contano: un titolo senza
-- prezzo entra ugualmente nell'universo, e quanti ne siano si dichiara
-- (regola 5), invece di far sparire le righe scomode.

-- Le sette colonne che cambiano di rado. Si ricostruisce ogni due settimane e
-- non tocca il parquet dei prezzi.
CREATE TABLE IF NOT EXISTS universe_anagrafica (
    symbol             TEXT NOT NULL PRIMARY KEY,
    -- Il nome della societa'. Il vecchio tradash lo dava per irrecuperabile da
    -- Defeatbeta, e aveva guardato solo `stock_profile`, che infatti non ce
    -- l'ha: sta nel calendario degli utili e nell'indice dei depositi, e
    -- unendoli si copre il 91,4% dell'universo (10.289 titoli su 11.256).
    name               TEXT,
    sector             TEXT,
    industry           TEXT,
    -- Il paese della SOCIETA', non della borsa: BABA risulta 'China' e SHOP
    -- 'Canada' pur essendo quotate negli USA. Si chiama cosi' perche' un
    -- domani nessuno ci scriva sopra un filtro "solo mercato americano":
    -- butterebbe via 3.783 titoli quotati negli USA.
    company_country    TEXT,
    employees          INTEGER  CHECK (employees IS NULL OR employees >= 0),
    -- Le azioni in circolazione si conservano invece di essere consumate nel
    -- prodotto: sono la ragione per cui una capitalizzazione manca. Senza di
    -- loro `market_cap` non e' "assente", e' NON DERIVABILE — e sono due cose
    -- diverse da dire a chi guarda. Stanno qui e non fra i dati di mercato
    -- perche' cambiano a trimestre: misurata una mediana di 102 date per
    -- titolo dal 1984.
    shares_outstanding REAL     CHECK (shares_outstanding IS NULL OR shares_outstanding >= 0),
    built_at           TEXT NOT NULL
) STRICT;

-- Le quattro colonne che cambiano ogni giorno. Legge SOLO il parquet dei
-- prezzi, ed e' l'unica meta' che costa.
--
-- Contiene esclusivamente i simboli che stanno gia' in `universe_anagrafica`.
-- Misurato il 14/09/2026 sulla ricostruzione vera: i prezzi coprono 12.289
-- simboli, l'anagrafica 11.351, e i due insiemi si sovrappongono su 11.283.
-- Quindi 1.006 quotazioni restano fuori — titoli che Defeatbeta quota ma di cui
-- non pubblica il profilo — e 68 titoli hanno anagrafica e nessun prezzo: quelli
-- restano visibili con le caselle vuote, che e' la regola 5.
--
-- Il numero da NON usare e' la differenza fra i due totali (938): sembra la
-- risposta e non lo e', perche' i due insiemi non sono uno dentro l'altro.
-- Quanti 8-K ha depositato ogni titolo, mese per mese. Derivata dall'indice
-- dei depositi di Defeatbeta con un aggregato solo (6,4 s, 250 MB).
--
-- Si contano SOLO gli 8-K, ed e' la scelta che fa l'indicatore: i Form 4
-- (operazioni degli insider) sono il 45,9% dell'indice, e contare «i depositi»
-- vorrebbe dire contare quelli.
--
-- Non c'e' vincolo verso l'anagrafica: qui ci sono anche titoli che
-- nell'universo non compaiono, e toglierli costerebbe una JOIN per non
-- guadagnare niente — chi legge parte sempre da un simbolo che ha gia'.
CREATE TABLE IF NOT EXISTS universe_depositi_mensili (
    symbol      TEXT    NOT NULL,
    mese        TEXT    NOT NULL,
    depositi    INTEGER NOT NULL CHECK (depositi >= 0),
    built_at    TEXT    NOT NULL,
    PRIMARY KEY (symbol, mese)
) STRICT;

CREATE TABLE IF NOT EXISTS universe_mercato (
    symbol             TEXT NOT NULL PRIMARY KEY
                       REFERENCES universe_anagrafica (symbol) ON DELETE CASCADE,
    last_close         REAL     CHECK (last_close IS NULL OR last_close >= 0),
    last_close_date    TEXT,
    avg_volume_30d     REAL     CHECK (avg_volume_30d IS NULL OR avg_volume_30d >= 0),
    -- La chiusura di 252 sedute fa e la sua data. Arrivano dalla stessa passata
    -- sul parquet dei prezzi che porta l'ultima chiusura: il pezzo caro e'
    -- attraversare 36,7 milioni di righe, e farlo due volte costerebbe il
    -- doppio per un dato che sta nella stessa finestra.
    --
    -- Servono alla forza relativa al settore, che ha bisogno della variazione a
    -- un anno di TUTTI i titoli insieme per farne la mediana per settore. Per
    -- un titolo solo il giornaliero si legge a richiesta; per undicimila no.
    close_1a_fa        REAL     CHECK (close_1a_fa IS NULL OR close_1a_fa >= 0),
    data_1a_fa         TEXT,
    built_at           TEXT NOT NULL
) STRICT;

-- L'universo come lo legge il resto del sistema. Si chiama `universe` perche'
-- e' cosi' che lo chiamano i dodici punti che lo interrogano: spezzare la
-- tabella non deve obbligarli a cambiare una riga.
--
-- `market_cap` e' CALCOLATO qui, non conservato. Prima era scritto al momento
-- della costruzione, quindi era il prodotto di un prezzo e di un numero di
-- azioni presi nello stesso istante; da quando le due meta' si rinfrescano a
-- ritmi diversi, conservarlo vorrebbe dire tenere il prodotto di due numeri di
-- epoche diverse senza che nessuno lo dica. Calcolato non puo' disallinearsi.
--
-- La LEFT JOIN e' voluta: un titolo con anagrafica e senza prezzo resta
-- visibile con le caselle vuote (regola 5).
CREATE VIEW IF NOT EXISTS universe AS
SELECT a.symbol,
       a.name,
       a.sector,
       a.industry,
       a.company_country,
       a.employees,
       a.shares_outstanding,
       m.last_close * a.shares_outstanding AS market_cap,
       m.last_close,
       m.last_close_date,
       m.avg_volume_30d,
       a.built_at AS anagrafica_built_at,
       m.built_at AS mercato_built_at
FROM universe_anagrafica a
LEFT JOIN universe_mercato m ON a.symbol = m.symbol;

CREATE INDEX IF NOT EXISTS idx_universe_name     ON universe_anagrafica (name);
CREATE INDEX IF NOT EXISTS idx_universe_sector   ON universe_anagrafica (sector);
CREATE INDEX IF NOT EXISTS idx_universe_industry ON universe_anagrafica (industry);
-- Nessun indice su `market_cap`: adesso e' un'espressione, e non si indicizza.
-- Su 11.351 righe l'ordinamento costa microsecondi, ed era l'unico uso.

-- ---------------------------------------------------------------------------
-- WATCHLIST E TAG — copia di lavoro, non originale
-- ---------------------------------------------------------------------------

-- ATTENZIONE: queste due tabelle NON sono la fonte di verita'. L'originale e'
-- `data/watchlist.json`, che si legge e si corregge con un editor di testo;
-- qui c'e' una copia allineata a ogni scrittura, che esiste solo per poter
-- fare JOIN con l'universo senza reinventare i filtri in Python.
--
-- La distinzione conta il giorno in cui si lancia `manage.py rebuild`: quel
-- comando cancella queste tabelle, e la watchlist deve sopravvivergli. Tutto
-- il resto del database e' ricostruibile da Defeatbeta; questa no.

-- La tassonomia: due livelli, ambito -> sotto-ambito. `parent` NULL significa
-- ambito di primo livello. Il vincolo di profondita' non e' esprimibile in SQL
-- e sta nel servizio.
-- I fondamentali di tutto l'universo, in forma LUNGA come li da' la sorgente:
-- una riga per (titolo, trimestre, voce). Il formato largo — una colonna per
-- voce — costringerebbe a una migrazione ogni volta che si aggiunge una voce, e
-- qui le migrazioni non ci sono per scelta.
--
-- `filing_date` e' quando quel trimestre e' diventato PUBBLICO, non quando si
-- e' chiuso: senza, ogni ricostruzione a una data passata vedrebbe bilanci che
-- allora non esistevano. Vuoto dove l'indice dei depositi non copre il titolo —
-- 8.087 simboli su 11.530 — e li' chi calcola ricade sul ritardo stimato
-- dichiarandolo.
CREATE TABLE IF NOT EXISTS universe_fondamentali (
    symbol      TEXT NOT NULL,
    report_date TEXT NOT NULL,
    voce        TEXT NOT NULL,
    valore      REAL,
    filing_date TEXT,
    built_at    TEXT NOT NULL,
    PRIMARY KEY (symbol, report_date, voce)
);

-- La chiusura di fine mese di ogni titolo, per rigiocare un criterio
-- all'indietro senza rileggere i prezzi un titolo alla volta. Mensile e non
-- giornaliera: un rigioco guarda i mesi, e la giornaliera sarebbe venti volte
-- piu' grande per una precisione che nessuno userebbe.
-- Le due colonne oltre la chiusura non sono un ornamento: sono cio' che rende
-- ONESTO il paragone del rigioco.
--
-- Il paragone confrontava chi un criterio trova con la mediana di TUTTO
-- l'universo, dentro cui ci sono migliaia di societa' minuscole e poco
-- scambiate su cui nessuno comprerebbe: un criterio che le evita risultava
-- perdente anche quando stava solo evitando il fondo del barile.
--
-- Filtrare quel paragone con la capitalizzazione e il volume di OGGI sarebbe
-- stato peggio del difetto: le societa' grandi oggi sono i sopravvissuti e i
-- vincitori, quindi il metro del 2019 sarebbe stato costruito con la risposta
-- del 2026. Qui volume e azioni sono quelli che si conoscevano ALLORA, e la
-- capitalizzazione di un mese e' `chiusura * azioni` di quel mese.
--
-- Le azioni portano il ritardo di deposito dei bilanci: un numero di azioni
-- riferito al 30 giugno diventa pubblico a inizio agosto, e usarlo a giugno
-- sarebbe lo stesso look-ahead che `as_of` esiste per impedire altrove.
CREATE TABLE IF NOT EXISTS universe_prezzi_mensili (
    symbol       TEXT NOT NULL,
    mese         TEXT NOT NULL,          -- 'YYYY-MM'
    chiusura     REAL NOT NULL,
    -- Volume medio delle sedute DI QUEL MESE. Vuoto non capita, ma la colonna
    -- resta opzionale: un mese con una sola seduta e' comunque un mese.
    volume_medio REAL,
    -- Azioni in circolazione gia' pubbliche a quella data. Vuote per i titoli
    -- di cui Defeatbeta non pubblica le azioni: sono 2.450 su 11.351, e per
    -- loro la capitalizzazione non e' assente, e' NON DERIVABILE.
    azioni       REAL,
    built_at     TEXT NOT NULL,
    PRIMARY KEY (symbol, mese)
);

CREATE INDEX IF NOT EXISTS idx_universe_prezzi_mensili_mese
    ON universe_prezzi_mensili (mese);

CREATE INDEX IF NOT EXISTS idx_universe_fondamentali_symbol
    ON universe_fondamentali (symbol);

CREATE TABLE IF NOT EXISTS watchlist_tags (
    name        TEXT NOT NULL PRIMARY KEY,
    label       TEXT NOT NULL,
    parent      TEXT REFERENCES watchlist_tags (name) ON DELETE CASCADE,
    order_index INTEGER NOT NULL DEFAULT 100 CHECK (order_index >= 0)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_watchlist_tags_parent ON watchlist_tags (parent);

-- I titoli osservati, con gli attributi con cui li si orienta.
--
-- `profilo` e `maturity` hanno valori enumerati copiati dal thematic-equity-
-- monitor, dove la scala e' gia' collaudata: il profilo dice quanto del valore
-- e' gia' provato, la maturity a che punto e' arrivato il business. Sono in
-- CHECK perche' un valore inventato non deve entrare in tabella e comparire in
-- un filtro sei mesi dopo.
CREATE TABLE IF NOT EXISTS watchlist (
    symbol   TEXT    NOT NULL PRIMARY KEY,
    profilo  TEXT             CHECK (profilo IS NULL OR profilo IN
                                     ('CORE', 'EMERGING', 'OPTIONALITY')),
    maturity TEXT             CHECK (maturity IS NULL OR maturity IN
                                     ('CONCEPT', 'DEVELOPMENT', 'DEMONSTRATED',
                                      'CONTRACTED', 'OPERATIONAL', 'SCALED')),
    favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
    added_at TEXT    NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_watchlist_profilo  ON watchlist (profilo);
CREATE INDEX IF NOT EXISTS idx_watchlist_maturity ON watchlist (maturity);

-- A quali temi appartiene un titolo. Una tabella a parte perche' i temi sono
-- PIU' di uno: AMD sta nei semiconduttori e nell'infrastruttura per l'AI, e il
-- tag singolo del primo modello costringeva a sceglierne uno solo, senza poter
-- tornare indietro. Ogni riga e' una coppia (titolo, etichetta), e l'etichetta
-- puo' essere un ambito oppure un sotto-ambito.
CREATE TABLE IF NOT EXISTS watchlist_membri (
    symbol TEXT NOT NULL REFERENCES watchlist (symbol) ON DELETE CASCADE,
    tag    TEXT NOT NULL REFERENCES watchlist_tags (name) ON DELETE CASCADE,
    PRIMARY KEY (symbol, tag)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_watchlist_membri_tag ON watchlist_membri (tag);

-- ---------------------------------------------------------------------------
-- MODELLI LINGUISTICI — cosa e' stato chiesto, a chi, e quanto e' costato
-- ---------------------------------------------------------------------------

-- Ogni chiamata a un modello lascia DUE righe: una in `calls`, come tutte le
-- altre chiamate del sistema, e una qui con quello che di un LLM conta e che
-- nessun'altra chiamata ha — il modello, i token, il costo.
--
-- Il costo in particolare non e' un dettaglio contabile: e' l'unica difesa
-- contro un'analisi che gira a vuoto. Nel vecchio sistema una run e' rimasta
-- "running" venti minuti senza che nessuno potesse vedere quanto stava bruciando.
CREATE TABLE IF NOT EXISTS llm_calls (
    id            INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    modello       TEXT    NOT NULL,
    fase          TEXT    NOT NULL,
    scope         TEXT,
    token_entrata INTEGER NOT NULL DEFAULT 0 CHECK (token_entrata >= 0),
    token_uscita  INTEGER NOT NULL DEFAULT 0 CHECK (token_uscita >= 0),
    costo_usd     REAL    NOT NULL DEFAULT 0 CHECK (costo_usd >= 0),
    stop_reason   TEXT,
    status        TEXT    NOT NULL CHECK (status IN ('ok', 'error')),
    error_msg     TEXT,
    run_id        TEXT             REFERENCES jobs (run_id) ON DELETE SET NULL,
    called_at     TEXT    NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_llm_calls_called_at ON llm_calls (called_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run_id    ON llm_calls (run_id);

-- I referti prodotti dalle analisi. Il contenuto e' un documento annidato, e
-- SQLite lo regge: `json_extract` con indice sui campi che si cercano, e FTS5
-- se un giorno servira' cercare nei testi. E' la ragione per cui MongoDB e'
-- stato scartato.
CREATE TABLE IF NOT EXISTS referti (
    id         INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT    NOT NULL,
    metodo     TEXT    NOT NULL,
    as_of      TEXT,
    contenuto  TEXT    NOT NULL,
    modello    TEXT,
    costo_usd  REAL    NOT NULL DEFAULT 0 CHECK (costo_usd >= 0),
    run_id     TEXT             REFERENCES jobs (run_id) ON DELETE SET NULL,
    creato_il  TEXT    NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_referti_symbol ON referti (symbol, metodo, creato_il DESC);
