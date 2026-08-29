"""
calls.py — il log delle chiamate, leggibile dal frontend.
# feat (Blocco 0): "ogni api call loggata, ogni chiamata di rete pure, ogni uso di cache idem".
"""
from flask import Blueprint, request

import config
from api import fail, ok
from core import calls as call_log

bp = Blueprint("calls", __name__, url_prefix="/api/calls")


@bp.get("")
def recent():
    """Ultime chiamate registrate. Filtri opzionali: `provider`, `run_id`, `limit`."""
    limite_grezzo = request.args.get("limit", config.CALLS_PAGE_LIMIT_DEFAULT)
    try:
        limite = int(limite_grezzo)
    except (TypeError, ValueError):
        return fail(f"limit non e' un numero: {limite_grezzo!r}")

    if limite < 1 or limite > config.CALLS_PAGE_LIMIT_MAX:
        return fail(f"limit deve stare fra 1 e {config.CALLS_PAGE_LIMIT_MAX}")

    return ok(call_log.recent(
        limit=limite,
        provider=request.args.get("provider"),
        run_id=request.args.get("run_id"),
    ))


@bp.get("/summary")
def summary():
    """Quante chiamate per provenienza: rete, cache, locale, non dichiarate."""
    conteggi = call_log.summary()
    return ok({
        "per_provenienza": conteggi,
        "non_dichiarate": conteggi.get(call_log.SOURCE_UNDECLARED, 0),
    })
