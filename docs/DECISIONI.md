# Decisioni di tradash2.0, con il difetto che le ha causate

Ogni riga qui sotto e' costata un giro vero sul vecchio tradash. Sono scritte
nel repo, non nella memoria di un assistente, perche' fra sei mesi la domanda
"perche' era stato deciso cosi'?" torna sempre.

---

## Perimetro

**Fonte unica Defeatbeta, solo mercato USA.** Twelve Data valutato con chiamate
vere e scartato: il piano free e' US-only e non da' **nessun** fondamentale
(403 *"available exclusively with pro or ultra or venture"*, e nemmeno Grow a
$29 basta). yfinance esce del tutto. Il prezzo accettato: **niente intraday** —
il dato piu' fresco e' la chiusura del giorno prima, che e' anche la piu'
recente esistente.

**Cosa significa "fonte unica".** Un solo **fornitore di dati di mercato**, non
"mai scaricare un documento pubblico". Il testo dei 10-K si prende da `sec.gov`
seguendo l'URL che Defeatbeta stesso fornisce: nessuna chiave, nessun credito,
nessuna dipendenza commerciale. Senza quel testo l'analisi qualitativa — l'unica
davvero usata, 46 referti su 69 — non esiste.

---

## Le cinque regole

1. **Osservabilita' e controllo totali.** Ogni lavoro batch o singolo:
   gestibile, fermabile, loggato. Ogni chiamata di rete, di API e **ogni uso di
   cache**: loggato. *Difetto: girava un download di ~500 ticker che nessun
   endpoint vedeva; l'unico modo di fermarlo era uccidere il processo.*
2. **Niente lavoro pesante all'apertura di una pagina.** Il costo di una pagina
   non dipende da quanto resta aperta. *Difetto: una scheda del browser
   dimenticata ha rilanciato 500 download al riavvio del backend.*
3. **Il guard di freschezza sta sull'eta' del dato che mostri**, mai su un campo
   vicino, e vale **per categoria**. *Difetto: `if force or meta.get("market_cap")
   is None` — il market cap c'e' sempre, quindi il prezzo non si rinfrescava
   mai: SNDK mostrato a 1782 quando valeva 1487, con la variazione di undici
   giorni prima spacciata per quella di oggi.*
4. **Un simbolo rotto si isola, non frena il gruppo.** *Difetto: un `KeyError`
   strutturale su un ticker morto contava come throttling; SATS ha fatto saltare
   SNDK e altri sedici titoli sani nello stesso giro.*
5. **L'assenza si dichiara con un motivo**, mai con una casella vuota:
   `available` + `reason` + `action`, deciso nel backend.

---

## Stack

**Svelte 5 + Vite + Flask + Bootstrap 5 (solo CSS) + lightweight-charts.**

- **Niente SvelteKit**: vorrebbe un processo Node accanto a Flask, cioe' un
  secondo servizio che gira da solo — contro la regola 1.
- **Niente `bootstrap.bundle.js`**: dropdown, modal e tooltip mutano il DOM che
  Svelte considera suo e vanno distrutti a mano allo smontaggio. Sono quattro
  comportamenti, in Svelte si scrivono in poche righe.
- **`@sveltestrap/sveltestrap` scartato**: 31k download/mese, fermo dal
  04/02/2025. Dipendenza sottile fra due cose grosse.
- **Recharts non era comunque lo strumento giusto**: e' React-only, ma
  soprattutto e' una libreria da dashboard, non da grafici finanziari.
  `lightweight-charts` e' di TradingView e vanilla JS.

---

## Dati: quattro archivi, ognuno per il suo mestiere

| Cosa | Dove | Perche' |
|---|---|---|
| Dati di mercato (prezzi, bilanci) | parquet Defeatbeta, letti con **DuckDB** | colonnari, sola lettura, enormi |
| Log, lavori, freschezza, cache | **SQLite** | scritture piccole e frequenti, da piu' thread |
| Watchlist, tag, impostazioni | **JSON** (fonte di verita') + SQLite come vista | piccoli, tuoi, leggibili, non ricostruibili |
| Storico degli eventi | **JSONL** append-only | cresce in fondo, non si corregge mai |

**DuckDB non puo' sostituire SQLite**, verificato con due processi in parallelo:
DuckDB prende un **lock esclusivo** sul file (`Could not set lock on file`), per
cui col server acceso `manage.py check` da un altro terminale fallirebbe. SQLite
in WAL scrive lo stesso. Sono mestieri diversi: colonnare/analitico contro
righe/transazionale.

**MongoDB scartato**: e' un demone sempre acceso — la prima cosa che faremmo
sarebbe aggiungere un servizio che gira da solo. E i dati sono relazionali
(`calls.run_id → jobs`, watchlist ↔ tag M2M) con domande analitiche, che e' il
terreno di SQL. L'unico punto valido — i referti LLM sono documenti annidati —
SQLite lo copre gia': `json_extract` con **indice** sul campo del documento, e
FTS5 per la ricerca nei testi. Verificato su questo build.

---

## Niente migrazioni

Il vecchio tradash ne aveva **107 file, 8.195 righe**. Servono quando ci sono
database che non controlli; qui il database e' una **vista ricostruibile**.

Lo schema sta tutto in `backend/core/schema.sql`. `ensure_schema()` e'
idempotente e gira a ogni avvio; `manage.py rebuild` ricostruisce e chiede di
battere una parola a mano.

**Quando servira' una migrazione vera** (rinominare, cambiare tipo, spezzare una
tabella — aggiungere colonne e tabelle non lo richiede):

