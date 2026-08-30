# tradash2.0 — piano di ricostruzione

Deciso il 2026-08-29. Cartella nuova, fuori dall'albero di `tradash`, repo
separato. Il vecchio tradash non viene migrato: si prende **solo** cio' che e'
elencato qui sotto, e il resto muore.

Questo documento e' il contratto di lavoro: si procede un blocco alla volta,
con conferma. Nessun blocco parte prima che il precedente sia verde.

---

## Le regole che governano tutto

Sono le cinque nate dai difetti misurati sul vecchio sistema. Valgono su ogni
riga di codice nuovo, senza eccezioni.

1. **Osservabilita' e controllo totali.** Ogni lavoro batch o singolo:
   gestibile, fermabile, loggato. Ogni chiamata API, ogni chiamata di rete,
   **ogni uso di cache**: loggato. Nessun percorso di codice puo' fare rete o
   lavoro lungo senza passare da un registro. Non "quasi tutti": nessuno.
2. **Niente lavoro pesante all'apertura di una pagina.** Il costo di una pagina
   non dipende da quanto a lungo resta aperta. Rimontare o riconnettersi non
   rilancia lavoro pesante.
3. **Il guard di freschezza sta sull'eta' del dato che mostri**, mai su un campo
   vicino, e vale **per categoria di dato**, non globalmente.
4. **Un simbolo rotto si isola, non frena il gruppo.** Distinguere "il provider
   ci rifiuta" da "questo simbolo e' rotto".
5. **L'assenza si dichiara con un motivo**, mai con una casella vuota:
   `available` + `reason` + `action`, deciso nel backend.

Piu' due vincoli di perimetro: **fonte unica Defeatbeta**, **solo mercato USA**.
Niente yfinance, niente Twelve Data, niente secondo provider.

---

## Struttura

```
tradash2.0/
├── PIANO.md                    ← questo file
├── backend/
│   ├── app.py                  Flask: API + statici del build Vite
│   ├── manage.py               check / rebuild del database
│   ├── core/                   infrastruttura trasversale (la regola 1)
│   │   ├── schema.sql          LO schema, dichiarato in un posto solo
│   │   ├── schema.py           ensure_schema() e rebuild()
│   │   ├── registry.py         run_id, cancel, stop — obbligatorio, non opzionale
│   │   ├── calls.py            log di ogni chiamata, con la provenienza
│   │   ├── freshness.py        should_fetch(scope, category) — gate per campo
│   │   └── db.py               db_session()
│   ├── data/                   accesso ai dati
│   │   ├── defeatbeta.py       UNICO punto di accesso ai parquet
│   │   └── glossary.json       171 termini
│   ├── domain/                 matematica pura, zero I/O, zero rete
│   ├── api/                    route sottili, nessuna logica
│   ├── prompts/                26 prompt
│   └── tests/
└── frontend/                   SPA Vite + Svelte 5 (NIENTE SvelteKit)
    └── src/{lib,components,routes,styles}
```

Niente SvelteKit: richiederebbe un processo Node accanto a Flask, cioe' un
secondo servizio che gira da solo — contro la regola 1.

---

## Cosa si SALVA dal vecchio tradash

### Copia sostanzialmente verbatim

| Da | A | Righe | Perche' |
|---|---|---|---|
| `lib/indicators.ts` | `frontend/src/lib/indicators.ts` | 319 | TypeScript puro, zero React |
| `services/indicator_service.py` | `backend/domain/indicators.py` | 456 | topo-sort sul grafo dei nodi |
| `glossary.json` | `backend/data/glossary.json` | 2530 | 171 termini |
| `api/glossary.py` | `backend/api/glossary.py` | 121 | |
| `prompts/*.txt` (21) | `backend/prompts/` | 1200 | |
| `data_analysis/prompts/*.txt` (5) | `backend/prompts/` | | |
| `point_in_time_service.py` | `backend/domain/point_in_time.py` | 292 | as_of, 43 test verdi |
| `publication_dates.py` | `backend/domain/publication_dates.py` | 257 | tronca sul depositato |
| `_statements_math.py`, `capm.py`, `beta_service.py`, `technical_features.py`, `feature_engine.py`, `price_changes_service.py`, `drawdown_period_service.py` | `backend/domain/` | | matematica pura |
| `fundamental_quality/` (18 moduli) | `backend/domain/fundamental_quality/` | | veti, assi economici, risk scoring, reverse DCF |
| `services/agent/` (14 moduli) | `backend/agent/` | | 7 metodi + qualitativa a 4 fasi |
| `data_analysis/forward_analysis/` (11 moduli) | `backend/domain/forward_analysis/` | 3295 | DCF, reverse DCF, proiezioni, guidance, sensitivita' |
| `forward_analysis/prompts/*.txt` (3) | `backend/prompts/forward/` | | driver di scenario, narrativa, estrazione guidance |
| `agent/forward_analysis_orchestrator.py` | `backend/agent/` | | pipeline deterministica, non conversazione |
| `api/point_in_time.py` | `backend/api/point_in_time.py` | | confronto a due date + storia fair value |
| 9 `tests/test_forward_*.py` | `backend/tests/` | | la rete di sicurezza del DCF |

