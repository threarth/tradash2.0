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

**Il paese e' quello della SOCIETA', non della borsa — e la colonna si chiama
`company_country`.** BABA risulta 'China', SHOP 'Canada', e 635 titoli non ce
l'hanno affatto. Filtrare l'universo su `country = 'United States'` butterebbe
via **3.783 titoli quotati negli USA**. Il perimetro americano ce l'ha gia' il
dataset, che contiene solo listini americani: non va riapplicato sui dati
anagrafici. Il nome per esteso non e' pedanteria — e' l'unica difesa che
funziona quando a scrivere il filtro sara' qualcun altro fra sei mesi.

**I titoli incompleti entrano lo stesso, e si contano.** Tenere solo le righe
complete farebbe sparire in silenzio migliaia di titoli. `stato()` dichiara
ogni buco, e conta anche i **1.583 titoli con un prezzo piu' vecchio di una
settimana** — perche' un prezzo fermo presentato come quello di oggi e' il
difetto che ha generato la regola 3.

Al 29/08/2026, coi numeri veri: settore e industria mancano al **13,5%** (1.521
titoli), i dipendenti al 31,7% (3.563).

**Ma "manca" e' la parola giusta solo per alcuni.** Tre distinzioni che valgono
piu' di una percentuale:

* i **635 senza settore sono ETF** — SPY, QQQ, GLD, TLT, IWM. Un fondo un
  settore non ce l'ha per natura: non e' un buco da tappare, e inventargliene
  uno sarebbe peggio del vuoto;
* la **capitalizzazione non manca, non e' derivabile**: e' prezzo per azioni in
  circolazione, e 2.634 titoli non hanno affatto il dato delle azioni. Per
  questo le azioni in circolazione si conservano nella tabella invece di essere
  consumate nel prodotto — sono la spiegazione del vuoto, e `stato()` separa le
  2.634 capitalizzazioni impossibili per mancanza di azioni dalle 69 impossibili
  per mancanza di prezzo;
* i **dipendenti mancano al 31,7% e basta**: Defeatbeta non ce li ha. Li' non
  c'e' niente da riparare, solo da dirlo.

### La copertura dichiarata era migliore del vero, per colpa nostra

Il primo giro di questi numeri diceva 5,6% di settori mancanti. Falso: nel
profilo di Defeatbeta il settore manca **635 volte come NULL e 886 volte come
stringa vuota**, e il conteggio guardava solo i NULL. La copertura dichiarata
risultava il doppio di quella vera — un buco silenzioso prodotto proprio dal
codice che esisteva per dichiarare i buchi.

Adesso una stringa vuota o di soli spazi diventa NULL in scrittura. La regola
generale che ne resta: **una stringa vuota e' un dato assente**, e un
`IS NULL` da solo non e' un controllo di copertura.

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

## La watchlist (Blocco 3)

**La verita' e' un file, il database e' una copia.** La watchlist e' l'unica
cosa del sistema che, se si perde, non torna: tutto il resto e' ricostruibile da
Defeatbeta. Per questo sta in `data/watchlist.json`, leggibile e correggibile
con un editor, e SQLite ne tiene solo una copia di lavoro per poter fare JOIN
con l'universo senza reinventare i filtri in Python.

La differenza si vede il giorno in cui si lancia `manage.py rebuild`: quel
comando cancella la copia, e la watchlist deve sopravvivergli. Un test lo
verifica svuotando le tabelle e rileggendo.

**Il file non e' in git** (scelta dell'utente, 29/08). L'albero resta pulito
mentre si lavora e nessun `checkout` puo' sovrascrivere la watchlist; in cambio
non c'e' backup automatico, e il backup e' copiare il file.

**Il riallineamento guarda il contenuto, non la data di modifica.** Il primo
tentativo confrontava l'mtime del file: non funziona, misurato con una
correzione a mano che non veniva raccolta. Il kernel aggiorna gli mtime a scatti
di millisecondi, e due scritture ravvicinate risultano identiche. Adesso il
confronto e' su un'impronta del contenuto, che non costa niente in piu' perche'
il file lo leggiamo comunque a ogni giro.

Serve anche una **seconda condizione**: la copia vuota mentre la verita' non lo
e'. E' esattamente cio' che succede dopo un `rebuild` — il file non e' cambiato,
e guardando solo il contenuto la watchlist sparirebbe dalla vista pur essendo
ancora sul disco.

**Le regole della tassonomia sono decisioni del 27/08**, prese sul vecchio
sistema e riportate qui perche' restano valide: un solo tag per titolo; due
livelli, ambito e sotto-ambito; il tag di un titolo puo' essere l'uno o
l'altro, e **il sotto-ambito implica il padre**; cancellare un tag non cancella
titoli, i membri tornano senza tag; un ambito con figli non si cancella senza
dirlo, perche' libera anche i membri dei figli.

Con un difetto del vecchio sistema gia' pagato: **i tag si scrivono padri prima
dei figli**. Le chiavi esterne sono attive davvero, e nel JSON — a maggior
ragione se corretto a mano — l'ordine puo' essere qualunque.

**Quattro esiti, mai un silenzio.** Aggiungendo titoli si risponde chi e' stato
aggiunto, chi c'era gia', chi e' stato scartato perche' non ha la forma di un
simbolo, e chi e' **sconosciuto all'universo**: un ticker con un refuso e' ben
formato, ed entrerebbe in watchlist per produrre analisi vuote per sempre. Se
l'universo non e' stato costruito la verifica non si puo' fare, e la risposta
dice anche quello invece di far finta di niente.

---

## Il frontend (Blocco 4)

**Un solo processo in uso reale.** Flask serve il build di Vite dalla cartella
`dist`: in sviluppo si tengono aperti Vite e Flask perche' Vite ricarica a
caldo, ma quando si usa davvero c'e' solo Flask. E' la ragione per cui SvelteKit
resta fuori — porterebbe il suo router, ma anche un processo Node che gira da
solo, contro la regola 1. Il router se lo scrive: trenta righe, e il tasto
"indietro" del browser funziona.

**L'inviluppo si scarta in un punto solo.** `{success, data, error}` viene
aperto in `lib/api.js`, che ritorna `data` oppure solleva con il messaggio che
il backend ha scritto. Scartarlo in venti punti sarebbero venti modi di
sbagliare, e l'errore mostrato all'utente sarebbe "qualcosa e' andato storto"
invece del motivo vero.

**La regola 5 ha una meta' a video.** Il backend decide `available`, `reason` e
`action`; se il frontend li ignora e mostra una tabella vuota, il lavoro fatto
nel backend non serve a niente. Per questo c'e' un componente unico che li
rende, e uno per i valori: una cella senza dato mostra "n/d" con il perche' nel
titolo, non uno spazio bianco che si legge come zero.

**Bootstrap senza il suo JavaScript.** Il tema e' `data-bs-theme` piu'
`localStorage`, e viene applicato in `index.html` PRIMA che la pagina sia
disegnata: farlo a componente montato fa lampeggiare il chiaro sullo scuro a
ogni caricamento.

**Se il build non c'e', la pagina lo dice** col comando da lanciare. Un 404 muto
su `/` manderebbe a cercare un errore di rotte che non esiste.

---

## La watchlist si guarda come il thematic-equity-monitor

Richiesta dell'utente (30/08): lo stile di `dashboard.html` del monitor — temi,
sottoambiti, profili e maturity — ma **editabile per ticker**. Nel monitor la
classificazione la scriveva un LLM dentro un file e la dashboard era una vista
immodificabile; qui la stessa forma, con ogni scheda che si apre e si corregge,
perche' quei quattro attributi sono giudizi di chi guarda.

Da li' arrivano due scale gia' collaudate, copiate coi loro valori e la loro
legenda: **profilo** (CORE / EMERGING / OPTIONALITY — quanto del valore e' gia'
provato) e **maturity** (CONCEPT → DEVELOPMENT → DEMONSTRATED → CONTRACTED →
OPERATIONAL → SCALED). Sono in CHECK nello schema: un valore inventato non entra
in tabella per poi comparire in un filtro sei mesi dopo.

**E da li' arriva la revisione del tag singolo.** Il monitor tiene `themes` come
lista perche' un titolo puo' stare in piu' temi; la regola del 27/08 ne
ammetteva uno solo, e il piano di allora annotava gia' AMD come il caso che non
sapeva rappresentare. Adesso e' una relazione molti-a-molti, e il filtro per
tema dice "contiene", non "e' uguale a".

