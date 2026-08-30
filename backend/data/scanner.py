"""
scanner.py — cercare titoli che soddisfano dei criteri, sul passato.
# feat (Blocco 9): un lavoro lungo, quindi tracciato e fermabile.

Il vecchio tradash aveva scanner che nessuno vedeva partire e che non si
potevano fermare. Qui ogni scansione e' un lavoro del registro: si vede in
`/api/ops/active`, si ferma con Stop, e ogni titolo letto lascia la sua riga
nel log delle chiamate con la provenienza.

**Sul passato** vuol dire due cose diverse, e vanno tenute distinte:

* i prezzi si tagliano alla data chiesta — quello e' un fatto, la data di
  chiusura e' proprio la colonna che abbiamo;
* i FONDAMENTALI, se un giorno entreranno nei criteri, andranno tagliati sul
  DEPOSITO e non sulla fine periodo, con `domain/publication_dates.py`.
  Oggi i criteri guardano solo i prezzi, e questa nota esiste perche' il primo
  criterio fondamentale non nasca sbagliato.
"""
import logging
import queue
import threading

import config
from core import registry
from core.db import db_read
from data import defeatbeta
from domain import scansione

logger = logging.getLogger(__name__)

JOB_KIND = "scanner"

# Ogni quanto la sentinella controlla se e' stato chiesto lo Stop.
INTERVALLO_CONTROLLO_STOP_S = 0.25

# Quanto si aspetta che il lavoro dichiari il proprio run_id.
ATTESA_AVVIO_S = 5.0

# Gli esiti di una scansione, tenuti in memoria: sono il risultato di UN lavoro,
# non un dato da conservare. Chi li vuole conservare li esporta.
_esiti: dict[str, dict] = {}
_lucchetto = threading.Lock()


def _candidati(filtri: dict) -> list[str]:
    """I simboli su cui scandagliare, presi dall'universo con i suoi filtri.

    Partire dall'universo e non dalla watchlist e' il senso di uno scanner: si
    cerca fra i titoli che NON stai gia' guardando.
    """
    condizioni, parametri = [], []
    if filtri.get("sector"):
        condizioni.append("sector = ?")
        parametri.append(filtri["sector"])
    if filtri.get("min_market_cap") is not None:
        condizioni.append("market_cap >= ?")
        parametri.append(float(filtri["min_market_cap"]))
    if filtri.get("min_volume") is not None:
        condizioni.append("avg_volume_30d >= ?")
        parametri.append(float(filtri["min_volume"]))

    dove = f"WHERE {' AND '.join(condizioni)}" if condizioni else ""
    limite = min(int(filtri.get("limite") or config.SCANNER_TITOLI_MAX),
                 config.SCANNER_TITOLI_MAX)

    with db_read() as conn:
        righe = conn.execute(
            f"SELECT symbol FROM universe {dove} ORDER BY market_cap DESC NULLS LAST LIMIT ?",
            [*parametri, limite],
        ).fetchall()
    return [r["symbol"] for r in righe]


def _chiusure(simbolo: str, fino_a: str | None, run_id: str) -> tuple[list, list]:
    """Prezzi e volumi di un titolo, tagliati alla data. Vuoti se non ce ne sono.

    Un simbolo rotto non ferma il giro (regola 4): torna vuoto, il chiamante lo
    conta fra quelli senza dati e va avanti. Solo un guasto del PROVIDER —
    `DefeatbetaUnavailable` — interrompe, perche' quello riguarda tutti.
    """
    lettura = defeatbeta.prices(simbolo, run_id=run_id)
    if not lettura.available:
        return [], []

    frame = lettura.frame
    if fino_a:
        frame = frame[frame["report_date"].astype(str) <= fino_a]

    return frame["close"].tolist(), frame["volume"].tolist()


def _scandaglia(lavoro, simboli: list[str], criteri: dict, fino_a: str | None) -> dict:
    """Il giro vero e proprio: un titolo alla volta, fermabile a ogni passo."""
    trovati, senza_dati = [], []

    for simbolo in simboli:
        chiusure, volumi = _chiusure(simbolo, fino_a, lavoro.run_id)
        if not chiusure:
            senza_dati.append(simbolo)
        else:
            misurato = scansione.misure(chiusure, volumi)
            soddisfa, perche = scansione.valuta(misurato, criteri)
            if soddisfa:
                trovati.append({"symbol": simbolo, "perche": perche,
                                "misure": _misure_leggibili(misurato)})

        # `advance` conta il passo E controlla lo Stop: sono la stessa cosa,
        # perche' un lavoro che avanza senza guardare non si ferma mai.
        lavoro.advance(detail=f"{simbolo}: {len(trovati)} trovati")

    return {"trovati": trovati, "senza_dati": senza_dati}


def _misure_leggibili(misurato: dict) -> dict:
    """Le misure da mostrare, arrotondate. Il resto resta nel calcolo."""
    return {
        "ultimo_prezzo": misurato["ultimo_prezzo"],
        "variazione_1a": misurato["variazione_1a"],
        "sedute": misurato["sedute"],
        "drawdown": misurato["drawdown"],
    }


def _esegui(criteri: dict, filtri: dict, fino_a: str | None = None,
            consegna: queue.Queue | None = None) -> dict:
    """Una scansione, dentro il registro dei lavori. Ritorna sempre un esito esplicito."""
    simboli = _candidati(filtri)
    etichetta = f"scansione su {len(simboli)} titoli" + (f" al {fino_a}" if fino_a else "")

    esito = {"run_id": None, "completata": False, "trovati": [], "senza_dati": [],
             "esaminati": 0, "totale": len(simboli), "fino_a": fino_a,
             "motivo": "fermata prima di completare"}

    with registry.job(JOB_KIND, etichetta, total=len(simboli)) as lavoro:
        esito["run_id"] = lavoro.run_id
        if consegna is not None:
            consegna.put(lavoro.run_id)

        risultato = _scandaglia(lavoro, simboli, criteri, fino_a)
        esito.update({"completata": True, "esaminati": lavoro.done,
                      "motivo": "completata", **risultato})

    # Anche una scansione fermata a meta' conserva quello che aveva trovato: e'
    # meno di quanto chiesto, non niente.
    esito["esaminati"] = esito["esaminati"] or 0
    with _lucchetto:
        _esiti[esito["run_id"]] = esito
    logger.info("[SCANNER] %s — %d trovati su %d esaminati",
                esito["motivo"], len(esito["trovati"]), esito["esaminati"])
    return esito


def avvia(criteri: dict, filtri: dict, fino_a: str | None = None) -> str:
    """Avvia una scansione in un thread e ritorna il run_id con cui fermarla."""
    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_esegui, args=(criteri, filtri, fino_a, consegna),
                     name="scanner", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def esito(run_id: str) -> dict | None:
    """Il risultato di una scansione, se e' finita. `None` se non se ne sa niente."""
    with _lucchetto:
        return _esiti.get(run_id)