Ogni file copiato va **riletto**, non incollato: si portano dietro import verso
moduli che non esistono piu'.

### Si riscrive (l'idea si salva, il codice no)

| Cosa | Vecchio | Perche' si riscrive |
|---|---|---|
| GUI del grafico | `symbol-chart.tsx`, 1674 righe | quaranta volte il limite di 40 righe/funzione; probabile causa del "frontend lentissimo". Si rifa' in Svelte su `lightweight-charts`, pilotata dai nodi che gia' esistono |
| Glossario frontend | 4 componenti React, 456 righe | React → Svelte. Il meccanismo (mappa keyword→id da tre forme per termine) si conserva |
| Accesso Defeatbeta | `defeatbeta_provider.py` | diventa unico punto, con log cache/rete obbligatorio |
| Registro operazioni | `ops_registry` | c'era ma opzionale: `drawdown_scan_service` lo usava (9 riferimenti), `explosive_growth_service` zero. Diventa obbligatorio |
| Freschezza | guard sparsi | diventa `should_fetch(symbol, categoria)`, sul modello di `monitor.py should-fetch ALB financial_statements` |
| Tema chiaro/scuro | `next-themes` | `data-bs-theme` di Bootstrap 5.3 + localStorage |

---

## Cosa NON si porta

- **yfinance**, in ogni forma. E con lui i 17 JSON di `data/universes/`, i 4
  universi virtuali, la migrazione v25 e la search per simbolo: la lista dei
  titoli e' dentro Defeatbeta (11.256 simboli, aggiornati ogni notte).
- **Market Overview + Index Attribution**: sono quelli che il 28/08 hanno
  scaricato ~500 ticker da soli al riavvio del backend.
- **Good Drawdown Monitor**, cioe' il servizio che scandagliava da solo
  ("carino come concetto, ma basato su cosa?"). Il **metodo di analisi**
  `good_drawdown` invece resta: vedi Blocco 8. Gli **scanner mai usati**, il **fair value canonico** (0 righe atterrate), il **peer
  registry** (7 ticker su 18), i **corporate_events** (0 su 18).
- **React, Next.js, shadcn/Radix, Recharts, next-themes, Tailwind.**
- `@sveltestrap/sveltestrap`: 31k download/mese, fermo dal 04/02/2025.
- `bootstrap.bundle.js`: muta il DOM che Svelte considera suo. Solo il CSS.

---

## Stack

| Pacchetto | Versione | Download/mese | Ruolo |
|---|---|---|---|
| `svelte` | 5.57.0 | 23,2 M | UI |
| `vite` | 8.2.2 | 703 M | build |
| `lightweight-charts` | 5.2.1 | 3,7 M | grafici (TradingView, vanilla JS) |
| `bootstrap` | 5.3.8 | 25,5 M | CSS: griglia, form, tabelle, utility |
| `bootstrap-icons` | 1.13.1 | 3,2 M | icone |

Backend: Python 3.13, Flask 3, DuckDB via `defeatbeta-api`, pandas.

---

## Ordine di lavoro

I blocchi sono in ordine di dipendenza. Uno alla volta, con conferma.

**Blocco 0 — Fondamenta. FATTO il 2026-08-29, 31 test verdi.**
`core/db.py`, `core/schema.sql` + `core/schema.py` (`jobs`, `calls`,
`freshness`), `core/registry.py`, `core/calls.py`, `core/freshness.py`,
`api/ops.py`, `api/calls.py`, `app.py`, `manage.py`.