### Il giro esporta → classifica altrove → importa

Serve a non classificare cinquanta titoli a mano. L'applicazione compone il
**prompt** da dare a un LLM e ci mette dentro i valori ammessi e **i temi che
esistono gia'**: senza quelli l'LLM ne inventa di paralleli, e l'import si
riempie di doppioni che dicono la stessa cosa con parole diverse.

L'esportato e l'importato hanno la **stessa forma** — un formato per uscire e
un altro per rientrare sarebbero due occasioni di sbagliare — e l'import crea i
temi che non trova, perche' rifiutare una classificazione perche' i nomi sono
nuovi vorrebbe dire ricopiarli a mano prima di poterla usare. Crea anche
l'ambito padre quando serve, **e lo dichiara**: un padre nato di soppiatto e'
esattamente il genere di cosa che un resoconto deve nominare.

Verificato dal vivo su sette titoli veri: dieci temi creati su due livelli,
profilo e maturity assegnati, zero perdite nel giro di andata e ritorno.

---

## Il glossario (Blocco 5)

**La sottolineatura e' sistematica perche' c'e' un controllo, non una regola.**
Nel vecchio tradash il glossario funzionava, ma andava applicato a mano
avvolgendo il testo in `GlossaryText`, e su tutto il frontend lo facevano **21
file**. Il difetto non era la copertura parziale: era che *sembrava completa* —
apri una pagina in cui i termini sono sottolineati e dai per scontato che lo
siano ovunque.

Qui la prosa passa da un componente `Testo`, e un test della suite legge i
sorgenti del frontend: ogni componente o usa `Testo`, o sta nell'elenco delle
eccezioni **col suo motivo**. Aggiungere una pagina fa fallire la suite finche'
qualcuno non sceglie. Due test di contorno tengono onesto l'elenco: le
eccezioni per file che non esistono piu' fanno fallire (una regola che si
allenta senza che nessuno se ne accorga), e le tre "porte della prosa" —
`Assente`, `Errore`, `Valore` — devono usare il glossario, perche' sono loro a
rendere vere le eccezioni degli altri.

**Il rilevatore e' logica pura, in un file suo.** Niente stato, niente Svelte,
niente chiamate: la stessa separazione che nel backend tiene `domain/` senza
I/O. Cosi' si e' potuto testarlo davvero, e i casi che ha richiesto dicono
quanto era necessario: parole dentro altre parole (`RS` dentro `MARS`), frasi
lunghe che ne contengono di corte (`Free Cash Flow` che non va spezzato in
`Cash` e `Flow`), le sigle distinte dalle traduzioni fra parentesi, e
l'espressione regolare con flag globale, il cui `lastIndex` mutabile fa saltare
pezzi di testo alla seconda chiamata sullo stesso oggetto.

E' costato una dipendenza nuova, `vitest` (387 M download/mese): il backend ha
ruff e pytest a far rispettare le regole, il frontend non aveva niente.

**Cinque rimandi puntavano a termini mai scritti.** Trovati dal test sui dati
copiati: `volatility` (citato da bollinger, atr e rolling_beta),
`market_tailwind` e `sector_leadership`. Un rimando rotto e' peggio di nessun
rimando — promette e non mantiene. Sono stati tolti dal file invece di
inventare tre definizioni in un glossario che e' curato a mano: **i tre
concetti restano da scrivere**, e questa riga esiste per non dimenticarlo.

---

## Il battito della barra aveva un ritmo solo

Trovato guardando il log del server dal vivo: la barra in alto chiedeva
`/api/ops/active` **ogni tre secondi per sempre**, anche a schermo fermo. E'
una lettura in memoria e non costa quasi niente, ma "il costo di una pagina non
dipende da quanto a lungo resta aperta" e' la regola 2 alla lettera — e il
vecchio sistema e' morto proprio cosi', con una scheda dimenticata che al
riavvio del backend ha rilanciato 500 download.

Adesso i ritmi sono due: due secondi mentre qualcosa gira, trenta quando non
gira niente. La reattivita' resta dov'e' utile, e una scheda dimenticata smette
di essere un costo.

---

## I filing li scarichi tu, e il nome e' il numero di protocollo

L'analisi qualitativa — l'unica davvero usata nel vecchio sistema, 46 referti su
69 — ha come fonte primaria il **testo** dei documenti SEC. Defeatbeta porta
l'INDICE dei depositi (tipo, date, URL, numero di protocollo) ma non il
contenuto, e senza contenuto quell'analisi non produce una versione povera: non
ne produce nessuna.

**Scelta dell'utente (30/08/2026): li scarica lui.** Il sistema dice quali
servono, dove metterli e con che nome; l'utente apre l'URL e salva. Niente
fetch automatico verso sec.gov.

### Il nome del file

    NVDA_10-Q_2026-07-26_0001045810-26-000075.html
    ^^^^ ^^^^ ^^^^^^^^^^ ^^^^^^^^^^^^^^^^^^^^
      |    |      |        il numero di protocollo: LA CHIAVE
      |    |      fine periodo, per ordinarli a occhio nella cartella
      |    che documento e'
      il titolo, cosi' un file spostato resta riconoscibile

**Il riconoscimento avviene sul numero di protocollo, non sul resto del nome.**
E' la chiave univoca di EDGAR e compare gia' dentro l'URL che si apre: se il
file viene salvato con un nome qualunque ma quel numero c'e', il documento viene
trovato lo stesso. Verificato con un file chiamato
`nvidia scaricato ieri 000104581026000075.html`.

Il confronto ignora i trattini, perche' il protocollo compare in due forme:
`0001045810-26-000075` nel documento, `000104581026000075` nel percorso.

**Perche' non l'accession number e basta.** Sarebbe univoco e sufficiente per la
macchina, e illeggibile per chi guarda la cartella: `0001045810-26-000075.html`
non dice di che societa' sia ne' di quale trimestre. Il nome completo serve
all'occhio, il protocollo alla macchina, e i due non litigano perche' il
secondo sta dentro il primo.

**Il testo si estrae con `html.parser` della libreria standard**, saltando
`<script>` e `<style>` e stringendo gli spazi ripetuti: ognuno di quelli, in un
filing HTML, e' un token pagato. Nessuna dipendenza nuova.

### Il collegamento diretto, e perche' e' una convenzione

Defeatbeta da' l'indirizzo della CARTELLA del deposito, dove ci sono
centoquattordici file e bisogna cercare a mano quale sia il documento. Il
collegamento diretto si costruisce invece per convenzione:

    {cartella}/{simbolo minuscolo}-{fine periodo senza trattini}.htm
    -> .../000104581026000021/nvda-20260125.htm

Dal 2019 la gran parte degli emittenti nomina cosi' il documento principale.
**Non e' una regola della SEC: e' un'abitudine**, e chi non la segue da' un 404.
Per questo la pagina mostra DUE collegamenti — "documento", comodo e non
garantito, e "cartella", scomodo e sempre valido — dicendo quale e' quale.

**Sapere il nome vero si potrebbe**: sta nel campo `primaryDocument` di
`data.sec.gov/submissions/CIK{cik}.json`, verificato. Era stato scritto, e poi
tolto: **decisione dell'utente del 30/08/2026, tradash non fa accessi a
sec.gov.** Il testo dei filing lo scarica lui col browser; il programma non
parla con la SEC.

---

## Una cache di byte puo' disallinearsi mentre il processo e' acceso

Trovato dal vivo il 30/08/2026. Una lettura che il giorno prima funzionava —
`stock_sec_filing` — ha cominciato a rispondere `don't know what type:`, e
falliva anche un semplice `COUNT(*)` con un filtro.

La causa: **il dataset si aggiorna ogni notte** (04:50 UTC quel giorno), e
`cache_httpfs` teneva pezzi della versione precedente. Mescolati ai nuovi, danno
un parquet illeggibile. La libreria un controllo ce l'ha — confronta
`update_time` di `spec.json` con la cache — ma **solo quando costruisce il
client**: un server lasciato acceso attraversa l'aggiornamento e non lo ripete
mai piu'.

