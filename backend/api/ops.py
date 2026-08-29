"""
ops.py — cosa sta girando, e come fermarlo.
# feat (Blocco 0): l'endpoint che nel vecchio sistema non vedeva il download da 500 ticker.
"""
from flask import Blueprint

from api import ok, fail, HTTP_NOT_FOUND
from core import registry
from core.db import db_read

bp = Blueprint("ops", __name__, url_prefix="/api/ops")

# Quanti lavori conclusi mostra la cronologia.
HISTORY_LIMIT = 50


@bp.get("/active")
def active():
    """I lavori vivi adesso. Lista vuota significa: non sta girando nulla."""
    return ok(registry.active())


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
