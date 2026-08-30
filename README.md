# tradash2.0

Riscrittura di tradash. Perimetro **solo USA**, **fonte unica Defeatbeta**,
niente servizi che partono da soli.

## Comandi

### Backend

```bash
cd backend
uv venv --python 3.13
uv pip install --python .venv/bin/python -r requirements-dev.txt

.venv/bin/python -m pytest -q       # la suite (108 test, rete spenta)
.venv/bin/python -m pytest -q -m network   # i test che escono davvero
.venv/bin/ruff check .              # il linter
.venv/bin/python app.py             # server su :5001, serve anche la SPA
.venv/bin/python manage.py check    # dove sta il database e cosa contiene
.venv/bin/python manage.py rebuild  # lo ricostruisce (chiede conferma a mano)
```

### Frontend

```bash
cd frontend
pnpm install
pnpm build     # produce dist/, che Flask serve: un solo processo
pnpm dev       # sviluppo con ricarica a caldo su :5173, /api va a Flask
pnpm test      # i test della logica pura (rilevatore del glossario)
```

In uso reale gira **solo Flask**: niente SvelteKit, quindi niente processo Node
accanto. In sviluppo si tengono aperti tutti e due perche' Vite ricarica a caldo.

`requirements.txt` contiene solo cio' che serve a far girare l'applicazione;
`requirements-dev.txt` aggiunge gli strumenti di sviluppo. Chi installa per
usare tradash2.0 non si ritrova pytest addosso.

## I test girano in fase di sviluppo, mai in fase d'uso

La separazione e' strutturale, non una convenzione:

- **la rete e' spenta a livello di socket** per ogni test — sotto qualunque
  libreria, quindi nessun mock dimenticato puo' uscire. Chi la vuole davvero la
  chiede con `@pytest.mark.network`, e allora si vede nel sorgente;
- **il database dell'uso reale e' irraggiungibile dalla suite**: `core/db.py`
  si rifiuta di aprirlo mentre pytest gira;
- **il codice di produzione non sa che i test esistono** — nessun ramo
  `if TESTING:`, nessun import verso `tests/`. Due test lo verificano leggendo
  i sorgenti;
- **`create_app()` fa due cose**: applica lo schema e registra i blueprint. Nel
  vecchio sistema faceva anche un UPDATE su tutti gli universi, tre ALTER TABLE
  e un ripopolamento di temi, a ogni costruzione dell'app.

## Il database

**Niente migrazioni.** Lo schema sta tutto in `backend/core/schema.sql` e si
applica a ogni avvio: aggiungere una tabella vuol dire scrivere il `CREATE`
li' dentro. Il database e' una vista ricostruibile, non un archivio da salvare.
Quando una tabella cambia forma, `ensure_schema()` se ne accorge e dice di
lanciare `manage.py rebuild` invece di lasciar passare un errore di SQLite.

**Con un'eccezione: la watchlist.** E' l'unica cosa che non si ricostruisce, e
per questo la sua fonte di verita' e' `backend/data/watchlist.json`, leggibile e
correggibile a mano. SQLite ne tiene solo una copia di lavoro, che il rebuild
puo' cancellare senza danno. Il file non e' in git: **il backup e' copiarlo.**

## Documenti

- **`PIANO.md`** — il contratto di lavoro: regole, cosa si salva dal vecchio
  tradash, cosa si riscrive, cosa non si porta, e i 10 blocchi in ordine di
  dipendenza. Da leggere per primo.
- **`docs/DECISIONI.md`** — ogni decisione con il difetto misurato che l'ha
  causata: perimetro, stack, i quattro archivi, perche' niente migrazioni,
  perche' i test sono isolati per costruzione, le trappole di Defeatbeta.
- `docs/COPERTURA_DEFEATBETA.md` — cosa copre e cosa non copre Defeatbeta
  rispetto a tutte le analisi, misurato dal vivo.

## Stato

| Blocco | Stato |
|---|---|
| 0 — Fondamenta (registro lavori, log chiamate, freschezza, schema, isolamento test) | **fatto** |
| 1 — Defeatbeta, punto unico di lettura con provenienza misurata | **fatto** |
| 2 — Universo derivato: 11.256 titoli, costruzione fermabile | **fatto** |
| 3 — Watchlist e tag: verita' in un file, temi multipli, profilo e maturity | **fatto** |
| 4 — Frontend, scheletro: Svelte 5 + Vite + Bootstrap CSS | **fatto** |
| 5 — Glossario: 171 termini, sottolineatura sistematica per costruzione | **fatto** |
| 6-9 | da fare |

119 test Python in meno di due secondi (piu' 2 che escono davvero in rete e
girano solo se richiesti) e 11 test JavaScript sul rilevatore del glossario.

## La regola che governa tutto

Ogni lavoro batch o singolo: gestibile, fermabile, loggato. Ogni chiamata di
rete, di API e **ogni uso di cache**: loggato. Nessun percorso di codice puo'
fare rete o lavoro lungo senza passare da `core/registry.py` e `core/calls.py`.