**La prima difesa era debole, e si e' vista cadere dopo mezz'ora.** Riconosceva
la cache guasta dal TESTO dell'errore, con un elenco di frasi ricavato da un
solo campione. La lettura successiva si e' rotta con una forma diversa —
`TProtocolException: Invalid data` invece di `don't know what type` — e ha
attraversato il controllo indisturbata, mandando in 500 la scheda del titolo.

La difesa vera non guarda il testo: **una query ben scritta non fallisce.** Se
fallisce, si butta via la cache di quel file *e il client*, e si riprova una
volta sola; se fallisce ancora, e' un guasto vero e passa a chi ha chiamato.
Buttare il client e' la mossa che conta, perche' ricostruirlo fa rifare alla
libreria il SUO confronto con `spec.json`, che sa svuotare tutta la cache —
cosa che noi, file per file, non sapremmo fare.

**Quanto e' grave, misurato.** Avevo scritto che una cache disallineata
"potrebbe restituire dati sbagliati invece di un errore". Non e' vero, o almeno
non e' cio' che succede: alterando 200 byte dentro un pezzo di cache gia'
scaricato, DuckDB si rifiuta di leggere il file
(`Invalid Input Error: Failed to read file`). Parquet ha struttura e checksum
sufficienti perche' il guasto sia rumoroso.

Quindi: e' un difetto vero — ha rotto l'applicazione due volte in una sessione —
ma **della specie rumorosa**, non di quella che falsa i numeri in silenzio.

---



---

## Un test lasciava vivo il proprio thread

Trovato dall'avviso di pytest su un'eccezione in un thread: il test delle route
dell'universo faceva partire la costruzione in background e finiva senza
aspettarla. Smontato il monkeypatch, quel thread chiamava la derivazione
**vera** e provava ad andare in rete — l'ha fermato il divieto sui socket, ma
il lavoro non sorvegliato e' proprio cio' che questo progetto esiste per
impedire, e in una suite non fa eccezione.

Adesso i test che avviano un lavoro aspettano che sia finito, e verificano che
sia stato il finto a girare.

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

---

## Un rimando dentro una sezione ne rovinava due (Blocco 8)

Dividere un 10-K nei suoi Item sembra un problema di espressioni regolari, e
non lo e': lo stesso «Item 1A» compare nell'indice, come titolo, e in ogni
rimando interno. Misurato su un documento costruito con le trappole vere:

La frase «For a discussion of these risks, see **Item 1A**. Risk Factors»,
scritta **dentro** la sezione Business, faceva due danni insieme — chiudeva
Business a un terzo della sua lunghezza, e faceva cominciare li' i Risk
Factors, che si portavano dietro la coda di Business. Due sezioni sbagliate per
una frase, e nessuna delle due segnalata come tale.

La regola che le distingue e' banale e regge: **un titolo apre la riga, un
rimando sta in mezzo a una frase.**

E poi un fatto strutturale sui trimestrali, che il primo test ha trovato subito:
**in un 10-Q la numerazione riparte nella Parte II.** L'MD&A e' l'Item 2 della
Parte I, i Risk Factors sono l'Item 1A della Parte II — che ha un numero piu'
basso. Cercando "il prossimo Item successivo" l'MD&A si prendeva dentro anche i
rischi. Si chiude al primo Item **diverso**, il che ha anche il pregio di non
farsi chiudere dalle intestazioni ripetute in testa a ogni pagina.

Il divisore non ha ancora incontrato un filing vero: e' provato su un documento
costruito. Va detto, perche' i documenti veri hanno sempre una trappola in piu'.

---

## Una citazione si verifica, non si crede (Blocco 8)

Il report qualitativo chiude chiedendo al modello le frasi che sostengono ogni
affermazione. **Una frase ricostruita a memoria assomiglia moltissimo a una
citata**, e l'unico modo di distinguerle e' cercarla nel testo.

Ogni citazione viene cercata alla lettera nel documento che il modello indica.
Quelle che non si trovano non vengono corrette: vengono scartate, e il referto
dice quante ne ha scartate — che e' l'informazione utile, perche' dice quali
parti del report non poggiano sul testo.

Gli spazi non contano nel confronto: il modello riavvolge le righe, e un a capo
in piu' non fa di una frase copiata una frase inventata.

Stessa forma per la **tassonomia**. Nel vecchio sistema il vocabolario chiuso
stava nell'enum dello schema di un tool, e a farlo rispettare era la validazione
del tool. Qui non ci sono tool: il modello risponde con un JSON, e un JSON
contiene qualunque parola. Il vocabolario sta nel codice e le etichette si
controllano dopo — un'etichetta fuori elenco viene **scartata e dichiarata**,
mai corretta d'ufficio: correggerla vorrebbe dire indovinare cosa intendeva il
modello, e un'etichetta indovinata da noi finirebbe nella watchlist come se
l'avesse scelta lui.

---

## Un DCF e' un'opinione sui propri ingressi (Blocco 9)

Le 3.295 righe di `forward_analysis` del vecchio sistema **non sono mai
girate** — zero istantanee, zero chiamate al modello. Riportarle avrebbe voluto
dire chiamare funzionalita' del codice mai visto funzionare. La forward analysis
e' ricostruita sul DCF che Defeatbeta calcola gia': WACC col CAPM, crescita
dagli utili, tasso terminale dal Tesoro a cinque anni.

Rifarlo in proprio serve a **poterlo rifare con altre ipotesi**, e i tre casi
misurati dal vivo dicono perche':

| | prezzo equo | mercato | letto male | letto per intero |
|---|---|---|---|---|
| NVDA | 52,59 | 217,55 | "sopravvalutata del 300%" | la crescita e' fissata al 20% (il tetto della libreria) mentre i ricavi crescono dell'88% annuo; per giustificare il mercato servirebbe il **55,6%** annuo |
| KO | 255,48 | 89,66 | "occasione, vale 3 volte tanto" | **l'82% del valore e' nel valore terminale**, e lo sconto e' il 6,15% |
| F | 69,05 | 13,88 | "occasione, vale 5 volte tanto" | **l'83% nel valore terminale**, sconto 5,5%, crescita al minimo del 5% |

Il nostro conto e quello della libreria coincidono fino all'ultima cifra
(52.58542482851447 contro ...48), e un controllo lo verifica a ogni referto: il
giorno che divergono, il referto lo dice invece di pubblicare una griglia di
sensibilita' che non descrive piu' il numero accanto a cui sta.

**Due cose della libreria non si propagano.** Il campo `recommendation`, con
scritto "Buy" o "Sell": e' un giudizio di una riga costruito sul confronto fra
due numeri, e accanto a un'analisi sembrerebbe la sua conclusione. E il loro
margine di sicurezza, che divide per il prezzo equo invece che per il mercato:
il -3,14 di NVDA si legge come "sopravvalutata del 314%" e non e' cio' che dice.
Diviso per il mercato fa -0,76, e non si puo' fraintendere.

---

## Il verdetto non e' un punteggio (Blocco 9)

Il vecchio sistema chiudeva con un giudizio sintetico. **Un numero unico che
riassume sei analisi discordanti nasconde esattamente cio' che va visto: che
discordano.**

La parte utile del verdetto sono le contraddizioni — la lettura tecnica che vede
forza mentre i segnali fondamentali si deteriorano, il DCF che dice caro mentre
la earnings call racconta un'accelerazione — e per ognuna il modello deve dire
**quale osservazione la scioglierebbe**.

E ogni referto gli arriva con la propria eta' in giorni, quelli oltre il mese
marcati vecchi: una sintesi che mette insieme una lettura di tre mesi fa e una
di stamattina e' coerente e sbagliata, e il difetto non si vede perche' il testo
di un referto e' scritto al presente e non dice quando e' stato scritto.

Con meno di due referti si ferma: la sintesi di uno solo e' una parafrasi.

---

## Il point-in-time ha due tagli, e sono diversi (Blocco 7, chiuso col 8)

Il valore della pagina di confronto sta in una condizione sola: **cio' che
mostra come "quello che si sapeva" dev'essere davvero quello che si sapeva.**
Bastano due sedute di troppo nel taglio perche' il confronto diventi la
dimostrazione che il metodo funziona, e sarebbe una dimostrazione falsa.

I prezzi si tagliano sulla data. I bilanci si tagliano sulla **data di
deposito** — un trimestre chiuso il 31 gennaio diventa pubblico a fine febbraio.
Il taglio dei bilanci e' una funzione sola, condivisa con la rotta dei segnali:
due tagli scritti due volte divergono, e il giorno che divergono una delle due
pagine mostra il futuro senza dirlo.

