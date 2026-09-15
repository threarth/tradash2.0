"""
ops.py — cosa sta girando, e come fermarlo.
# feat (Blocco 0): l'endpoint che nel vecchio sistema non vedeva il download da 500 ticker.
"""
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint

import config
from api import HTTP_NOT_FOUND, fail, ok
from core import registry
from core.db import db_read
from data import allarmi

# Le cartelle che contengono il codice dell'applicazione. Se una di queste e'
# piu' recente dell'avvio del processo, il server sta servendo codice vecchio.
CARTELLE_DEL_CODICE = ("api", "core", "data", "domain")

AVVIATO_IL = datetime.now(UTC).isoformat(timespec="seconds")


bp = Blueprint("ops", __name__, url_prefix="/api/ops")

# Quanti lavori conclusi mostra la cronologia.
HISTORY_LIMIT = 50


@bp.get("/active")
def active():
    """I lavori vivi adesso. Lista vuota significa: non sta girando nulla."""
    return ok(registry.active())


@bp.get("/processo")
def processo():
    """Da quando gira questo processo, e con quale codice.

    Il difetto che chiude: il server di sviluppo parte con `use_reloader=False`,
    quindi **non si accorge delle modifiche**. Un'analisi qualitativa e' andata
    a sbattere due volte nello stesso guasto — la seconda dopo che il guasto era
    gia' corretto sul disco — e le prime due fasi erano gia' state pagate
    entrambe le volte. Un processo che gira con codice vecchio non lo dice da
    solo: ora lo dice qui.
    """
    return ok({
        "avviato_il": AVVIATO_IL,
        "codice_del": _ultima_modifica(),
        "aggiornato": _ultima_modifica() <= AVVIATO_IL,
        "nota": ("il server non si ricarica da solo: se il codice e' piu' "
                 "recente dell'avvio, riavvialo"),
    })


def _ultima_modifica() -> str:
    """Quando e' stato toccato l'ultimo sorgente dell'applicazione."""
    radice = Path(config.BASE_DIR)
    piu_recente = max(
        (f.stat().st_mtime for cartella in CARTELLE_DEL_CODICE
         for f in (radice / cartella).rglob("*.py")),
        default=0.0,
    )
    return datetime.fromtimestamp(piu_recente, UTC).isoformat(timespec="seconds")


@bp.get("/freschezza")
def freschezza():
    """Cosa e' invecchiato. Non ricostruisce niente: lo dice e basta.

    Sta in `ops` perche' e' la regola 1 vista dall'altro lato: quella pagina
    mostra cosa STA girando, questo endpoint cosa DOVREBBE girare e non gira —
    e non girera' finche' non lo chiedi tu.

    E' una lettura di SQLite e di un file: si puo' chiedere all'apertura di una
    pagina senza violare la regola 2.
    """
    return ok(allarmi.stato())


@bp.post("/stop/<run_id>")
def stop(run_id: str):
    """Chiede a un lavoro di fermarsi."""
    consegnato, motivo = registry.request_stop(run_id)
    if not consegnato:
        return fail(motivo, HTTP_NOT_FOUND)
    return ok({"run_id": run_id, "stop_requested": True})


@bp.get("/history")
def history():
    """Gli ultimi lavori conclusi, con il loro esito."""
    with db_read() as conn:
        righe = conn.execute(
            "SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?", (HISTORY_LIMIT,)
        ).fetchall()
    return ok([dict(r) for r in righe])