**Niente migrazioni, per decisione dell'utente (29/08).** Il vecchio tradash ne
aveva 109: servono quando c'e' un database in produzione che non si puo'
perdere, e qui il database e' una vista ricostruibile. Lo schema si dichiara in
`schema.sql`, si applica a ogni avvio (idempotente) e si ricostruisce con
`python manage.py rebuild`, che chiede una parola battuta a mano.

Tre scelte dello schema: **STRICT** (SQLite applica davvero i tipi), **CHECK**
sui valori enumerati (uno stato inventato non entra in tabella), e **`scope`
invece di `symbol`** — perche' la curva dei Treasury e la lista dell'universo
non appartengono a nessun titolo e vanno comunque chieste prima di andare in
rete.
*Verifica passata: un lavoro finto parte, compare in `/api/ops/active`, riceve
Stop via HTTP e si ferma a meta' lasciando `status=stopped` in cronologia; due
letture dello stesso dato producono due righe distinte, `network` e `cache`;
avviare l'app non produce una sola chiamata.*

**Blocco 1 — Defeatbeta, punto unico. FATTO il 2026-08-29, 53 test verdi +
2 di rete.** `data/defeatbeta.py`: profilo, prezzi, bilanci, calendario,
filings, news. Ogni lettura passa da `core/calls.py`.

Si usa **la libreria `defeatbeta-api`**, non DuckDB a mano: e' comunque un
client DuckDB (fissa `duckdb==1.5.3`) e in cambio da' l'URL delle tabelle e
l'invalidazione della cache quando Defeatbeta pubblica dati nuovi. Le tre
chiamate di rete che fa da sola all'import non si nascondono con una
monkey-patch: l'import avviene al **primo uso reale**, dentro `calls.track()`,
e compare nel registro come `defeatbeta:libreria:init`.

**La provenienza non e' una stima**: e' il numero di richieste HTTP che DuckDB
ha davvero fatto per servire quella query, letto da `duckdb_logs` e azzerato
prima di ogni interrogazione. Zero richieste, riga `cache`.

*Verifica passata (MSFT, dal vivo): la prima lettura del profilo 3.946 ms
`network`, la seconda 22 ms `cache`; i bilanci 4.570 righe in 3.190 ms
`network`; un simbolo inesistente torna `available=False` con motivo e azione
invece di sollevare; avviare l'applicazione produce zero chiamate.*

**Blocco 2 — Universo. FATTO il 2026-08-29, 68 test verdi.** Derivazione da
`stock_profile` unito a prezzi e azioni in circolazione (settore, industria,
paese, dimensione, prezzo, volume). Nessun JSON statico: **11.256 titoli**.
`data/universe.py` costruisce, `api/universe.py` espone, la tabella `universe`
in SQLite conserva.

La costruzione e' un lavoro tracciato e **fermabile davvero**: e' una query
sola da minuti, e spezzarla in pezzi avrebbe voluto dire rileggere piu' volte
lo stesso parquet. Una sentinella traduce lo Stop del registro in
`interrupt()` su DuckDB.

*Nota: `exchange` e i costituenti degli indici NON sono in Defeatbeta — se
servono, entrano come lista importata una volta, non come servizio.*
*Nota 2: `country` e' il paese della SOCIETA', non della borsa — BABA risulta
'China', SHOP 'Canada', e 635 titoli non ce l'hanno. Filtrare l'universo su
'United States' butterebbe via 3.783 titoli quotati negli USA.*

*Verifica passata: prima costruzione 214 s e ~443 MB (il parquet dei prezzi
letto per intero), a cache calda 3,7-5,7 s; Stop su una query DuckDB vera
onorato in 0,60 s lasciando `status=stopped` e zero righe scritte; le domande
all'universo (settore + capitalizzazione minima) rispondono in 0,4-2,2 ms.*

*La copertura e' dichiarata invece che scoperta, con i numeri veri: manca il
settore e l'industria al **13,5%** (1.521 titoli), i dipendenti al 31,7%
(3.563), e 1.583 titoli hanno un prezzo piu' vecchio di una settimana. La
capitalizzazione non "manca" al 23,4%: **non e' derivabile** per 2.636 titoli,
2.634 dei quali perche' Defeatbeta non ha le loro azioni in circolazione —
prezzo per azioni, senza azioni non esiste. E i 635 titoli senza settore sono
**ETF** (SPY, QQQ, GLD, TLT, IWM): un fondo un settore non ce l'ha, e
inventarglielo sarebbe peggio del vuoto.*

