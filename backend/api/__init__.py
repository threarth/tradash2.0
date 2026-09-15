"""
Route sottili: nessuna logica di business qui dentro.
# feat (Blocco 0): inviluppo di risposta unico per tutte le API.

Ogni endpoint risponde `{"success": bool, "data": ..., "error": ...}`. Il
frontend ha un solo formato da scartare, e un errore non arriva mai come corpo
vuoto con uno status strano.
"""
import logging

from flask import jsonify

logger = logging.getLogger(__name__)

HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_SERVICE_UNAVAILABLE = 503


def ok(data):
    """Risposta riuscita."""
    return jsonify({"success": True, "data": data, "error": None})


def fail(message: str, status: int = HTTP_BAD_REQUEST):
    """Risposta fallita, con un messaggio leggibile e nessun dettaglio interno.

    Gli stack trace restano nei log del server: all'utente arriva il motivo,
    non l'implementazione.
    """
    return jsonify({"success": False, "data": None, "error": message}), status


# Cosa si dice a chi guarda quando la fonte dei dati non risponde. Il motivo e
# l'azione stanno qui e non in ventisei `try/except`: il provider cade tutto
# insieme, non una rotta alla volta.
MESSAGGIO_PROVIDER_GIU = (
    "la fonte dei dati (Defeatbeta) non risponde in questo momento. "
    "Non e' un guasto di tradash: i dati gia' scaricati continuano a funzionare "
    "— universo, watchlist e scanner leggono dal database locale — mentre la "
    "scheda di un titolo ha bisogno della rete. Riprova fra qualche minuto."
)


def installa_gestori(app) -> None:
    """Traduce il guasto del provider in una risposta leggibile, in un posto solo.

    Il difetto che chiude: `DefeatbetaUnavailable` risaliva fino a Flask, che
    rispondeva **500 con uno stack trace**. Ventiquattro rotte su ventisei di
    `api/titolo.py` non lo catturavano, quindi bastava che la fonte avesse un
    quarto d'ora di problemi perche' la scheda di un titolo mostrasse un errore
    illeggibile invece di dire cosa stava succedendo.

    Non e' un caso di scuola: e' stato trovato mentre la fonte era davvero giu'.

    Un `errorhandler` invece di un `try/except` per rotta perche' il provider
    cade **tutto insieme**: metterlo in ventisei posti significherebbe
    dimenticarlo nel ventisettesimo (regola 19).
    """
    from data.defeatbeta import DefeatbetaUnavailable  # noqa: PLC0415

    @app.errorhandler(DefeatbetaUnavailable)
    def _fonte_non_disponibile(errore):
        # Il dettaglio tecnico resta nel log del server, dove serve a capire
        # cosa e' successo; all'utente arriva il motivo (regola 16).
        logger.warning("[API] fonte non disponibile: %s", errore)
        return fail(MESSAGGIO_PROVIDER_GIU, HTTP_SERVICE_UNAVAILABLE)
