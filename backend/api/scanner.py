"""
scanner.py — cercare titoli sul passato.
# feat (Blocco 9): route sottili; il lavoro sta nel registro, come tutti.

L'avvio ritorna subito il run_id: una scansione su trecento titoli dura minuti,
e una richiesta HTTP che resta appesa e' un'altra forma di lavoro che non si
puo' fermare.
"""
import logging

from flask import Blueprint, request

import config
from api import HTTP_NOT_FOUND, fail, ok
from data import scanner
from domain import scansione

logger = logging.getLogger(__name__)

bp = Blueprint("scanner", __name__, url_prefix="/api/scanner")


@bp.get("/criteri")
def criteri():
    """Quali criteri si possono chiedere. Il frontend ci costruisce il modulo."""
    return ok({"criteri": sorted(scansione.CRITERI), "titoli_max": config.SCANNER_TITOLI_MAX})


@bp.post("")
def avvia():
    """Avvia una scansione e ritorna il run_id con cui seguirla o fermarla."""
    corpo = request.get_json(silent=True) or {}
    richiesti = corpo.get("criteri") or {}

    sconosciuti = sorted(set(richiesti) - set(scansione.CRITERI))
    if sconosciuti:
        return fail(f"criteri sconosciuti: {', '.join(sconosciuti)}")
    if not richiesti:
        return fail("serve almeno un criterio: una scansione senza criteri "
                    "ritornerebbe l'universo intero")

    try:
        run_id = scanner.avvia(richiesti, corpo.get("filtri") or {}, corpo.get("fino_a"))
    except Exception as exc:
        logger.exception("[SCANNER] avvio fallito")
        return fail(f"la scansione non e' partita: {type(exc).__name__}")

    return ok({"run_id": run_id, "stop": f"/api/ops/stop/{run_id}",
               "esito": f"/api/scanner/{run_id}"})


@bp.get("/<run_id>")
def esito(run_id: str):
    """Il risultato di una scansione. Finche' gira, si guarda in /api/ops/active."""
    trovato = scanner.esito(run_id)
    if trovato is None:
        return fail("scansione sconosciuta, oppure ancora in corso: "
                    "guarda in /api/ops/active", HTTP_NOT_FOUND)
    return ok(trovato)