**Blocco 3 — Watchlist e tag. FATTO il 2026-08-29, 93 test verdi.** Modello a
due livelli (ambito → sotto-ambito), freschezza per categoria di dato, storico
append-only sul modello di `events.jsonl`. `data/watchlist.py` e
`api/watchlist.py`.

**La fonte di verita' e' `data/watchlist.json`, non il database.** E' l'unica
cosa del sistema che, persa, non torna: tutto il resto si ricostruisce da
Defeatbeta. SQLite ne tiene una copia di lavoro, che serve solo a fare JOIN con
l'universo — e che `manage.py rebuild` puo' cancellare senza danno, perche' si
riallinea da sola. Il file si corregge anche con un editor di testo, e la
correzione viene raccolta.

**Il file NON e' in git** (scelta dell'utente, 29/08): l'albero resta pulito
mentre lavori e nessun `checkout` puo' sovrascriverti la watchlist. Il backup e'
copiare il file.

Le regole della tassonomia: **due livelli**, il **sotto-ambito implica il
padre** (chi guarda "Semiconductor" vede anche "Semiconductor / Memory"), e
**cancellare un tag non cancella titoli** — i membri lo perdono e basta.

**Rivisto il 30/08: un titolo puo' stare in PIU' temi.** Il tag singolo scelto
il 27/08 costringeva a mettere AMD o nei semiconduttori o nell'infrastruttura
per l'AI, e quella scelta non era recuperabile — il piano di allora lo
annotava gia' come limite. Ogni titolo porta inoltre due attributi con valori
chiusi, presi dal thematic-equity-monitor: **profilo** (CORE / EMERGING /
OPTIONALITY) e **maturity** (CONCEPT → DEVELOPMENT → DEMONSTRATED →
CONTRACTED → OPERATIONAL → SCALED).

E c'e' il giro **esporta → classifica altrove → importa**: l'applicazione
compone il prompt da dare a un LLM, portandosi dietro i valori ammessi e i temi
gia' esistenti, e reimporta il JSON classificato creando i temi mancanti.

*Verifica passata dal vivo: tassonomia a due livelli col terzo rifiutato;
aggiunta di `"nvda, mu; tsm, ZZQX, no@buono, MU"` che rende quattro esiti
distinti (aggiunti, gia' presenti, scartati perche' malformati, sconosciuti
perche' non nell'universo) invece di un silenzio; i conteggi dell'ambito
comprensivi dei figli; la watchlist unita all'universo che mostra settore e
capitalizzazione; la copia SQLite cancellata e riallineata da sola alla
rilettura; la freschezza chiesta per categoria che distingue `price` da
`profile`; lo storico che conserva l'aggiunta anche dopo la rimozione.*

**Blocco 4 — Frontend, scheletro. FATTO il 2026-08-30, 108 test verdi.**
Vite 8 + Svelte 5 + Bootstrap 5.3 (solo CSS), tema chiaro/scuro, layout,
chiamate API con l'inviluppo `{success, data, error}` scartato in un punto solo.

Tre pagine: **Universo** (stato, copertura dichiarata, filtri), **Watchlist**
(schede nello stile del thematic-equity-monitor, editabili) e **Operazioni**,
che e' la regola 1 resa visibile — cosa sta girando, il pulsante per fermarlo,
la cronologia dei lavori e il registro delle chiamate con la provenienza.

**Flask serve anche il build**, cosi' in uso reale il processo resta uno. Se il
build non c'e', la risposta lo dice col comando da lanciare invece di un 404
muto. Il router e' trenta righe: SvelteKit porterebbe il suo, ma anche un
processo Node accanto a Flask.

*Verifica passata dal vivo, col server vero: `/`, `/watchlist` e `/operazioni`
servite dalla SPA e `/api/inventata` che resta un 404 parlante; universo
ricostruito da zero in 5 s dalla pagina; sette titoli aggiunti con gli scarti
dichiarati; il giro completo prompt → JSON classificato → import, che ha creato
dieci temi su due livelli e assegnato profilo e maturity a tutti e sette.*

**Blocco 5 — Glossario. FATTO il 2026-08-30, 119 test Python + 11 JavaScript.**
Backend copiato (171 termini in `data/glossary.json`, curati a mano e mai
riscritti dal programma). Frontend in Svelte: rilevatore keyword, pannello
laterale, pagina di consultazione, interruttore globale ricordato.

