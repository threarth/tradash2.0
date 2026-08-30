"""
web.py — Flask serve anche la SPA, cosi' i processi restano uno.
# feat (Blocco 4): niente SvelteKit, niente secondo servizio che gira da solo.

In sviluppo girano due processi (Vite e Flask) perche' Vite ricarica a caldo;
in uso reale c'e' solo Flask, che serve il build di Vite dalla cartella `dist`.

Se il build non c'e', la risposta lo DICE con il comando da lanciare: un 404
muto su `/` manderebbe a cercare un errore di rotte che non esiste.
"""
import logging

from flask import Blueprint, send_from_directory

import config
from api import fail

logger = logging.getLogger(__name__)

bp = Blueprint("web", __name__)

HTTP_NOT_FOUND = 404
HTTP_SERVICE_UNAVAILABLE = 503

PAGINA_INIZIALE = "index.html"

MESSAGGIO_BUILD_MANCANTE = (
    "il frontend non e' stato ancora costruito. Da `frontend/`: `pnpm install` "
    "e `pnpm build`. Per lo sviluppo con ricarica a caldo: `pnpm dev` e apri "
    "la porta di Vite, che gira le chiamate /api qui."
)


@bp.get("/")
@bp.get("/<path:richiesto>")
def spa(richiesto: str = ""):
    """Serve un file del build, oppure la pagina iniziale per le rotte della SPA.

    Le rotte del frontend (`/watchlist`, `/operazioni`) non sono file: chi le
    apre direttamente, o le ricarica, deve ricevere `index.html` e lasciare che
    sia il router a decidere. Un percorso `/api` che arriva fin qui e' invece un
    endpoint che non esiste, e va detto in quel modo.
    """
    if richiesto.startswith("api/"):
        return fail(f"endpoint inesistente: /{richiesto}", HTTP_NOT_FOUND)

    cartella = config.FRONTEND_DIST
    if richiesto and (cartella / richiesto).is_file():
        return send_from_directory(cartella, richiesto)

    if not (cartella / PAGINA_INIZIALE).is_file():
        logger.warning("[WEB] build del frontend assente in %s", cartella)
        return fail(MESSAGGIO_BUILD_MANCANTE, HTTP_SERVICE_UNAVAILABLE)

    return send_from_directory(cartella, PAGINA_INIZIALE)
