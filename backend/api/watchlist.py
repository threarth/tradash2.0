"""
watchlist.py — i titoli che segui, visti dal frontend.
# feat (Blocco 3): route sottili, nessuna logica qui dentro.

Un errore d'uso — un tag che non esiste, un terzo livello, un nome gia' preso —
torna come 400 con scritto cosa non andava. Un `WatchlistError` e' un errore
dell'utente, non un guasto del server.
"""
import logging

from flask import Blueprint, request

import config
from api import fail, ok
from data import watchlist
from data.watchlist import WatchlistError

logger = logging.getLogger(__name__)

bp = Blueprint("watchlist", __name__, url_prefix="/api/watchlist")


def _simboli_richiesti(corpo: dict) -> str | list[str]:
    """I simboli mandati dal frontend, come lista o come testo incollato."""
    return corpo.get("simboli") or corpo.get("testo") or []


@bp.get("")
def elenco():
    """I titoli osservati. Filtri: `tag` (comprende i sotto-ambiti), `preferiti`."""
    return ok({
        "titoli": watchlist.elenco(
            tag=request.args.get("tag"),
            solo_preferiti=request.args.get("preferiti", "").strip() == "1",
        ),
        "tag": watchlist.tag_elenco(),
    })


@bp.post("")
def aggiungi():
    """Aggiunge titoli, dicendo di ognuno che fine ha fatto."""
    corpo = request.get_json(silent=True) or {}
    try:
        return ok(watchlist.aggiungi(_simboli_richiesti(corpo), tag=corpo.get("tag")))
    except WatchlistError as exc:
        return fail(str(exc))


@bp.delete("")
def rimuovi():
    """Toglie titoli dalla watchlist."""
    corpo = request.get_json(silent=True) or {}
    try:
        return ok(watchlist.rimuovi(list(_simboli_richiesti(corpo))))
    except WatchlistError as exc:
        return fail(str(exc))


@bp.patch("")
def modifica():
    """Cambia tag e/o preferito su piu' titoli in un colpo solo."""
    corpo = request.get_json(silent=True) or {}
    simboli = list(_simboli_richiesti(corpo))
    esito = {}
    try:
        if "tag" in corpo:
            esito["tag"] = watchlist.assegna_tag(simboli, corpo["tag"])
        if "preferito" in corpo:
            esito["preferito"] = watchlist.preferito(simboli, bool(corpo["preferito"]))
    except WatchlistError as exc:
        return fail(str(exc))

    if not esito:
        return fail("niente da cambiare: serve 'tag' oppure 'preferito'")
    return ok(esito)


@bp.get("/tag")
def tag_elenco():
    """L'albero dei tag, con i conteggi comprensivi dei sotto-ambiti."""
    return ok(watchlist.tag_elenco())


@bp.post("/tag")
def tag_crea():
    """Crea un ambito, o un sotto-ambito se arriva `padre`."""
    corpo = request.get_json(silent=True) or {}
    etichetta = (corpo.get("etichetta") or "").strip()
    if not etichetta:
        return fail("serve un'etichetta per il tag")
    try:
        return ok(watchlist.tag_crea(etichetta, padre=corpo.get("padre")))
    except WatchlistError as exc:
        return fail(str(exc))


@bp.delete("/tag/<nome>")
def tag_elimina(nome: str):
    """Elimina un tag. I titoli restano, senza tag. `?cascata=1` per i figli."""
    cascata = request.args.get("cascata", "").strip() == "1"
    try:
        return ok(watchlist.tag_elimina(nome, cascata=cascata))
    except WatchlistError as exc:
        return fail(str(exc))


@bp.get("/da-aggiornare/<categoria>")
def da_aggiornare(categoria: str):
    """Quali titoli osservati hanno quel dato ormai vecchio, e da quanto."""
    if categoria not in config.FRESHNESS_TTL_S:
        return fail(f"categoria sconosciuta: {categoria!r}")
    return ok({"categoria": categoria, "titoli": watchlist.da_aggiornare(categoria)})


@bp.get("/storico")
def storico():
    """Cosa e' successo alla watchlist, dal piu' recente."""
    grezzo = request.args.get("limit", config.WATCHLIST_EVENTS_LIMIT_DEFAULT)
    try:
        return ok(watchlist.eventi(limit=int(grezzo)))
    except (TypeError, ValueError):
        return fail(f"limit non e' un numero: {grezzo!r}")
    except WatchlistError as exc:
        return fail(str(exc))