**Il requisito nuovo e' soddisfatto con un controllo, non con una regola
scritta.** La sottolineatura passa dal componente `Testo`, e un test della
suite legge i sorgenti del frontend: ogni componente o usa `Testo`, o compare
nell'elenco delle eccezioni **col suo motivo**. Aggiungere una pagina nuova fa
fallire la suite finche' qualcuno non sceglie fra le due cose — ed e' cio' che
nel vecchio tradash mancava, dove usavano `GlossaryText` 21 file su tutto il
frontend e la copertura parziale sembrava completa.

Il rilevatore sta in `lib/rilevatore.js`, senza stato e senza Svelte — la
stessa separazione che nel backend tiene `domain/` senza I/O — e ha undici test
suoi: parole dentro altre parole, sigle, frasi lunghe che ne contengono di
corte, e l'espressione regolare con stato che salta pezzi alla seconda chiamata.

*Verifica passata dal vivo: 171 termini serviti, la lettura registrata con
provenienza `local`, i rimandi di `roic` che puntano a termini esistenti.*
*Difetto trovato nei dati copiati: cinque rimandi puntavano a termini mai
scritti — `volatility`, `market_tailwind`, `sector_leadership`. Tolti, e i tre
concetti restano da scrivere se li vuoi.*

**La scheda titolo — attraversa i Blocchi 6, 7 e 8.** Non e' un blocco a se':
e' la pagina che consuma tutti gli altri, e finirla prima dell'8 e' impossibile.
Ma aspettare l'8 per vederla vorrebbe dire restare per settimane senza il posto
dove cliccare da watchlist e universo. Quindi cresce a strati:

| In quale blocco | Cosa le si aggiunge |
|---|---|
| 6 | il guscio: intestazione col profilo, grafico, prezzi, e le sezioni che dichiarano di essere vuote |
| 7 | fondamentali, filing e news, con `as_of` |
| 8 | le sette analisi, ognuna nella sua sezione |

**Il precedente da non ripetere sono le sue 1.342 righe.** Nel vecchio tradash
`app/ticker/[symbol]/page.tsx` montava una ventina di componenti e sapeva tutto:
grafico, pannello fondamentali, alberi di filing e news, KPI operativi, contesto
di mercato, salute, calendario dei rendimenti, schede dell'advisor. Qui dev'essere
un **guscio piu' sezioni**, dove ogni blocco aggiunge la sua senza toccare le
altre — e una sezione non ancora costruita dice "non ancora disponibile" invece
di non esserci (regola 5).

---

**Blocco 6 — Grafici. FATTO il 2026-08-30, 130 test verdi.**
`lightweight-charts` pilotato dai nodi indicatore, con `domain/indicators.py`
(copiato: 456 righe, topo-sort sul grafo) e `lib/indicators.ts` (copiato: la
tabella condivisa fra pannello e disegno). Pannelli, overlay, e impostazioni per
ticker in `data/grafici.json` — tue, quindi in un file come la watchlist.
**Piu' il guscio della scheda titolo**, che dichiara le sezioni dei blocchi 7 e
8 invece di farle mancare in silenzio.

*Difetto trovato dal vivo e chiuso: gli indicatori venivano calcolati sul solo
intervallo mostrato. A un mese di grafico l'EMA50 aveva 22 valori — una "media a
50 giorni" costruita su ventidue sedute, un numero che sembra giusto e non lo e'.
Ora si calcola su tutta la storia (6.943 sedute per NVDA) e si taglia dopo.*

**Blocco 7 — Matematica e as_of. IN PARTE, il 2026-08-30, 146 test verdi.**

*Fatto:* `domain/publication_dates.py` (copiato e **reso puro**: le date di
deposito gliele passa chi chiama, invece di andarsele a prendere),
`domain/prospetti.py`, `domain/statements_math.py`, `data/depositi.py` che
costruisce la mappa dei depositi da Defeatbeta. Nella scheda titolo sono
arrivati **fondamentali, filing e news**, col taglio `as_of` e la **base del
taglio dichiarata** in ogni risposta.

*Misurato dal vivo, e meglio del vecchio sistema:* AAPL 20/20 periodi con date
di deposito reali, CIEN 20/20 (era 11/17), RACE 7/20 — che infatti risulta
`mixed`, ed e' esattamente cio' che `truncation_basis` serve a dire.

