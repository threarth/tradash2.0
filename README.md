# tradash2.0

Riscrittura di tradash. Perimetro **solo USA**, **fonte unica Defeatbeta**,
niente servizi che partono da soli.

## Comandi

```bash
cd backend
uv venv --python 3.13
uv pip install --python .venv/bin/python -r requirements.txt

.venv/bin/python -m pytest -q     # la suite
.venv/bin/python app.py           # server di sviluppo su :5001
```

## Documenti

- **`PIANO.md`** — il contratto di lavoro: regole, cosa si salva dal vecchio
  tradash, cosa si riscrive, cosa non si porta, e i 10 blocchi in ordine di
  dipendenza. Da leggere per primo.
- `docs/COPERTURA_DEFEATBETA.md` — cosa copre e cosa non copre Defeatbeta
  rispetto a tutte le analisi, misurato dal vivo.

## Stato

| Blocco | Stato |
|---|---|
| 0 — Fondamenta (registro lavori, log chiamate, freschezza) | **fatto**, 19 test verdi |
| 1-9 | da fare |

## La regola che governa tutto

Ogni lavoro batch o singolo: gestibile, fermabile, loggato. Ogni chiamata di
rete, di API e **ogni uso di cache**: loggato. Nessun percorso di codice puo'
fare rete o lavoro lungo senza passare da `core/registry.py` e `core/calls.py`.
