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

## Come si legge Defeatbeta (Blocco 1)

**Si usa la libreria `defeatbeta-api`, non DuckDB scritto a mano.** Non e' una
scelta fra due motori: la libreria *e'* un client DuckDB, e fissa
`duckdb==1.5.3` fra le sue dipendenze. Quello che da' in piu' sono due cose che
non vogliamo mantenere noi: l'URL delle tabelle (`get_url_path`) e soprattutto
**l'invalidazione della cache** — il costruttore confronta l'`update_time` di
`spec.json` remoto con quello in cache e svuota tutto quando Defeatbeta
pubblica dati nuovi. Il prezzo e' il peso: 14 dipendenze d'obbligo, fra cui
`openai`, `matplotlib`, `nltk`, `ipython`. 73 pacchetti nel venv.

**Le sue tre chiamate di rete non si nascondono, si dichiarano.** Misurato il
29/08/2026 su 0.0.60, tracciando `getaddrinfo` su un import pulito:
`nltk.download('punkt_tab')` verso raw.githubusercontent.com e
`_print_welcome()` verso huggingface.co partono **all'import del modulo**, piu'
una terza nel costruttore del client. Non e' un difetto di piattaforma e non si
toglie senza monkey-patch — il vecchio tradash ne aveva scritte cento righe.
Qui l'import avviene al **primo uso reale**, dentro `calls.track()`, e finisce
nel registro come `defeatbeta:libreria:init`. La regola 2 resta intatta:
avviare l'applicazione produce zero chiamate, verificato.

**La provenienza si misura, non si stima.** Rete o cache e' il numero di
richieste HTTP che DuckDB ha davvero fatto per servire quella query: si azzera
`duckdb_logs` prima, si conta dopo. Zero richieste, riga `cache`.
*Alternativa scartata:* `cache_httpfs_cache_access_info_query()`, i contatori
dell'estensione — in una sessione hanno riportato `hit +0 miss +0` per query
che avevano fatto sei richieste HTTP vere. Dipendono da un'impostazione di
profilazione e non sono una misura affidabile.

**Cache dei byte, non cache di risposte.** `cache_httpfs` cacha byte-range:
2,2 MB su disco bastano a servire i prezzi di un titolo da un parquet di
443 MB, e la seconda lettura passa da 8,9 s a 0,03 s. Per questo non teniamo
una nostra cache di risultati: sarebbe una seconda cache sopra la prima, e
"ogni uso di cache loggato" tornerebbe ambiguo. La cartella pero' si sposta
**dentro il progetto**: la libreria la mette in `/tmp/defeatbeta/cache/<versione>`,
che su molte macchine sparisce al riavvio, e ogni byte perso e' un byte da
riscaricare.

**Il simbolo viaggia come parametro legato.** La libreria interpola il ticker
nel testo SQL (`query.format(ticker=...)`); il nostro guscio no, e in piu'
scarta con una regex tutto cio' che non ha la forma di un ticker prima ancora
di accendere il motore.

### Il peso vero delle tabelle, misurato

| Tabella | Peso remoto | Query per un simbolo, a freddo |
|---|---|---|
| `stock_profile` | 2,5 MB | 12,7 s |
| `stock_prices` | 443 MB | 8,9 s |
| `stock_statement` | 110 MB | 9,2 s (3.844 righe per AAPL) |
| `stock_earning_calendar` | 0,2 MB | 5,9 s |
| `stock_sec_filing` | 86 MB | 13,2 s |
| `stock_news` | 1.081 MB | 8,6 s |
| `stock_earning_call_transcripts` | 2.159 MB | 11,9 s |

Totale 3,9 GB, di cui 3,2 in news e trascrizioni: **scaricare tutto in locale
non e' un'opzione**, e il tetto sulle notizie non e' un lusso — quella tabella
e' grossa perche' contiene il testo degli articoli.

### Una questione lasciata aperta al Blocco 7/8

`defeatbeta-api` porta **39 template SQL e circa 80 metodi di calcolo** su
`Ticker`: margini, crescite YoY, market cap, PS/PB/PEG, enterprise value, TTM
di revenue/FCF/EBITDA, ROE/ROA/ROIC/ROCE, WACC, beta, DCF — e i **confronti di
settore** (`industry_ttm_pe`, `industry_roe`, `industry_asset_turnover`), che
il vecchio tradash non aveva: il suo peer registry copriva 7 ticker su 18.
Vale la pena valutarli al posto di parte della matematica portata a mano, con
tre avvertenze gia' verificate sul sorgente:

1. passano da `duckdb_client.query()` diretto, quindi **saltano il guscio**:
   nessuna riga di log, nessuna provenienza, nessuna freschezza. Si recuperano
   avvolgendoli nello stesso `_read`, che e' scritto per quello;
2. **non hanno `as_of`**: calcolano sull'ultimo dato disponibile. E' la porta
   nuova al look-ahead di cui parla la sezione qui sotto;