```
1. esporta i dati TUOI in JSON        ← PRIMA di toccare schema.sql
2. modifica schema.sql
3. manage.py rebuild
4. reimporta, mappando forma vecchia → forma nuova
```

Tre condizioni perche' funzioni: il dump dev'essere **semantico** (un `.dump`
SQL contiene INSERT sullo schema vecchio, inservibili appena rinomini una
colonna); si esporta **solo la roba tua** (log e cache si buttano); il file
**dichiara la propria versione**, altrimenti fra un anno non sai cosa stai
leggendo.

**Il lavoro non sparisce, cambia lingua.** Il punto 4 *e'* la migrazione,
scritta in Python su un dizionario invece che in SQL. Ci si guadagna perche'
JSON perdona e quel codice si puo' testare — non perche' sia gratis.

**Se un giorno tradash2.0 girasse anche su altre macchine**, le migrazioni si
aggiungono partendo dallo `schema.sql` di allora come versione 1. Nessuna porta
e' chiusa: il contrario costerebbe uno squash.

---

## I test girano in sviluppo, mai in uso

Quattro difese strutturali, non convenzioni:

1. **Rete spenta a livello di socket** (`connect`, `connect_ex`,
   `create_connection`, **`getaddrinfo`**) — sotto qualunque libreria. Via
   d'uscita esplicita: `@pytest.mark.network`. *Difetto: la vecchia suite
   mandava backfill yfinance veri per mesi, invisibili; e `TRADASH_OFFLINE` non
   copriva i provider principali mentre il docstring diceva il contrario.*
2. **Il database dell'uso reale e' irraggiungibile dalla suite**: `core/db.py`
   si rifiuta di aprirlo mentre pytest gira. *Difetto: la vecchia suite scriveva
   sul database vero e ne ha cancellato dati.*
3. **Il codice di produzione non sa che i test esistono** — nessun `if TESTING:`,
   nessun import verso `tests/`. Due test lo verificano leggendo i sorgenti.
4. **`create_app()` fa due cose**: schema e blueprint.

### La correzione che vale piu' della regola

Si era detto che il vecchio sistema rigiocasse le 109 migrazioni a ogni
`create_app()`. **Falso, verificato sul codice**: il ciclo controllava
`_migration_applied()` e saltava correttamente, e la suite usava un solo
database temporaneo per sessione.

A girare **88 volte per giro di suite** era la **coda di `init_db()`**, che
nessun controllo proteggeva: un `UPDATE` su tutti i membri degli universi, tre
`_add_column_if_missing`, e `ensure_seed_themes_metadata()` dentro un
`except Exception: pass` vuoto.

> Le migrazioni erano scritte bene. Il problema e' che **`create_app()` faceva
> lavoro sui dati**, e il lavoro non guardato e' finito nella riga *dopo* la
> disciplina.

---

## Vincoli noti sulle analisi

- **Le analisi sono sette.** `good_drawdown` e' stato tolto come metodo LLM: non
  per scarso uso (7 referti) ma perche' leggeva lo snapshot del GD Monitor, il
  servizio che si butta. Torna come feature tecnica deterministica.
  `earnings_review` si rifonda sulle **trascrizioni** delle earnings call: il suo
  input storico erano le sorprese Finnhub, che spariscono.
- **`forward_analysis` non e' MAI girata**: 11 moduli, 3295 righe, 9 file di
  test, zero snapshot e zero chiamate LLM. Portarla significa **verificarla dal
  vivo per la prima volta**: aspettarsi bug.
- **La qualitativa e' spezzata in 4 fasi apposta.** In un loop unico il contesto
  riaccodato a ogni retry cresceva senza limite: una run e' rimasta "running"
  20+ minuti prima che il watchdog la marcasse "hung".
- **`forward_analysis` non ha un system prompt di loop e non deve averlo**: e'
  una pipeline deterministica, le sue chiamate LLM stanno nel pacchetto di
  dominio.
- **Haiku fallisce le fasi di analisi qualitativa** (solo compressione e
  triage): su Q ha prodotto un submit invalido bruciando $0,24; Sonnet ha chiuso
  a $0,99.
- **Per i prompt il mock non basta**: la verifica e' dal vivo.

---

## Trappole misurate su Defeatbeta

- **Niente colonna `exchange`** in `stock_profile`: NASDAQ e NYSE non si
  distinguono. Rilevante perche' lo scarto prezzi misurato (2-6 centesimi) e'
  proprio per borsa.
- **Nessuna tabella di costituenti indice** (provate e tutte 404): S&P 500,
  Nasdaq 100 e Russell 2000 non sono derivabili. Entrano come lista importata
  una volta, non come servizio.
- **`stock_revenue_breakdown` copre 367 simboli su 11.256 (3%)**: e' una
  curiosita', non una fonte. Nessuna analisi puo' dipenderne.
- **Il suo `report_date` piu' recente e' nel FUTURO** (2026-09-30 osservato il
  29/08) con `period_type = trailing`. Un filtro `report_date <= as_of` scritto
  senza pensarci fa entrare periodi non ancora chiusi. **Ogni dataset nuovo apre
  una porta nuova al look-ahead.**
