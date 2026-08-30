"""
analisi.py — le sette analisi, viste dal frontend.
# feat (Blocco 8): route sottili; il lavoro sta nel registro come tutti.

L'elenco comprende anche i metodi non ancora costruiti, con scritto cosa manca
a ciascuno: toglierli li farebbe sparire, e un'analisi che manca senza dirlo e'
indistinguibile da un'analisi che non serve.
"""
import logging

from flask import Blueprint, request

from api import HTTP_NOT_FOUND, fail, ok
from core import llm
from data import analisi
from data.analisi import AnalisiError

logger = logging.getLogger(__name__)

bp = Blueprint("analisi", __name__, url_prefix="/api/analisi")


@bp.get("")
def metodi():
    """I sette metodi, con lo stato di ciascuno e quanto si e' speso finora."""
    return ok({"metodi": analisi.elenco(), "speso": llm.speso_totale()})


@bp.post("/<metodo>/<simbolo>")
def esegui(metodo: str, simbolo: str):
    """Esegue un'analisi. Dura secondi, non minuti: si aspetta la risposta."""
    try:
        return ok(analisi.esegui(metodo, simbolo))
    except AnalisiError as exc:
        return fail(str(exc))
    except llm.LlmNonDisponibile as exc:
        # Non e' un errore dell'utente: manca una chiave, o il modello non
        # risponde. Va detto con parole sue, non come un 500 muto.
        logger.exception("[ANALISI] modello non disponibile")
        return fail(str(exc), HTTP_NOT_FOUND)


@bp.get("/referti")
def referti():
    """I referti prodotti, dal piu' recente. Filtri: `symbol`, `metodo`."""
    return ok(analisi.referti(request.args.get("symbol"),
                              request.args.get("metodo")))
