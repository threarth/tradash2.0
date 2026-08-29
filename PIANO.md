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

Le regole della tassonomia sono decisioni gia' prese il 27/08 sul vecchio
sistema, riportate qui: **un solo tag per titolo**, **due livelli**, il
**sotto-ambito implica il padre** (chi guarda "Semiconductor" vede anche
"Semiconductor / Memory"), e **cancellare un tag non cancella titoli** — i
membri tornano senza tag.

*Verifica passata dal vivo: tassonomia a due livelli col terzo rifiutato;
aggiunta di `"nvda, mu; tsm, ZZQX, no@buono, MU"` che rende quattro esiti
distinti (aggiunti, gia' presenti, scartati perche' malformati, sconosciuti
perche' non nell'universo) invece di un silenzio; i conteggi dell'ambito
comprensivi dei figli; la watchlist unita all'universo che mostra settore e
capitalizzazione; la copia SQLite cancellata e riallineata da sola alla
rilettura; la freschezza chiesta per categoria che distingue `price` da
`profile`; lo storico che conserva l'aggiunta anche dopo la rimozione.*

**Blocco 4 — Frontend, scheletro.** Vite + Svelte + Bootstrap CSS, tema
chiaro/scuro, layout, chiamate API con l'inviluppo `{success, data, error}`.

**Blocco 5 — Glossario.** Backend gia' pronto (copiato). Frontend in Svelte:
rilevatore keyword, hover, pannello laterale, toggle globale persistito.
**Requisito nuovo rispetto al vecchio:** la sottolineatura dev'essere
**sistematica** — applicata dal componente di testo di default, non aggiunta a
mano dove qualcuno si ricorda. Nel vecchio tradash solo 21 file su tutto il
frontend usavano `GlossaryText`: copertura parziale che sembrava completa.

**Blocco 6 — Grafici.** `lightweight-charts` pilotato dai nodi indicatore.
Pannelli, overlay, impostazioni per ticker.

**Blocco 7 — Matematica e as_of.** Porting di `domain/`, con i test.
Comprende la **pagina di confronto point-in-time**: ricostruire l'analisi a una
data passata e confrontarla con l'evoluzione reale (`compare_point_in_time`,
`fair_value_history`). `truncation_basis()` deve continuare a dichiarare se un
periodo poggia su una data di deposito reale o su una stima — la copertura varia
moltissimo (AAPL 17/17 periodi reali, CIEN 11/17, RACE 4/16) e sei periodi su
una stima, invisibili, erano proprio sul ticker su cui la fase era stata
verificata dal vivo.
*Da chiudere qui: `before` su `get_recent_filings` era esposto e nessuno dei 9
chiamanti di produzione lo passava.*

**Blocco 8 — Tutte le analisi.** Nessuna esclusa. L'elenco completo, cosi'
com'e' nel vecchio sistema:

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

**Blocco 9 — Scanner sul passato.** Solo su Defeatbeta, cache il piu' possibile,
ogni scan con run_id e Stop.

---

## Riepilogo

Nuovo progetto (rewrite completo). Nessuna riga del vecchio tradash arriva qui
senza essere elencata sopra.
