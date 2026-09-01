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
            profilo=request.args.get("profilo"),
            maturity=request.args.get("maturity"),
        ),
        "tag": watchlist.tag_elenco(),
        "profili": config.PROFILI,
        "maturity": config.MATURITY,
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
    """Azioni in blocco: aggiunge o toglie un tema, accende o spegne il preferito."""
    corpo = request.get_json(silent=True) or {}
    simboli = list(_simboli_richiesti(corpo))
    esito = {}
    try:
        if corpo.get("aggiungi_tag"):
            esito["aggiunto"] = watchlist.aggiungi_tag(simboli, corpo["aggiungi_tag"])
        if corpo.get("togli_tag"):
            esito["tolto"] = watchlist.togli_tag(simboli, corpo["togli_tag"])
        if "preferito" in corpo:
            esito["preferito"] = watchlist.preferito(simboli, bool(corpo["preferito"]))
    except WatchlistError as exc:
        return fail(str(exc))

    if not esito:
        return fail("niente da cambiare: serve 'aggiungi_tag', 'togli_tag' o 'preferito'")
    return ok(esito)


@bp.patch("/<simbolo>")
def attributi(simbolo: str):
    """L'editor della scheda: temi, profilo e maturity di UN titolo.

    Cio' che non arriva nel corpo non viene toccato: mandare `null` significa
    svuotare, non mandare il campo significa lasciarlo com'e'.
    """
    corpo = request.get_json(silent=True) or {}
    non_toccare = ...
    try:
        return ok(watchlist.imposta_attributi(
            simbolo,
            tag=corpo.get("tag", non_toccare),
            profilo=corpo.get("profilo", non_toccare),
            maturity=corpo.get("maturity", non_toccare),
        ))
    except WatchlistError as exc:
        return fail(str(exc))


@bp.get("/esporta")
def esporta():
    """La watchlist in forma portabile, da incollare in un LLM o da tenere da parte."""
    return ok(watchlist.esporta())


@bp.get("/prompt")
def prompt():
    """Il testo gia' pronto da dare a un LLM perche' classifichi i titoli."""
    grezzo = request.args.get("simboli", "").strip()
    richiesti = [s for s in grezzo.replace(",", " ").split()] if grezzo else None
    try:
        return ok({"prompt": watchlist.prompt_classificazione(richiesti),
                   "profili": config.PROFILI, "maturity": config.MATURITY})
    except WatchlistError as exc:
        return fail(str(exc))


@bp.post("/importa")
def importa():
    """Carica una classificazione prodotta altrove, dicendo di ognuno che fine ha fatto."""
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return fail("serve un oggetto JSON con dentro 'titoli'")
    try:
        return ok(watchlist.importa(corpo))
    except WatchlistError as exc:
        return fail(str(exc))


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
    if categoria not in config.FRESHNESS_CATEGORIE_PER_TITOLO:
        globale = categoria in config.FRESHNESS_TTL_S
        return fail(
            f"«{categoria}» e' un dato globale, non di un titolo: chiederne la "
            f"freschezza per simbolo non ha senso" if globale
            else f"categoria sconosciuta: {categoria!r}. Ci sono: "
                 f"{', '.join(config.FRESHNESS_CATEGORIE_PER_TITOLO)}"
        )
    return ok({"categoria": categoria,
               "ttl_s": config.FRESHNESS_TTL_S[categoria],
               "osservati": len(watchlist.simboli()),
               "titoli": watchlist.da_aggiornare(categoria)})


@bp.get("/da-aggiornare")
def categorie_da_aggiornare():
    """Di quali dati si puo' chiedere la freschezza, e ogni quanto scadono.

    L'elenco lo decide il backend e non lo indovina l'interfaccia: quali
    categorie riguardino un titolo e quali siano globali e' una proprieta' dei
    dati, non una scelta di chi disegna.
    """
    return ok({"categorie": [
        {"nome": nome, "ttl_s": config.FRESHNESS_TTL_S[nome]}
        for nome in config.FRESHNESS_CATEGORIE_PER_TITOLO
    ]})


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