*Non fatto, e non per dimenticanza:* `point_in_time_service`, `capm`,
`technical_features` e `feature_engine` non sono matematica pura — importano
`fundamentals_service`, `market_data`, `fq_service`, `forward_service`, cioe'
**servizi del Blocco 8**. Portarli adesso vorrebbe dire portarsi dietro mezzo
Blocco 8 travestito da `domain/`. Vanno con l'8, e la pagina di confronto
point-in-time con loro.

*Da chiudere ancora:* `before` su `get_recent_filings` — qui il taglio dei
filing e' esatto e usato, ma la lezione vale per ogni parametro nuovo.
Comprende la **pagina di confronto point-in-time**: ricostruire l'analisi a una
data passata e confrontarla con l'evoluzione reale (`compare_point_in_time`,
`fair_value_history`). `truncation_basis()` deve continuare a dichiarare se un
periodo poggia su una data di deposito reale o su una stima — la copertura varia
moltissimo (AAPL 17/17 periodi reali, CIEN 11/17, RACE 4/16) e sei periodi su
una stima, invisibili, erano proprio sul ticker su cui la fase era stata
verificata dal vivo.
*Da chiudere qui: `before` su `get_recent_filings` era esposto e nessuno dei 9
chiamanti di produzione lo passava.*

**Blocco 8 — Tutte le analisi. IN PARTE, il 2026-08-30, 183 test verdi.**

*Fatto:* i **cinque segnali fondamentali** F1-F5, deterministici, con le soglie
del vecchio sistema e la copertura dichiarata a parte. L'**infrastruttura** per
i modelli: `core/llm.py`, dove ogni chiamata lascia due righe — una in `calls`
come tutte, una in `llm_calls` col modello, i token e **il costo**. Il
**registro dei sette metodi**, dove quelli non ancora costruiti restano in
elenco con scritto cosa manca a ciascuno. E la prima analisi che gira davvero,
la **lettura tecnica**.

*La scelta di disegno che conta:* **niente loop di strumenti.** Nel vecchio
sistema l'analisi era una conversazione in cui il modello chiamava tool fino a
decidere di aver finito, e il contesto riaccodato a ogni tentativo cresceva
senza limite. Qui si calcola prima e si chiede dopo, una volta sola: il modello
riceve i numeri gia' pronti e puo' solo sintetizzarli. La regola ferrea del
vecchio prompt — *"non ricalcolare NULLA"* — diventa strutturale invece che
raccomandata, perche' senza strumenti da chiamare non ha modo di inventare un
numero.

**Le metriche di Defeatbeta si usano.** `Ticker` porta un'ottantina di metodi
che calcolano ROE, ROIC, margini, debito netto, multipli e — cosa che il vecchio
tradash non aveva — i **confronti di settore**. Passano da
`defeatbeta.metrica()`, quindi dal registro con la provenienza misurata. Le
serie si comprimono in `domain/pannello.py` prima di arrivare a un modello:
`ttm_pe` da solo ha 6.875 righe, e mandarle intere costerebbe ~200.000 token
per un numero che si guarda alla fine.

*Fatta anche la seconda analisi:* la **qualita' fondamentale**, che mette
insieme i cinque segnali e nove metriche col confronto di settore. Su NVDA
misurato: ROE 33,1%, **il 45% sotto la sua industria**, con i margini invece
sopra — la lettura che il vecchio sistema non sapeva produrre per undici ticker
su diciotto.

*Non fatto, e ognuno sa perche':* la **qualitativa** aspetta le quattro fasi (i
documenti si possono gia' preparare: la scheda dice quali servono e con che nome
salvarli); la **forward** aspetta il suo pacchetto (3.295 righe mai girate);
l'**earnings review** la tabella delle trascrizioni; il **verdetto** gli altri
metodi; lo **spin-off** e' il candidato a essere tolto.

*Non verificato dal vivo:* la lettura tecnica non e' mai stata eseguita con un
modello vero — servono la chiave e la decisione di spendere. La memoria dice che
per i prompt il mock non basta, e questo resta l'unico pezzo del sistema che
non ho potuto guardare girare.

L'elenco completo, cosi' com'e' nel vecchio sistema:

