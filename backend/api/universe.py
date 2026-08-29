"""
universe.py — l'universo dei titoli, visto dal frontend.
# feat (Blocco 2): route sottili, nessuna logica qui dentro.

La costruzione non parte mai da sola: si chiede, e mentre gira si vede in
`/api/ops/active` e si ferma con `/api/ops/stop/<run_id>` come qualunque altro
lavoro. E' la regola 2 messa in pratica — il costo di una pagina non dipende da
quanto resta aperta.
"""
import logging

from flask import Blueprint, request

import config
from api import fail, ok
from data import universe

logger = logging.getLogger(__name__)

bp = Blueprint("universe", __name__, url_prefix="/api/universe")


def _numero(nome: str, grezzo: str | None) -> tuple[float | None, str | None]:
    """Converte un parametro numerico, dicendo quale non andava bene."""
    if grezzo is None:
        return None, None
    try:
        return float(grezzo), None
    except (TypeError, ValueError):
        return None, f"{nome} non e' un numero: {grezzo!r}"


@bp.get("")
def elenco():
    """I titoli dell'universo. Filtri: `sector`, `industry`, `min_market_cap`, `search`."""
    limite, errore = _numero("limit", request.args.get("limit"))
    if errore:
        return fail(errore)
    minimo, errore = _numero("min_market_cap", request.args.get("min_market_cap"))
    if errore:
        return fail(errore)

    try:
        titoli = universe.rows(
            sector=request.args.get("sector"),
            industry=request.args.get("industry"),
            min_market_cap=minimo,
            search=request.args.get("search"),
            limit=int(limite) if limite is not None else config.UNIVERSE_PAGE_LIMIT_DEFAULT,
        )
    except ValueError as exc:
        return fail(str(exc))

    stato = universe.stato()
    return ok({"titoli": titoli, "totale": stato.get("titoli", 0),
               "available": stato["available"], "reason": stato.get("reason"),
               "action": stato.get("action")})


@bp.get("/stato")
def stato():
    """Quanti titoli ci sono, quanto e' vecchio l'universo, e cosa gli manca."""
    return ok(universe.stato())


@bp.post("/build")
def costruisci():
    """Avvia la costruzione e ritorna subito il run_id con cui fermarla."""
    forzato = request.args.get("force", "").strip() == "1"
    try:
        run_id = universe.build_in_background(force=forzato)
    except Exception as exc:
        # Il dettaglio resta nel log del server: all'utente arriva il motivo,
        # non l'implementazione (regola 16).
        logger.exception("[UNIVERSO] avvio della costruzione fallito")
        return fail(f"la costruzione non e' partita: {type(exc).__name__}")
    return ok({"run_id": run_id, "stop": f"/api/ops/stop/{run_id}"})