Verificato su NVDA al 2025-08-29: 17 periodi su 20 visibili, tutti su date di
deposito reali. E un difetto trovato proprio li': il rendimento a un anno veniva
calcolato — l'ultima seduta distava 364 giorni, dentro la tolleranza di sette —
ma l'orizzonte risultava non maturato. **Due campi della stessa risposta che si
contraddicono sono peggio di entrambe le letture.**

---

## Due fornitori, e il fornitore lo dice il nome del modello

Scelta dell'utente il 31/08/2026: **GPT-5.5 come modello predefinito**, con la
strada Anthropic tenuta accanto. Il fornitore si riconosce dal prefisso del
nome — `gpt-*` a OpenAI, `claude-*` ad Anthropic — e non da un interruttore in
configurazione: chiedere `gpt-5.5` e ottenere una risposta di Claude perche' un
valore era rimasto indietro sarebbe un difetto invisibile nei referti.

Le due API non si somigliano — `system`+`messages` contro
`instructions`+`input`, pensiero adattivo contro sforzo esplicito, e un rifiuto
che da una parte e' uno stato della risposta e dall'altra un pezzo di contenuto
— e ogni adattatore restituisce la stessa forma. Il resto del sistema non sa
quale libreria ha risposto.

`openai` era **gia' installata**: arriva come dipendenza di defeatbeta-api.

**Il listino di GPT-5.5 non ce l'ho, e non l'ho scritto a memoria.** Un prezzo
inventato darebbe la cosa peggiore possibile: un numero in dollari che sembra
misurato. Finche' manca, `speso_totale()` dichiara quante chiamate non sanno
quanto sono costate, con quali modelli e quanti token — e il frontend lo mostra
dove mostra il totale. Un listino mancante letto come «gratis» nasconderebbe
proprio cio' che il registro dei costi esiste per mostrare.

---

## I due assenti di pandas, e quello che non si fermava

La prima analisi qualitativa vera si e' fermata alla **terza fase**, dopo che le
prime due erano state pagate — 78.000 token — con
`TypeError: Object of type NAType is not JSON serializable`.

`pandas.NA` arrivava dall'elenco dei dirigenti di NVDA, dove eta', anno di
nascita e compenso mancano per sette righe su dieci. Non e' un float, non ha
`.item()`, non ha `.isoformat()`: passava indenne attraverso ogni controllo di
`core/tipi.py` — il modulo che esiste **proprio** per questo — e arrivava fino a
`json.dumps`.

Cercandolo si e' trovato il suo gemello peggiore. **`pandas.NaT` non si
fermava**: ha `.isoformat()`, e quel metodo restituisce la stringa `"NaT"`. Una
data mancante diventava il testo «NaT» dentro un referto, dove nessuno l'avrebbe
riconosciuta per un dato assente. Un guasto che si vede costa due fasi; uno che
non si vede costa un referto sbagliato che sembra giusto.

Adesso i modi di dire «non c'e'» sono quattro e stanno in una funzione sola,
controllata **prima** di ogni altra cosa: `None`, `NaN`, `NA`, `NaT`.

E una lezione sul metodo: dopo il guasto, i quattro prompt sono stati costruiti
**senza chiamare il modello** per vedere se qualcos'altro esplodeva. Provare a
vuoto cio' che costa e' gratis, e va fatto prima.


---

## Una risposta tagliata non e' una risposta sbagliata

La fase delle citazioni ha prodotto **16.000 token esatti** — il tetto — e il
JSON e' arrivato monco. Il registro aveva gia' scritto la causa vera,
`incomplete: max_output_tokens`, e il referto ha riportato «il JSON del modello
non e' leggibile». **Una diagnosi disponibile e ignorata e' peggio di una
diagnosi assente: manda a cercare nel posto sbagliato.**

Quattro correzioni, una per livello:

1. L'adattatore riconosce il taglio per entrambi i fornitori e lo porta su; la
   fase lo controlla **prima** di provare a leggere il JSON.
2. Il tetto dipende dalla fase: le citazioni devono elencare una frase letterale
   per ogni affermazione di nove sezioni, ed e' la risposta piu' lunga che
   questo sistema chieda.
3. Se ne chiedono **al massimo 24**, e il prompt spiega perche' scegliere e'
   meglio che elencare: una risposta piu' lunga non viene accorciata, viene
   tagliata, e allora si perdono tutte e non le ultime.
4. La quarta fase non fa piu' perdere le altre tre. Buttare un report gia'
   scritto perche' l'ultimo passo e' fallito e' sbagliato due volte: si perde il
   referto e si perde il denaro gia' speso.

E la lezione a monte, che vale per ogni analisi a piu' passi: **il materiale si
raccoglie tutto prima di spendere il primo token.** Il `json.dumps` che lo
controlla non e' decorativo, e' il controllo — un guasto nei dati costa zero
invece di due fasi.

---

## Il giro riuscito, e cosa dimostra

31/08/2026, GPT-5.5, i documenti veri di NVDA salvati a mano. 140.831 token in
ingresso, 27.439 in uscita, quattro fasi.

- **Nove sezioni scritte**, tutte piene.
- **Dodici dimensioni classificate, zero etichette inventate.** Il vocabolario
  chiuso ha tenuto senza che a farlo rispettare ci fosse l'enum di uno schema:
  la verifica dopo la risposta basta.
- **25 citazioni verificate alla lettera, zero scartate**, prese da tutti e due
  i documenti — il 10-K e il 10-Q. Una di quelle conteneva un apostrofo
  tipografico: e' la citazione che, con la codifica sbagliata, sarebbe stata
  scartata senza che nessuno capisse perche'.
- La sezione Risk Factors e' stata **troncata** da 114.916 a 60.000 caratteri, e
  il referto lo dichiara in tre posti: nel prompt, nella copertura, e a schermo.

Un dettaglio da tenere d'occhio: ne sono arrivate **25 a fronte di 24 chieste**.
Il tetto e' una richiesta nel prompt, non un limite imposto dal codice, e il
modello puo' superarlo di poco. Si dichiarano tutte e due le cifre invece di
troncare l'elenco: tagliare la venticinquesima nasconderebbe che il modello non
ha rispettato il tetto.

---

## Il conto vero della prima giornata con un modello

Listino di gpt-5.5 riferito dall'utente il 31/08/2026 da una ricerca sul web —
**non letto dal cruscotto ne' da un'API**, e questo sta scritto anche in
`config.py` accanto ai numeri: 5,00 dollari per milione di token in ingresso,
30,00 in uscita. La chiave normale non ha il permesso `api.usage.read`, quindi
la strada automatica non c'era.

`manage.py costi` ha ricalcolato tutte e tredici le chiamate gia' registrate
senza rifarne nessuna, ed e' venuto fuori il conto:

| | |
|---|---|
| totale della giornata | **$4,74** su 13 chiamate |
| il referto qualitativo riuscito (4 fasi) | **$1,53** |
| buttato nei tre giri falliti | **$3,18** su 8 chiamate |
| la lettura tecnica | $0,03 |

**Due terzi della spesa sono finiti nei tentativi falliti**, e conviene guardare
dove: 1,22 dollari in due fasi 1 e due fasi 2 rifatte da capo per un
`pandas.NA`, e 0,73 dollari in una sola risposta tagliata dal tetto di token —
la piu' cara della giornata, e completamente persa.

E' la misura che giustifica le due correzioni fatte subito dopo: raccogliere
tutto il materiale **prima** di spendere il primo token, e non far perdere alla
quarta fase le tre gia' pagate. Non erano rifiniture: erano i due terzi del
conto.


---

## Due verdetti sulla stessa azienda erano uno di troppo

La sezione «salute» del vecchio tradash produceva un **Health Score 0-100** con
etichetta OTTIMA/BUONA/MODERATA/DEBOLE/CRITICA, calcolato da quattro
sotto-punteggi con pesi e scale proprie. Accanto, il Fundamental Quality Service
dava il suo giudizio sulla stessa azienda. **Due numeri diversi, nessuno dei due
derivabile dall'altro**, e chi leggeva doveva scegliere a quale credere.

