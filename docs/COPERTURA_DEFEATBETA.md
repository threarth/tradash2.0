# Copertura Defeatbeta rispetto a tutte le analisi

Verificato dal vivo il 2026-08-29 interrogando i parquet
(`Data Update Time 2026-08-29T05:06:00Z`).

## I dataset sono 15, non 12

L'elenco reale, dall'API HuggingFace:

```
stock_profile · stock_prices · stock_statement · stock_shares_outstanding
stock_tailing_eps · stock_earning_calendar · stock_sec_filing · stock_news
stock_officers · stock_dividend_events · stock_split_events
stock_earning_call_transcripts   ← non censito prima
stock_revenue_breakdown          ← non censito prima
daily_treasury_yield             ← non censito prima
exchange_rate                    ← non censito prima
```

Tre di questi cambiano cosa si puo' costruire.

## Cosa c'e', e basta

| Serve a | Dato | Dataset |
|---|---|---|
| FQ, DCF, reverse DCF | **166 voci di bilancio** (72 stato patrimoniale, 55 flussi, 39 conto economico) | `stock_statement` |
| Tecnica, scanner, drawdown, grafici | OHLCV | `stock_prices` |
| Universo, profilo | 11.256 simboli con settore/industria/paese/dipendenti | `stock_profile` |
| News | titolo, editore, testo per paragrafi | `stock_news` |
| Calendario earnings | data, orario, **nome societa'** | `stock_earning_calendar` |
| Elenco filing | accession, form_type, filing_date, **filing_url** | `stock_sec_filing` |
| Diluizione, split, dividendi, dirigenti | | 4 dataset dedicati |

Le 166 voci coprono tutto quello che serve senza ricostruzioni:
`invested_capital` (ROIC diretto), `free_cash_flow`, `capital_expenditure`,
`stock_based_compensation`, `interest_expense`, `ebit`, `ebitda`,
`research_and_development`, `total_debt`, `net_debt`, `working_capital`,
`tangible_book_value`.

## Cosa c'e' in PIU' di quello che tradash aveva

| Dato | Dataset | Cosa abilita |
|---|---|---|
| **Trascrizioni delle earnings call**, con speaker e numero di paragrafo, dal 2006 | `stock_earning_call_transcripts` | fonte qualitativa che tradash non ha mai avuto: la guidance dichiarata a voce, le domande degli analisti |
| **Ricavi per geografia e per segmento** | `stock_revenue_breakdown` | analisi di segmento — **ma vedi l'avvertenza sotto: copre 367 simboli su 11.256** |
| **Curva Treasury 1m→30 anni, giornaliera dal 1990** | `daily_treasury_yield` | tasso privo di rischio **per data**: il DCF ricostruito a una data passata usa il tasso di quel giorno, non quello di oggi |

L'ultimo e' un miglioramento diretto dell'as_of: era una delle porte da cui
rientrava il futuro in una ricostruzione point-in-time.

### Copertura misurata dei tre dataset nuovi

| Dataset | Simboli coperti | Dato piu' recente |
|---|---|---|
| `stock_earning_call_transcripts` | **6.495** su 11.256 (58%) | 2026-08-28 (ieri) |
| `stock_news` | **8.545** su 11.256 (76%) | 2026-08-29 (oggi) |
| `stock_revenue_breakdown` | **367** su 11.256 (**3%**) | 2026-09-30 |

**Trascrizioni e news reggono: copertura ampia e freschezza di un giorno.**

**`stock_revenue_breakdown` NO: 3% e' una curiosita', non una fonte.** Va usato
solo dove c'e', dichiarando l'assenza con motivo negli altri casi (regola 5).
Nessuna analisi puo' dipenderne.

**E ha una trappola:** il suo `report_date` piu' recente e' **2026-09-30**, una
data nel FUTURO rispetto a oggi (29/08), con `period_type = trailing`. Un
filtro `report_date <= as_of` scritto senza pensarci lascia entrare periodi che
non erano ancora chiusi. E' esattamente la porta da cui il look-ahead rientra:
**il futuro non si conta per punti del piano, si conta per porte.**

## Cosa MANCA — i tre buchi veri

| Manca | Chi lo usava | Cosa se ne fa |
|---|---|---|
| **Il TESTO dei filing** (c'e' solo `filing_url`) | qualitativa a 4 fasi, l'analisi piu' usata (46 referti) | si scarica da sec.gov, seguendo l'URL che Defeatbeta stesso fornisce |
| **Stime analisti / earnings surprise** | `get_earnings_surprise_history`, `revision_trend` (input di FQ) — erano 114 chiamate Finnhub | si cambia il dato richiesto: non "sorpresa contro consenso" ma "andamento contro la guidance dichiarata", presa dalle trascrizioni |
| **Insider / Form 4** | `get_insider_transactions` — era yfinance | si dichiara assente con motivo (regola 5), oppure si toglie il tool |

E due che **non sono buchi ma adattamenti**, entrambi in meglio:

- **Peer**: non c'e' una classificazione pronta, ma settore e industria ci sono
  per tutti gli 11.256 simboli. I peer si derivano a query. Il vecchio sistema
  li prendeva da Finnhub + classificazione LLM e copriva 7 ticker su 18.
- **Beta**: non c'e' come campo, si calcola dai prezzi contro l'indice.

## Sul significato di "fonte unica"

Scaricare un 10-K da `sec.gov` seguendo l'URL che Defeatbeta ci consegna **non
e' un secondo provider**: e' andare a prendere il documento pubblico che il
dataset indicizza. "Fonte unica" significa **un solo fornitore di dati di
mercato**, non "mai scaricare un documento pubblico".

La differenza pratica: sec.gov non ha chiavi, non ha crediti, non ha piani a
pagamento e non e' una dipendenza commerciale. Va comunque loggato come ogni
altra chiamata di rete, e ha le sue regole di user-agent da rispettare.