3. interpolano il ticker nella stringa SQL.

---

## L'universo (Blocco 2)

**Derivato, non dichiarato.** Il vecchio tradash teneva la lista dei titoli in
17 JSON statici, piu' quattro universi virtuali e una migrazione dedicata:
invecchiavano da soli e nessuno sapeva piu' da dove venissero. Qui e' una vista
ricostruibile — 11.256 titoli derivati da `stock_profile` unito ai prezzi e
alle azioni in circolazione, conservati in SQLite perche' le domande che gli si
fanno ("i tecnologici sopra 500 miliardi") sono domande da SQL: 0,4-2,2 ms,
contro i secondi che costerebbe rifare la derivazione ogni volta.

**Il costo vero, misurato.** La prima costruzione dura **214 s** e scarica
**443 MB**: per sapere l'ultima chiusura di ogni titolo bisogna leggere tutto
il parquet dei prezzi. Dalla cache dei byte scende a **3,7 s**. E' esattamente
il tipo di lavoro che la regola 2 vieta di far partire aprendo una pagina: si
chiede con `POST /api/universe/build`, che ritorna subito il `run_id`.

**Fermabile davvero, non a parole.** La derivazione e' *una* query da minuti.
Spezzarla in blocchi per poterla fermare avrebbe voluto dire rileggere piu'
volte lo stesso parquet, cioe' pagare la fermabilita' con il costo che si sta
cercando di evitare. DuckDB sa interrompere una query in corso — misurato:
fermata in 1,00 s su una query sintetica, 0,60 s sulla derivazione vera — e una
sentinella traduce lo Stop del registro in quell'interruzione. Il lavoro chiude
`status=stopped` con zero righe scritte.

Da qui nasce una distinzione che va tenuta: **una query interrotta da noi non
e' un guasto del provider.** Arriva come lo stesso errore, e senza guardare se
qualcuno ha premuto Stop diventerebbe un `failed` invece di uno `stopped`.

**`country` e' il paese della SOCIETA', non della borsa.** BABA risulta
'China', SHOP 'Canada', e 635 titoli non ce l'hanno affatto. Filtrare
l'universo su `country = 'United States'` butterebbe via **3.783 titoli quotati
negli USA**. Il perimetro americano ce l'ha gia' il dataset, che contiene solo
listini americani: non va riapplicato sui dati anagrafici.

**I titoli incompleti entrano lo stesso, e si contano.** Al 29/08/2026 manca il
settore al 5,6%, l'industria al 12,8%, i dipendenti al 31,7%, la
capitalizzazione al 23,4%. Tenere solo le righe complete farebbe sparire in
silenzio 2.636 titoli. `stato()` dichiara ogni buco, e conta anche i **1.583
titoli con un prezzo piu' vecchio di una settimana** — perche' un prezzo fermo
presentato come quello di oggi e' il difetto che ha generato la regola 3.

---

## `undeclared` voleva dire due cose diverse

Trovato fermando dal vivo la prima derivazione: la query interrotta finiva nel
registro come `source=undeclared` **con un ERROR "provenienza non
dichiarata"**, cioe' segnalata come un difetto del nostro codice.

Ma una chiamata fallita non ha una provenienza da dichiarare: il dato non e'
mai arrivato. Se contasse come dimenticanza, la spia si accenderebbe a ogni
errore di rete e smetterebbe di voler dire qualcosa proprio quando serve.

Adesso l'allarme suona solo per `undeclared` **con esito ok** — quello si' e'
un percorso di codice che ha letto un dato senza dire da dove. Il numero da
tenere a zero e' `calls.undeclared_ok()`, non il conteggio grezzo.

---

## Un buco nella difesa dei test, trovato misurando

**La rete spenta a livello di socket non ferma DuckDB**, che apre le
connessioni in C++ senza passare dal modulo `socket` di Python: durante le
prove, query che facevano sei richieste HTTP vere sono state contate come zero
connessioni dal contatore Python. La difesa del conftest e' reale per requests,
urllib e le librerie Python, ma non copre un motore nativo.

La difesa che copre questo caso e' un'altra, e vale anche in uso reale:
`data/defeatbeta.py` **non importa mai la libreria a livello di modulo**. Senza
import non c'e' motore, e in una suite senza rete non c'e' niente che possa
uscire. Un test lo verifica leggendo il sorgente con `ast`, non fidandosi di
`sys.modules` (che l'ordine dei test puo' sporcare).

**E il marcatore `network` era dichiarato ma non applicato**: `pytest.ini`
elencava il marcatore e il commento diceva "escluso dai giri normali", ma senza
`addopts = -m "not network"` un `pytest` liscio i test di rete li eseguiva
davvero. E' la stessa forma del difetto di `TRADASH_OFFLINE` nel vecchio
sistema: un docstring che dichiarava una difesa inesistente. Chiuso.

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