Il vecchio sistema l'aveva gia' tolto, e qui non e' tornato: restano le figure
di bilancio e i quattro rapporti di solidita', che sono cio' che la sezione deve
mostrare. Il giudizio appartiene all'analisi fondamentale, ed e' uno solo.

Un rapporto che non si puo' calcolare vale `None` e porta il motivo. Un
denominatore a zero non da' un rapporto infinito: da' un rapporto che non
esiste, e mostrare un numero enorme al suo posto sarebbe peggio che non mostrare
niente.

E la storia del debito porta **tutti e tre i numeri**, non solo il rapporto: un
debito su patrimonio che scende puo' voler dire che il debito cala o che il
patrimonio sale, e sono due storie diverse. Misurato su NVDA: da 0,088 a 0,063 in
due trimestri col debito che **saliva** da 10,5 a 12,3 miliardi — era il
patrimonio a correre.

---

## Un indice e un elenco di sezioni sono due elenchi che divergono

Il navigatore laterale della scheda titolo non ha un elenco suo. Ogni sezione si
registra quando compare e si toglie quando sparisce, e il navigatore mostra
quello che c'e' davvero.

L'alternativa — un elenco di voci nel navigatore e uno di sezioni nella pagina —
e' la stessa forma di difetto del vocabolario degli indicatori: due posti da
tenere allineati, e prima o poi si aggiunge una sezione senza aggiungerla
all'indice, oppure la si nomina e il collegamento non porta da nessuna parte.

Le sezioni si richiudono, e quelle **di consultazione partono chiuse** — i
depositi SEC, le notizie, il simulatore, la ricostruzione: aperte spingono in
fondo alla pagina tutto quello che viene dopo. Lo stato si ricorda nel browser,
perche' chi chiude i depositi SEC li vuole chiusi anche domani.

---

## Ricognizione del 01/09/2026: cosa e' uscito, e cosa no

Passate tutte le 140 righe dell'inventario e le 21.000 righe di codice, con
attenzione a tre domande: puo' uscire qualcosa verso il web, parte qualcosa da
solo, e ci sono numeri inventati.

### Quello che NON c'e', verificato e non promesso

- **Nessuna libreria di rete** nel codice di produzione: ne' `requests`, ne'
  `urllib`, ne' `httpx`, ne' `socket`. Le uniche due porte sono
  `core/llm.py` (OpenAI/Anthropic) e `data/defeatbeta.py` (DuckDB verso
  HuggingFace), entrambe con import ritardato.
- **Nessun URL letterale** nel codice di produzione. `sec.gov` compare solo in
  stringhe costruite per te da aprire a mano, e in commenti che spiegano perche'
  non ci chiediamo niente.
- **Il frontend chiama solo `/api`.** Un `fetch` solo, in tutto il progetto, e
  punta a una costante `"/api"`. I link a sec.gov sono `<a href>`: si aprono se
  ci clicchi tu.
- **Niente parte da solo.** I due thread che esistono — scanner e costruzione
  dell'universo — partono da una POST e da nient'altro, e stanno nel registro
  dei lavori, quindi si vedono e si fermano. Nessuna GET fa lavoro.
- **La watchlist non esce mai.** Nessun modulo che parla col modello la importa.
  Il prompt di classificazione viene RESTITUITO a te da incollare altrove, non
  spedito.
- **Nessuna credenziale nel sorgente**, e watchlist, grafici, `.env`, database e
  documenti SEC non sono in git.
- **Nessuna query SQL costruita con valori esterni**: le uniche interpolazioni
  sono nomi di tabella e di colonna che vengono da elenchi chiusi nel codice.

### Cosa esce davvero, quando premi un pulsante

Verso il modello: le misure sui prezzi, il pannello di metriche, i segnali, il
TESTO delle sezioni dei filing che hai salvato tu, l'elenco dei dirigenti,
l'indice dei depositi, le trascrizioni delle call, i titoli delle notizie, e i
referti gia' prodotti. Tutto dato pubblico di mercato. Niente di personale,
niente percorsi di file, niente watchlist.

### I quattro difetti trovati, e chiusi

1. **Si poteva costruire un percorso fuori dalla cartella dei documenti.**
   `cartella("../../../etc")` usciva da `data/filings`. Non era raggiungibile
   dalle rotte — Werkzeug normalizza il percorso e la rotta non combacia — ma
   quella e' una proprieta' di un'altra libreria, e una difesa che dipende da un
   pezzo che non controlliamo non e' una difesa. Contava doppio: quei file, se
   letti, sarebbero finiti dentro un prompt. Ora il simbolo si valida qui, e in
   piu' si verifica che il percorso RISOLTO stia dentro il perimetro — cosi' la
   difesa regge anche se un giorno l'espressione si allarga.
2. **Nel DCF, cassa e debito mancanti diventavano zero.** Un debito assente
   sarebbe stato letto come «azienda senza debiti» e il prezzo equo ne sarebbe
   uscito piu' alto, senza che niente lo segnalasse. Su F il debito vale 163
   miliardi. Adesso un ingresso che manca ferma il calcolo dicendo QUALE.
3. **`domain/statements_math.py`, 62 righe orfane.** Copiato dal vecchio
   sistema, importato da nessuno, e il suo docstring descriveva
   `FundamentalsService` e `fundamental_quality/_context` — moduli che qui non
   esistono. Tolto: il codice morto che spiega un'architettura inesistente e'
   peggio del codice morto.
4. **Due funzioni mai chiamate**: `publication_dates.visible_frame` e
   `voci.spiegazione`. Tolte.

### Un falso allarme, annotato perche' sembra un difetto

`cartella("NON..VALIDO")` produce una cartella dal nome strano DENTRO il
perimetro: i punti non sono separatori. Un test lo dice, col percorso risolto a
dimostrarlo — altrimenti qualcuno lo "corregge" un'altra volta.

---

## L'archiviazione delle chiamate: cosa si e' portato e cosa no

Il vecchio tradash archiviava 3.567 chiamate in una tabella con diciotto
colonne. Il **meccanismo** e' stato portato, non i dati; e non tutte le colonne.

**Portato, e migliorato:** modello, fase, ambito, token in entrata e in uscita,
costo, lavoro, istante. In piu' rispetto al vecchio: `stop_reason`, `status` e
`error_msg` — cioe' **come si e' fermata** una chiamata e perche' e' fallita,
che e' l'informazione che ha permesso di riconoscere una risposta tagliata dal
tetto di token invece di dare la colpa al JSON.

**Non portato di proposito:** `system_prompt`, `user_prompt` e `response`. Il
prompt di una fase qualitativa passa i 200.000 caratteri: archiviarlo a ogni
chiamata vorrebbe dire far crescere il database di un megabyte per analisi, per
un contenuto che sta gia' sul disco. Al suo posto ogni referto porta
l'**impronta** del prompt che l'ha scritto — nome, hash, lunghezza — che risponde
alla domanda per cui servirebbe il testo: «due referti dello stesso metodo sono
confrontabili, o nel mezzo il prompt e' cambiato?».

**Non portato, e resta un limite dichiarato:** `cache_read_tokens` e
`cache_write_tokens`. Se il fornitore serve parte dell'ingresso dalla cache, la
fattura e' piu' bassa del nostro conto, che li paga tutti a prezzo pieno.
Misurato su una chiamata da 1.221 token: la cache non si attiva. Sulle fasi
qualitative, da 44.000 token, potrebbe — e in quel caso il costo che mostriamo e'
una SOVRASTIMA. Registrarlo vorrebbe dire una colonna nuova, quindi un rebuild,
quindi perdere i referti gia' pagati: si aspetta di averne motivo.

---

## Il database e' ricostruibile, tranne dove non lo e'

Il progetto dichiara che il database e' una vista che si rifa' leggendo
Defeatbeta, e che l'unica eccezione e' la watchlist — che infatti sta in un file
fuori da git. **Non era vero:** i **referti** sono stati pagati, e nessuna fonte
sa riprodurli. Il registro delle chiamate e' il solo posto dove c'e' scritto
quanto si e' speso.

`manage.py rebuild` diceva «questo cancella tutti i dati» ed elencava le
tabelle. Adesso dice cosa non tornera' piu', contandolo:

    ATTENZIONE — questo non si ricostruisce da nessuna fonte:
      - 9 righe in «referti» — referti delle analisi, che sono costati denaro
      - 18 righe in «llm_calls» — registro delle chiamate, con i costi

