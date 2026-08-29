"""
Route sottili: nessuna logica di business qui dentro.
# feat (Blocco 0): inviluppo di risposta unico per tutte le API.

Ogni endpoint risponde `{"success": bool, "data": ..., "error": ...}`. Il
frontend ha un solo formato da scartare, e un errore non arriva mai come corpo
vuoto con uno status strano.
"""
from flask import jsonify

HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404


def ok(data):
    """Risposta riuscita."""
    return jsonify({"success": True, "data": data, "error": None})


def fail(message: str, status: int = HTTP_BAD_REQUEST):
    """Risposta fallita, con un messaggio leggibile e nessun dettaglio interno.

    Gli stack trace restano nei log del server: all'utente arriva il motivo,
    non l'implementazione.
    """
    return jsonify({"success": False, "data": None, "error": message}), status