| Analisi | Natura | Prompt / motore |
|---|---|---|
| Fondamentale (FQ) | deterministica + veti LLM | `fundamental_quality/` (18 moduli) |
| **Forward analysis** | **pipeline deterministica, NON conversazione** | `forward_analysis/` (11 moduli, 3295 righe) |
| Qualitativa (report a 10 sezioni) | 4 fasi LLM bounded | `agent_qualitative_phase1..4` |
| Tecnica | deterministica + lettura LLM | `agent_technical_analysis_system.txt` |
| Earnings review **rifondato** | LLM sulle trascrizioni | `stock_earning_call_transcripts` (6.495 simboli) |
| Spin-off | LLM | `agent_spin_off_analysis_system.txt` |
| Verdetto finale | sintesi cross-dimensionale | `agent_final_verdict_system.txt` |

**Le analisi sono SETTE. Due decisioni prese il 29/08 dopo aver misurato l'uso
reale sul DB:**

- **`good_drawdown` esce come metodo LLM.** Non per scarso uso (7 referti, piu'
  di technical_analysis e final_verdict) ma perche' legge
  `get_good_drawdown_snapshot`: era il **lettore del GD Monitor**, il servizio
  che buttiamo. Tolto il monitor resta senza dato. Il concetto torna come
  **feature tecnica deterministica** — profondita', durata e recupero del
  drawdown calcolati dai prezzi. Niente LLM, niente servizio, e una risposta
  finalmente verificabile a "basato su cosa?".
- **`earnings_review` si rifonda sulle trascrizioni.** Aveva 1 referto e 3
  chiamate in tutta la vita del sistema, e il suo input principale
  (`get_earnings_surprise_history`, 114 chiamate Finnhub) sparisce con Finnhub.
  Ricostruito sulle **earnings call** — guidance dichiarata a voce, domande
  degli analisti — e' un prodotto diverso e migliore. Portato com'era, moriva.
- `spin_off_analysis` resta nell'elenco ma con zero referti storici: e' il
  candidato successivo a essere tolto se non lo usi.

Tre vincoli gia' pagati con giri veri, da non riscoprire:

- **La qualitativa e' spezzata in 4 chiamate apposta.** Con tutto in un loop
  solo (fino a 15 iterazioni) il contesto riaccodato a ogni retry cresceva
  senza limite: una run e' rimasta "running" 20+ minuti senza una sola risposta
  HTTP nuova prima che il watchdog la marcasse "hung". Ogni fase ha scope
  ristretto e **non eredita la cronologia** delle altre.
- **Forward analysis non ha un system prompt di loop, e non deve averlo.** E'
  una pipeline deterministica; le sue chiamate LLM stanno dentro il pacchetto
  di dominio, coi propri tre prompt. Un settimo file in `prompts/` sarebbe un
  prompt che nessuno carica.
- **Haiku fallisce le fasi 1-4** (solo compressione e triage): su Q ha prodotto
  un submit invalido bruciando $0,24, Sonnet ha chiuso a $0,99. E la verifica e'
  **dal vivo**: per i prompt il mock non basta.

Blocco che si ferma invece di degradare: `qualitative_filing_analysis` e le sue
4 fasi hanno come **fonte primaria** i documenti SEC. Senza le sezioni del
filing non producono un'analisi povera: non ne producono nessuna. L'avvio si
ferma. Gli altri metodi leggono dati gia' calcolati e usano i filing come
complemento facoltativo — bloccarli sarebbe sbagliato.

**Blocco 9 — Scanner sul passato. FATTO il 2026-08-30, 158 test verdi.**
Solo su Defeatbeta, con la cache dei byte che rende gratis la seconda passata,
e ogni scansione dentro il registro: si vede in `/api/ops/active` e si ferma.

`domain/drawdown.py` e' il **good_drawdown promesso come feature deterministica**
— profondita', durata e recupero calcolati dai prezzi, senza LLM e senza
servizio che gira per conto suo. `domain/scansione.py` decide, e ogni titolo
trovato porta **il perche'**: "sette titoli" costringe a fidarsi, e "basato su
cosa?" nel vecchio sistema non aveva risposta.

*Verifica passata dal vivo: 51 tecnologici sopra i 100 miliardi esaminati, 17
trovati fra scesi almeno il 15% e che hanno recuperato almeno il 20% — MU a
-23,1% con il 41% recuperato in 45 sedute sotto il massimo, ognuno con la
propria riga di spiegazione. Una scansione fermata a meta' conserva quello che
aveva trovato: e' meno di quanto chiesto, non niente.*

---

## Riepilogo

Nuovo progetto (rewrite completo). Nessuna riga del vecchio tradash arriva qui
senza essere elencata sopra.