Un comando che dice «cancella tutto» senza dire che li' dentro ci sono cinque
dollari di analisi e' un comando che si esegue una volta di troppo.

---

## Tre prompt su sette non dicevano di non dare consigli

L'audit dei prompt ha trovato la regola «niente compra o vendi» in quattro su
sette. Mancava proprio nei tre piu' esposti: la **lettura tecnica**, che e' a un
passo dal «compra qui»; l'**earnings review**, dove da una call si scivola
facilmente a «il titolo salira'»; e il **rilevatore di spin-off**, dove la
domanda naturale del lettore e' «conviene comprare prima o dopo».

Nessuno dei referti prodotti aveva dato consigli — ma non lo garantiva niente.

E il compositore dei prompt adesso **rifiuta un segnaposto rimasto vuoto**. Se
il file dichiara `{fase1}` e nessuno lo riempie, al modello arriva la parola
«{fase1}» sotto un titolo che promette le conclusioni della fase precedente: lui
non le ha, e la sua risposta sembra comunque una risposta.


---

## Via il blu notte con l'accento ciano

La prima palette era quella del thematic-equity-monitor: fondo #081019, accento
ciano #62d4ff, verde e rosa al neon. Si legge bene — era stata guardata per ore
su schermi veri — **ma e' anche l'aria che hanno tutti i cruscotti generati.**
Fondo blu-nero freddo, accento ciano elettrico, caratteri di sistema: si
riconosce da lontano chi li ha fatti.

Cambiate due cose, e la seconda conta piu' della prima.

