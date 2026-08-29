# tradash2.0

Riscrittura di tradash. Perimetro **solo USA**, **fonte unica Defeatbeta**,
niente servizi che partono da soli.

## Comandi

```bash
cd backend
uv venv --python 3.13
uv pip install --python .venv/bin/python -r requirements.txt

.venv/bin/python -m pytest -q       # la suite (41 test, rete spenta)
.venv/bin/python app.py             # server di sviluppo su :5001
.venv/bin/python manage.py check    # dove sta il database e cosa contiene
.venv/bin/python manage.py rebuild  # lo ricostruisce (chiede conferma a mano)
```

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
| 0 — Fondamenta (registro lavori, log chiamate, freschezza, schema, isolamento test) | **fatto**, 41 test verdi |
| 1-9 | da fare |

## La regola che governa tutto

Ogni lavoro batch o singolo: gestibile, fermabile, loggato. Ogni chiamata di
rete, di API e **ogni uso di cache**: loggato. Nessun percorso di codice puo'
fare rete o lavoro lungo senza passare da `core/registry.py` e `core/calls.py`.
