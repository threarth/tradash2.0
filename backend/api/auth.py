"""
auth.py — entrare, uscire, cambiare password, decidere sui cookie.
# feat (Blocco 10): route sottili, la logica sta in `core/accesso.py`.

Sono le uniche rotte di `/api/` raggiungibili senza aver fatto l'accesso, e
l'elenco con i motivi sta in `core/accesso.py:API_PUBBLICHE` — non qui, perche'
chi verifica la chiusura deve trovarne uno solo.
"""
import logging

from flask import Blueprint, request

import config
from api import fail, ok
from core import accesso, utente
from core.utente import UtenteError

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

HTTP_UNAUTHORIZED = 401

# Cosa viene salvato nel browser, dichiarato dal BACKEND e non scritto nella
# pagina. Sta qui perche' l'informativa e cio' che il programma fa davvero
# devono cambiare insieme: una lista scritta a mano nel frontend invecchia da
# sola alla prima preferenza nuova.
COSA_SI_SALVA = {
    "cookie": [{
        "nome": config.COOKIE_SESSIONE,
        "tipo": "tecnico, strettamente necessario",
        "contiene": "il tuo nome utente e un numero di generazione, firmati",
        "dura": "fino alla chiusura del browser — non ha scadenza",
        "rifiutabile": False,
        "perche": "senza non si resta connessi: rifiutarlo significa non entrare",
    }],
    "preferenze": [
        {"nome": "tradash-tema", "cosa": "chiaro o scuro"},
        {"nome": "tradash-glossario", "cosa": "se le parole del glossario sono sottolineate"},
        {"nome": "tradash-pannelli", "cosa": "quali pannelli del grafico hai aperto, per titolo"},
        {"nome": "tradash-sezioni", "cosa": "quali sezioni della scheda titolo tieni aperte"},
    ],
    "terze_parti": [],
    "tracciamento": False,
}


@bp.get("/stato")
def stato():
    """Chi sei, se sei dentro, e cosa hai deciso sui cookie.

    E' la prima domanda che la pagina fa, prima ancora di sapere se mostrare la
    schermata di accesso: per questo e' pubblica.
    """
    dati = utente.leggi()
    return ok({
        "connesso": accesso.connesso(),
        "utente": dati["nome"] if dati else None,
        "configurato": dati is not None,
        "consenso": utente.consenso(),
        "cosa_si_salva": COSA_SI_SALVA,
    })


@bp.post("/login")
def login():
    """Entra. Un fallimento non dice MAI quale dei due campi era sbagliato."""
    corpo = request.get_json(silent=True) or {}
    riuscito, motivo = accesso.accedi(corpo.get("nome", ""), corpo.get("password", ""))
    if not riuscito:
        return fail(motivo, HTTP_UNAUTHORIZED)

    dati = utente.leggi()
    return ok({"connesso": True, "utente": dati["nome"], "consenso": utente.consenso()})


@bp.post("/logout")
def logout():
    """Esci. Funziona anche se non eri dentro: e' idempotente, e non fa danni."""
    accesso.esci()
    return ok({"connesso": False})


@bp.post("/password")
def cambia_password():
    """Cambia la password, e con essa scadono tutte le sessioni aperte.

    Anche la tua: chi cambia password dall'applicazione si ritrova alla
    schermata di accesso, ed e' giusto cosi' — la prova che il cambio ha
    davvero effetto e' che ti tocca rientrare.
    """
    corpo = request.get_json(silent=True) or {}
    try:
        esito = utente.cambia_password(corpo.get("vecchia", ""), corpo.get("nuova", ""))
    except UtenteError as exc:
        return fail(str(exc))

    accesso.esci()
    return ok({"cambiata": True, "generazione": esito["generazione"],
               "nota": "tutte le sessioni aperte sono scadute, compresa questa"})


@bp.put("/consenso")
def consenso():
    """Registra la scelta del banner: consenti o rifiuta le preferenze.

    Si salva sul SERVER e non nel browser. Non e' pignoleria: ricordare in
    `localStorage` che hai rifiutato `localStorage` sarebbe la prima cosa che
    quel rifiuto vieta.
    """
    corpo = request.get_json(silent=True) or {}
    preferenze = corpo.get("preferenze")
    if not isinstance(preferenze, bool):
        return fail("serve `preferenze`: true per consentire, false per rifiutare")

    try:
        return ok(utente.imposta_consenso(preferenze))
    except UtenteError as exc:
        return fail(str(exc))