**I colori.** Il fondo e' un nero CALDO con dentro un po' di terra (#17150f), e
la carta sopra ha lo stesso tono invece del bianco puro — che su nero vibra, e
su una tabella lunga si sente. L'accento e' un ocra: e' il colore che si nota di
meno fra quelli che si notano, e non somiglia a niente di predefinito. Su e giu'
restano distinguibili a colpo d'occhio ma smettono di essere fluorescenti —
verde salvia e cotto — perche' il neon stanca in mezz'ora.

**I caratteri, che erano quelli di sistema.** Tre famiglie con tre mestieri:
Source Serif per i titoli, che da' alla pagina un'aria da documento invece che
da pannello di controllo; IBM Plex Sans per il testo; IBM Plex Mono per i
numeri e per i simboli, che in una tabella devono incolonnarsi.

**Ospitati in casa**, non chiesti a un servizio di font: una pagina che a ogni
apertura chiama Google per i caratteri e' una chiamata verso l'esterno, e qui
non se ne fanno. Verificato sul build: zero riferimenti a `fonts.googleapis`,
tutti gli `url()` puntano a `/assets`.

Una nota pratica costata dieci minuti: il progetto usa **pnpm**, e `npm install`
su un albero di pnpm non fallisce con un messaggio chiaro — si rompe con
«Cannot read properties of null (reading 'edgesOut')», che non dice niente.

---

## Aprire e chiudere devono essere lo stesso gesto

Il pulsante per chiudere un pannello stava dentro il pannello, e quello per
riaprirlo da un'altra parte: **due bersagli diversi per una cosa sola**, e il
secondo si trovava solo cercandolo.

Adesso l'etichetta e' la stessa aperta o chiusa, resta dov'e', e si preme due
volte per tornare al punto di prima. Chiusa diventa una striscia verticale:
occupa una colonna sottile invece di una riga in mezzo al contenuto. E la
colonna del menu resta appiccicata in alto, perche' l'interruttore dev'essere
raggiungibile a qualunque altezza della pagina.

---

## L'import buttava via il perche'

Il prompt di scoperta chiede sei cose per ogni titolo proposto, e due sono
prosa: **`perche`** — cosa fa, a chi vende, da dove viene il legame col tema —
e **`cosa_lo_distingue`**, che il prompt pretende al punto di dire «se non lo
sai dire, quel titolo non serve».

L'import ne accettava tre: temi, profilo e maturity. Le altre le leggeva e le
lasciava cadere, senza una riga di resoconto. Il difetto si vede solo dopo:
entra una classificazione su un tema nuovo, e mesi dopo in watchlist c'e' un
simbolo con due etichette addosso e nessuna traccia del motivo per cui e'
entrato — cioe' l'unica parte che non si sarebbe potuta ricalcolare, perche'
tutto il resto il sistema lo deriva da se'.

Le due note adesso restano, e sono modificabili: **un perche' scritto da un
modello vale finche' non lo si riscrive.**

Tre scelte dentro la scelta.

**Non stanno nella copia SQLite.** La copia esiste per filtrare e per fare JOIN
con l'universo, e su un testo libero non si filtra. `elenco()` le rimette
accanto ai titoli leggendo il file, che ha gia' in mano — nessuna lettura in
piu', e nessuna colonna che vive solo per essere ricopiata.

**Chi non le manda non le sta svuotando.** Il prompt di classificazione le due
note non le produce: se «assente» valesse «cancella», riclassificare la
watchlist porterebbe via i perche' scritti mesi prima, e non se ne
accorgerebbe nessuno finche' non servono. Vale la stessa regola dell'editor di
un titolo: non passare un campo significa lasciarlo com'e'.

**Il testo troppo lungo si rifiuta, non si taglia.** Un taglio silenzioso fa
credere di aver salvato tutto. Il tetto — 2000 caratteri — lo dichiara il
backend nella risposta dell'elenco, e la casella lo mostra mentre si scrive
invece di farlo scoprire da un errore a salvataggio gia' tentato.

Il campo si scrive in un posto solo, la watchlist, che e' dove quella decisione
si prende. La pagina del titolo lo mostra sotto alla descrizione e basta: la
descrizione dice cosa fa la societa', la nota dice cosa ci fa **qui**, e due
punti in cui si modifica lo stesso campo sono due punti che prima o poi si
contraddicono.

---

## La tabella mostra tutto insieme, ed e' il problema

Il simulatore psicologico e' arrivato col Blocco 9 come **matrice**: mesi in
colonna, giorni in riga, verde e rosso. E' una vista onesta e si legge in un
colpo d'occhio — che e' esattamente il suo limite.

Una discesa del 60%, guardata a consuntivo, e' una macchia rossa larga tre
colonne. Vissuta, e' quattordici mesi in cui ogni mattina il numero e' ancora
sotto. Sono due informazioni diverse, e la seconda e' quella che decide se una
posizione la si sarebbe tenuta davvero: la domanda del simulatore non e' «quanto
avrei guadagnato» ma «cosa avrei passato», e la matrice risponde alla prima
meglio che alla seconda.

Nel vecchio tradash quella parte c'era: `psycho-backtest-dialog.tsx`, modalita'
«cinema», cursore che avanza giorno per giorno con la velocita' regolabile.
Riportata, con tre scelte diverse.

**Il grafico non conosce il futuro.** La scala verticale si ricalcola sui soli
giorni gia' scoperti. Con una scala fissa su tutta la corsa si vedrebbe dal
primo fotogramma quanto in alto si arrivera' — che e' precisamente
l'informazione che chi lo viveva non aveva, e senza la quale il film non serve
a niente. Vale la stessa regola gia' scritta nel dominio: la discesa di un
giorno si misura dal massimo di **allora**, non da quello di tutta la storia.

**Una passeggiata sola.** `esperienza()` faceva il suo giro sui giorni per
ricavare le misure e lo buttava via; adesso quel giro e' `andamento()`, e il
riassunto si calcola su di lui. Due passeggiate sugli stessi giorni sono due
occasioni di non essere d'accordo, e il giorno che divergessero il numero grande
in cima e il punto dove si e' fermato il film si smentirebbero nella stessa
schermata.

**Sopra i sessanta scatti al secondo si allunga il passo, non la cadenza.** A
120 sedute al secondo un fotogramma per seduta vorrebbe dire uno scatto ogni 8
millisecondi: il tempo lo si guadagna avanzando di due sedute per scatto, non
chiedendo al browser di disegnare piu' spesso di quanto un occhio veda. E oltre
i 1200 punti la linea si assottiglia — un punto ogni N sedute — con scritto
sotto che lo sta facendo: i numeri sopra restano quelli esatti del giorno.

Niente doppia valuta, a differenza del vecchio: non abbiamo una fonte per i
cambi, e l'effetto valuta qui non c'e' e non viene stimato. Era gia' dichiarato
nella pagina, e resta vero.

---

## Il percorso giusto era quello che non funzionava dove serve

La scheda dei documenti SEC mostrava la cartella in cui salvarli, con un pulsante
per copiarla: `/home/dan/coding/tradash2.0/backend/data/filings/NVDA`. Corretto,
e inutile — perche' **quel percorso va incollato in una finestra di salvataggio
di Windows**, dove un indirizzo che comincia con `/home` non porta da nessuna
parte.

E' l'unico punto del sistema in cui il giro attraversa due sistemi operativi: la
pagina gira dentro WSL, ma a scaricare e' il browser, che sta fuori. I due nomi
dello stesso posto sono due, e ne mostravamo uno solo — quello sbagliato per chi
doveva usarlo.

Adesso ci sono tutti e due, e **per primo quello di Windows**, che e' quello che
si copia: `\\wsl.localhost\Ubuntu-26.04\home\dan\...`.

Il nome della distribuzione non si indovina: lo dichiara WSL nell'ambiente del
processo (`WSL_DISTRO_NAME`), e «Ubuntu» e «Ubuntu-26.04» sono due percorsi
diversi di cui uno non esiste. Se quel nome manca, la riga non compare **e la
pagina dice perche'**: un campo che sparisce in silenzio si legge come un
guasto. Fuori da WSL non compare e non c'e' niente da spiegare, perche' li' i
due percorsi sono lo stesso.

---

## Il registro sapeva tutto, e nessuno glielo chiedeva

Ogni analisi gira gia' dentro `registry.job`, con i suoi passi e il suo
`detail`, e `/api/ops/active` lo espone da sempre. Di quel dato, pero', la barra
in alto usava **solo la lunghezza dell'elenco** — un pallino giallo con dentro
un numero — e la scheda di un titolo non lo chiedeva affatto: il pulsante
scriveva «fase 1 di 4» e restava fermo su quella scritta per tre minuti, anche
quando era alla terza fase, anche quando era andata storta.

Il pannello con tutto c'era, ed era nella pagina Operazioni: cioe' la pagina che
NON stai guardando mentre lanci un'analisi. La regola 1 dice che ogni lavoro
dev'essere visibile, e un lavoro visibile solo altrove e' visibile a meta'.

Tre pezzi, e ognuno chiude un difetto diverso.

**La scia.** Il registro teneva l'ULTIMO `detail`, non la storia. Una barra che
avanza racconta un istante; quando un'analisi sta zitta quaranta secondi alla
volta la domanda vera e' «e' ferma o sta pensando», e a quella risponde solo
l'ora dell'ultima riga. Ora ogni lavoro accumula le sue righe — con un tetto, e
col conteggio di quelle passate, perche' un elenco tagliato che non dice di
esserlo si legge come l'elenco intero. Vive in memoria e muore col lavoro: e'
una cosa che si guarda mentre succede, e la storia sta gia' in `jobs` e
`llm_calls`.

**Il racconto della chiamata sta in `llm.chiedi`**, non dentro a ogni analisi:
e' l'unico punto da cui passano tutte, comprese quelle che verranno. Si vede
partire la domanda («chiedo a claude-sonnet-5 — fase 2 · 21.312 caratteri») e
tornare la risposta, coi token e il costo. E se il modello non risponde, il
motivo si legge li' dove si stava guardando invece che solo nel log del server.

`nota()` **non controlla lo stop**, a differenza di `advance()`: viene chiamata
da dentro `llm.chiedi`, e far uscire un'eccezione da una riga di racconto
vorrebbe dire far fallire il lavoro per colpa del suo racconto.

**Un battito solo.** La barra, il pannello e la scheda del titolo chiedono lo
stesso elenco: con un poller ciascuno, un'analisi in corso sarebbero tre
richieste ogni due secondi per la stessa risposta. Il battito sta in
`lavori.svelte.js` e conta i lettori — parte col primo, si ferma con l'ultimo —
e tiene i due ritmi che aveva la barra: svelto mentre qualcosa gira, lento
quando non gira niente, perche' «il costo di una pagina non dipende da quanto
resta aperta» e il vecchio sistema e' morto proprio di una scheda dimenticata.

Un lavoro finito resta a video qualche secondo col suo esito: un pannello che si
svuota nell'istante in cui finisce non lascia il tempo di leggere com'e' andata,
ed e' la fine il momento in cui si guarda.

E il titolo su cui si sta lavorando adesso lo **dichiara** il lavoro (`ambito`)
invece di doverlo indovinare leggendo l'etichetta: un'etichetta e' una frase per
gli occhi, e cercarci dentro un simbolo vorrebbe dire che riscriverla romperebbe
la scheda. Resta in memoria — la tabella `jobs` non cambia forma, e nessuno deve
ricostruire il database.

---

## Il modello si sceglieva riavviando, cioe' non si sceglieva

Le sette fasi che chiamano un modello — le quattro della qualitativa,
fondamentale, tecnica, earnings, spin-off, verdetto, forward — passano tutte da
`llm.chiedi` e nessuna dichiara quale modello vuole: prendevano
`config.LLM_MODELLO`, cioe' `gpt-5.5`. Cambiarlo si poteva, con
`TRADASH2_MODELLO` e un riavvio del processo. E il `.env` **non veniva nemmeno
letto** — manca `python-dotenv`, e Flask lo dice a ogni avvio.

Una scelta che per cambiare vuole un riavvio non e' una scelta: e' una
configurazione. Adesso c'e' un selettore, e sta nella barra in alto — con SOPRA
il nome del modello in uso, non solo dentro al menu: quale modello risponde e'
cio' che cambia il conto, e un dato che si vede solo aprendo una tendina si
guarda quando la spesa e' gia' fatta.

**Uno solo per tutte le fasi.** Il vecchio tradash aveva una tabella di sedici
task, ognuno col suo modello. Qui le fasi sono sette e usano tutte lo stesso:
sedici righe da tenere allineate sarebbero sedici occasioni di scoprire un
giorno che una fase gira su un modello che non ricordavi di aver scelto. Il
posto per lo scavalco per fase c'e' — il file e' un dizionario — ma finche' non
serve non esiste.

**In un file, non in una tabella.** `data/impostazioni.json`, per lo stesso
motivo della watchlist: `manage.py rebuild` cancella il database, e una scelta
che dopo una ricostruzione torna al predefinito senza dirlo cambia il conto di
nascosto.

**Si rilegge a ogni chiamata**, non all'avvio: cambiare modello vale
dall'analisi successiva, comprese quelle gia' aperte in una scheda. L'ordine e'
esplicito > scelto > predefinito — un'analisi che sa quale modello le serve non
deve poter essere scavalcata da un'impostazione, e oggi nessuna lo chiede, ma la
porta resta aperta per il giorno che una fase avra' bisogno di un modello suo.

**Un modello sconosciuto si rifiuta, uno senza listino si accetta e si
dichiara.** Il primo `llm.chiedi` lo scoprirebbe comunque, ma a chiamata gia'
avviata e dentro un'analisi: il rifiuto deve arrivare mentre si sceglie. Il
secondo no: impedire un modello perche' non conosciamo ancora il suo prezzo
vorrebbe dire non poterlo mai provare, e i token restano salvati riga per riga —
`manage.py costi` ricalcola all'indietro appena il listino c'e'.

---

## Una sola cosa entra da fuori, e solo se la premi

La decisione del 30/08 diceva **fonte unica Defeatbeta, niente provider
esterni**. Il 04/09 e' stata rivista, per un dato solo e con un confine
scritto.

Il motivo e' verificabile: **Defeatbeta non sa dire chi e' nato da uno
spin-off.** Misurato su SNDK — 182 depositi nell'indice dei filing, il piu'
vecchio del 2026-01-21, nessun modulo **10-12B**, che sarebbe *il* documento con
cui uno spin-off si registra. L'indice e' recente-only. Senza sapere chi si e'
separato, il rilevatore non ha una popolazione da cercare: non e' un segnale
che manca, e' l'elenco dei candidati.

Il confine nuovo, per esteso:

* si prende **un elenco di nomi** — data, madre, nata — da
  `stockanalysis.com/actions/spinoffs/<anno>/`. **Non** prezzi, **non**
  bilanci: quelli restano di Defeatbeta e non hanno un secondo fornitore;
* si prende **solo premendo un pulsante**. Nessun aggiornamento all'avvio, a
  scadenza, o «se il file sembra vecchio». Un fetch che parte da solo resta
  esattamente cio' che qui non si fa;
* l'elenco si salva in `data/spinoff.json` e resta li' finche' non lo ripremi,
  con scritto **quando e' stato preso**: un elenco di tre mesi fa non e'
  sbagliato, e' incompleto;
* la pagina si legge con la libreria standard, nessuna dipendenza nuova per
  cinque colonne, e ci si presenta con uno User-Agent che dice chi siamo;
* se la pagina cambia forma e non si legge piu' niente, **il file di prima
  resta dov'e'**: sostituire un elenco buono con uno vuoto sarebbe perdere
  l'unica cosa che questo modulo non sa ricostruire.

La lettura passa da `registry.job` e da `calls.track` come tutte le altre: si
vede in Operazioni, lascia la sua riga col `source = network`, e si puo'
fermare. Un provider nuovo che non passasse di li' sarebbe il difetto del
vecchio sistema che ricomincia.

**Una discrepanza da ricordare**: stockanalysis data lo spin di SNDK al
2025-02-24, mentre la prima seduta nei prezzi di Defeatbeta e' del 2025-02-13.
Sono due cose diverse — la distribuzione e l'inizio degli scambi — e per
contare i mesi la piu' affidabile e' la nostra, che e' il primo prezzo davvero
esistente.

---

## I pesi del rilevatore vengono da un caso, e il caso li ha ribaltati

Il vecchio tradash aveva «find the next SanDisk»: otto segnali con pesi
differenziati, un punteggio 0-100, bonus e malus. Prima di portarlo abbiamo
fatto l'analisi del caso da cui prende il nome, e il caso ha detto che i pesi
erano quasi invertiti.

SNDK: prima seduta 2025-02-13 a $36, minimo il 22 aprile a $29,62, oggi $1.554.
Incrociando **quando un dato e' diventato pubblico** con **quanto prezzo restava
da li'**:

| quando | prezzo | cosa era pubblico | da li' a oggi |
|---|---:|---|---:|
| 2025-04-22 | 29,62 | niente: EPS -13,33, ricavi in calo | +5.150% |
| 2025-09 | ~41→113 | volume +170% sui tre mesi | +1.276% |
| 2025-11-03 | 207,01 | ricavi +21%, EPS torna positivo | +651% |
| 2026-02-02 | 665,24 | ricavi +31%, margine 51% | +134% |

**L'accelerazione fondamentale — il 30% dei pesi vecchi — e' diventata pubblica
quando il titolo aveva gia' fatto cinque volte.** Il segnale arrivato per primo
e' stato il **volume**, che nel vecchio pesava il 5%, il minimo di tutti. E il
**margine lordo**, che descrive il ciclo meglio dei ricavi (22,5% -> 78,4% in
quattro trimestri), fra gli otto non c'era affatto.

Da qui i sei segnali nuovi: volume 25, margine 20, ricavi 20, EPS 15, prezzo
sulla media a 6 mesi 10, sulla media a 50 sedute 10. **La media a 200 non c'e'**:
per uno spin-off di sei mesi non esiste — SNDK l'ha avuta a fine novembre, dieci
mesi dopo la quotazione — e un peso strutturalmente assente falsa tutto il resto.

Il difetto peggiore del vecchio non erano i pesi, era questo:

```python
except Exception:
    signals[key] = {"passed": False, "partial_score": 0.0, "note": "dati non disponibili"}
```

**«Non lo so» e «va male» finivano nello stesso numero.** Qui un segnale non
calcolabile esce dal **denominatore**: il punteggio e' «punti presi su punti
disponibili», e accanto c'e' sempre scritto su quanti segnali dei sei. Niente
bonus e niente malus: quelli del vecchio mescolavano additivo e moltiplicativo
(`+= 5`, `*= 0,85`, `*= 0,90`) e poi tagliavano a 100, e un 62 non era
interpretabile in nessun senso.

Accanto al numero c'e' uno **stato**, che il punteggio da solo non da':
*troppo presto* (meno di due trimestri dopo la separazione), *in movimento*
(prezzo e volume si', bilanci non ancora — dove stava SanDisk a settembre 2025),
*numeri girati* (novembre), *in raffreddamento* (bilanci al massimo e volume
girato — maggio 2026, e da li' -8%).

## Le tre guardie, trovate solo facendolo girare

Il modello sulla carta sembrava a posto. Queste sono venute fuori misurando
davvero i ventisette candidati dell'elenco vero.

1. **I mesi si contano dalla data dello spin, non dalla prima seduta.** Contati
   dai prezzi, NVRI dava **381 mesi** e ANGI 178: quei ticker non sono nuovi,
   hanno ereditato la storia della madre. Quando la storia comincia molto prima
   della separazione la riga lo dichiara, perche' li' «quotato da poco» non vale.
2. **I trimestri chiusi prima della separazione non si guardano.** MFP dava un
   EPS da 270,80 a 0,26: cifre per azione di una societa' che non esisteva
   ancora.
3. **Un titolo non piu' scambiato non si giudica.** TWNPQ segnava zero ovunque e
   -100% su tutto: la Q finale e' il suffisso delle bancarotte, e un punteggio
   li' sopra e' un numero che sembra un giudizio.

## Il rischio che resta

**I pesi vengono da un caso solo**, ed e' sovradattamento fino a prova
contraria: un modello tarato su SanDisk che descrive benissimo SanDisk non ha
dimostrato niente. L'antidoto e' rigiocare il punteggio a ogni fine mese su
tutti gli spin-off dell'elenco e guardare cosa e' successo dopo — venti o trenta
casi, non statistica, ma la differenza fra pesi misurati e pesi inventati. Sta
nel backlog, e non e' stato fatto.

---

## Gli stati del rilevatore sono termini, non etichette

«Numeri girati», «in raffreddamento», «troppo presto»: sono parole inventate
qui, e chi le legge in una tabella non ha modo di sapere cosa dividono da cosa.
Otto voci nuove nel glossario — i sei stati, piu' «punti disponibili» e «ticker
non nuovo» — e ognuna porta il caso da cui e' nata, che di solito e' SanDisk a
una data precisa.

Il punto non e' la definizione: e' la **differenza fra due stati vicini**. «In
movimento» e «numeri girati» possono avere lo stesso punteggio e sono due
momenti diversi — il primo e' settembre 2025 col +1.276% davanti, il secondo e'
novembre col +651%. E «troppo presto» non e' un punteggio basso: e' il rifiuto
di darne uno, che e' l'opposto.

Perche' si aprano, gli stati passano da `Testo` come tutta la prosa che arriva
dal backend. La voce **«ticker non nuovo»** invece sta nella legenda sotto la
tabella e non dentro l'icona: nascosta in un `visually-hidden` sarebbe stata
leggibile solo da un lettore di schermo, cioe' invisibile proprio a chi vede
l'orologio e si chiede cosa significhi.

---

## Un simbolo non dice chi e'

In un elenco di venti candidati la domanda «ma questo chi e'?» si fa venti
volte, e ogni volta costava una pagina aperta e una chiusa. Il vecchio tradash
aveva l'anteprima al passaggio del mouse (`ticker-cell.tsx`): e' tornata.

Tre cose sono state copiate perche' erano giuste, e sono le stesse tre che
rendono la cosa sostenibile:

* **si legge una volta sola per simbolo**, con la memoria nel MODULO e non nel
  componente: lo stesso ticker compare in due tabelle, e la seconda non deve
  richiedere quello che la prima ha gia' chiesto;
* **le richieste in volo si condividono**, altrimenti passare velocemente su una
  colonna ne fa partire una per ogni riga sfiorata;
* **non parte al montaggio**: venti simboli che si preparano l'anteprima sono
  venti richieste per una che servira'. Si legge quando il mouse si ferma
  davvero, dopo un quarto di secondo.

Il dato viene dalla tabella `universe`, che e' locale: e' una query per chiave,
non una lettura da Defeatbeta, e per questo si puo' fare mentre si scorre.

Sta dove il simbolo compare **da solo** — la tabella degli spin-off, i risultati
dello scanner. Non nell'universo, dove la riga porta gia' nome, settore,
industria e dimensione: li' l'anteprima ripeterebbe la riga sotto il mouse.
