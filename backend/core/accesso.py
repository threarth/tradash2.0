"""
accesso.py — la porta: chi entra, chi resta fuori, e con quali intestazioni.
# feat (Blocco 10): tutto chiuso per default, non tutto aperto con qualche toppa.

## La scelta che conta: si chiude per PERCORSO, non per elenco

La guardia non tiene una lista di rotte da proteggere: **rifiuta tutto cio' che
comincia per `/api/`** tranne un elenco corto e dichiarato di eccezioni. La
differenza si vede il giorno in cui qualcuno aggiunge un endpoint nuovo: con
l'elenco delle protette, quello nasce aperto e nessuno se ne accorge; cosi'
nasce chiuso, e se dev'essere pubblico bisogna scriverlo — con il suo motivo.

E' la stessa forma del controllo sul glossario del Blocco 5: o passi dalla via
normale, o compari nell'elenco delle eccezioni con la ragione accanto.

## Il cookie

Di sola sessione — nessuna scadenza, muore col browser — `HttpOnly` (nessun
JavaScript lo legge, quindi un XSS non se lo porta via), `Secure`, e
**`SameSite=Lax`**, che e' la difesa CSRF: con Lax il cookie non viaggia su una
POST partita da un altro sito, e le POST qui sono tutto cio' che spende soldi o
cancella dati.

Dentro ci sono due cose sole: il nome e la generazione. Nessun dato, nessun
segreto, niente che valga la pena rubare — e firmato, quindi nemmeno modificabile.

## Il freno

Cinque tentativi, poi si aspetta, e l'attesa raddoppia. Non e' paranoia: una
password di sei caratteri regge finche' provarle tutte costa tempo, e questo e'
il pezzo che glielo fa costare.
"""
import logging
import secrets
import threading
import time

from flask import jsonify, request, session

import config
from core import utente

logger = logging.getLogger(__name__)

# Cosa si porta dietro il cookie. Due chiavi, nessun dato.
CHIAVE_NOME = "nome"
CHIAVE_GENERAZIONE = "generazione"

HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429

PREFISSO_API = "/api/"

# Le UNICHE rotte di `/api/` raggiungibili senza aver fatto l'accesso, ognuna
# col motivo per cui deve esserlo. Chi ne aggiunge una qui sta aprendo una porta
# sull'internet pubblico, e deve poterlo giustificare in una riga.
API_PUBBLICHE = {
    "/api/auth/stato": "dice se sei dentro o fuori: e' la domanda che si fa PRIMA di entrare",
    "/api/auth/login": "e' la porta stessa: chiuderla vorrebbe dire non poter entrare",
    "/api/auth/logout": "uscire non richiede di essere entrati, e non puo' fare danni",
}

# Le intestazioni di sicurezza, tutte con il loro perche'.
#
# La CSP e' volutamente stretta e senza `unsafe-eval`: il build di Vite non ne ha
# bisogno. `style-src` accetta `unsafe-inline` perche' Svelte scrive stili in
# linea, e toglierlo vorrebbe dire una nonce su ogni componente.
INTESTAZIONI_SICUREZZA = {
    # Niente sniffing del tipo: un file di testo non deve poter diventare script.
    "X-Content-Type-Options": "nosniff",
    # Niente incorniciamento: nessuno mette questa pagina dentro la sua.
    "X-Frame-Options": "DENY",
    # L'indirizzo di questa pagina non esce verso altri siti.
    "Referrer-Policy": "no-referrer",
    # Nessuna di queste serve, e cio' che non serve si spegne.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}

# Quanto dura l'HSTS annunciato: sei mesi. Si manda solo sulle richieste che
# sono davvero arrivate in HTTPS — annunciarlo in chiaro non ha senso e su
# localhost bloccherebbe lo sviluppo.
HSTS = "max-age=15552000; includeSubDomains"

# I tentativi falliti, per indirizzo. In memoria: si azzerano al riavvio, ed e'
# accettabile — riavviare il servizio e' gia' un privilegio di chi amministra.
_tentativi: dict[str, dict] = {}
_lucchetto = threading.Lock()


def chiave_sessione() -> bytes:
    """La chiave con cui si firma il cookie. Si crea al primo avvio e resta.

    Rigenerarla a ogni avvio significherebbe rifare l'accesso a ogni riavvio del
    servizio, cioe' a ogni aggiornamento del codice.
    """
    percorso = config.CHIAVE_SESSIONE_PATH
    if percorso.exists():
        return percorso.read_bytes()

    percorso.parent.mkdir(parents=True, exist_ok=True)
    chiave = secrets.token_bytes(config.CHIAVE_SESSIONE_BYTE)
    percorso.write_bytes(chiave)
    percorso.chmod(config.CHIAVE_SESSIONE_PERMESSI)
    logger.warning("[ACCESSO] chiave di sessione creata in %s", percorso)
    return chiave


def configura(app) -> None:
    """Mette la porta all'applicazione: chiave, cookie, guardia, intestazioni."""
    app.secret_key = chiave_sessione()
    app.config.update(
        SESSION_COOKIE_NAME=config.COOKIE_SESSIONE,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=config.COOKIE_SICURO,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    # Il cookie e' di sola sessione perche' `session.permanent` resta falso — si
    # veda `accedi()`. Non si tocca `PERMANENT_SESSION_LIFETIME`: quello governa
    # le sessioni permanenti, che qui non esistono, e metterlo a None rompe
    # Flask alla prima risposta.
    app.before_request(guardia)
    app.after_request(intestazioni)


def connesso() -> bool:
    """C'e' una sessione valida?

    Valida significa due cose: il nome e' quello dell'utente configurato, **e**
    la generazione e' quella corrente. Un cookie sopravvissuto a un cambio di
    password non passa di qui.
    """
    dati = utente.leggi()
    if dati is None:
        return False
    return (session.get(CHIAVE_NOME) == dati["nome"]
            and session.get(CHIAVE_GENERAZIONE) == int(dati.get("generazione", 1)))


def guardia():
    """Chiude tutto cio' che sta sotto `/api/`, tranne le eccezioni dichiarate.

    Ritorna `None` per lasciar passare, com'e' il contratto di `before_request`.
    Quello che NON sta sotto `/api/` — la pagina, il JavaScript, i fogli di
    stile — resta pubblico: e' il guscio dentro cui vive la schermata di
    accesso, e non contiene niente che non sia gia' nel repo.
    """
    percorso = request.path
    if not percorso.startswith(PREFISSO_API):
        return None
    if percorso in API_PUBBLICHE:
        return None
    if connesso():
        return None

    return jsonify({
        "success": False, "data": None,
        "error": "devi accedere per usare tradash2.0",
    }), HTTP_UNAUTHORIZED


def intestazioni(risposta):
    """Aggiunge le intestazioni di sicurezza a ogni risposta."""
    for nome, valore in INTESTAZIONI_SICUREZZA.items():
        risposta.headers.setdefault(nome, valore)
    if request.is_secure:
        risposta.headers.setdefault("Strict-Transport-Security", HSTS)
    return risposta


def _chi_chiama() -> str:
    """L'indirizzo da cui arriva la richiesta, per contare i tentativi.

    Dietro nginx l'indirizzo vero sta in `X-Forwarded-For`, che pero' **e'
    scrivibile da chiunque** se nessuno lo ripulisce: e' il proxy a doverlo
    impostare. Si usa l'ultimo salto, che e' quello che il nostro proxy ha
    aggiunto, e si ripiega su `remote_addr` quando non c'e'.
    """
    inoltrato = request.headers.get("X-Forwarded-For", "")
    if inoltrato:
        return inoltrato.split(",")[-1].strip()
    return request.remote_addr or "sconosciuto"


def attesa_residua(indirizzo: str) -> int:
    """Quanti secondi mancano prima che questo indirizzo possa riprovare."""
    with _lucchetto:
        stato = _tentativi.get(indirizzo)
        if not stato:
            return 0
        return max(0, int(stato["libero_da"] - time.monotonic()))


def _registra_fallimento(indirizzo: str) -> int:
    """Conta un tentativo sbagliato e ritorna quanto dovra' aspettare."""
    adesso = time.monotonic()
    with _lucchetto:
        stato = _tentativi.get(indirizzo)
        if stato is None or adesso - stato["ultimo"] > config.ACCESSO_MEMORIA_S:
            stato = {"falliti": 0, "libero_da": adesso, "ultimo": adesso}

        stato["falliti"] += 1
        stato["ultimo"] = adesso

        oltre = stato["falliti"] - config.ACCESSO_TENTATIVI_PRIMA_DEL_FRENO
        attesa = 0
        if oltre > 0:
            attesa = min(config.ACCESSO_ATTESA_INIZIALE_S * (2 ** (oltre - 1)),
                         config.ACCESSO_ATTESA_MASSIMA_S)
            stato["libero_da"] = adesso + attesa

        _tentativi[indirizzo] = stato

    return attesa


def _dimentica(indirizzo: str) -> None:
    """Un accesso riuscito azzera il conto: il freno punisce chi indovina, non te."""
    with _lucchetto:
        _tentativi.pop(indirizzo, None)


def accedi(nome: str, password: str) -> tuple[bool, str]:
    """Prova ad accedere. Ritorna `(riuscito, motivo)`, sempre con un motivo.

    Il motivo del fallimento e' volutamente lo stesso per nome sbagliato e
    password sbagliata: dire quale dei due non andava e' dire meta' della
    risposta a chi sta provando.
    """
    indirizzo = _chi_chiama()
    residua = attesa_residua(indirizzo)
    if residua:
        return False, f"troppi tentativi: riprova fra {residua} secondi"

    if not utente.esiste():
        return False, ("non c'e' nessun utente configurato: crealo sul server con "
                       "`python manage.py utente`")

    if not utente.verifica(nome, password):
        attesa = _registra_fallimento(indirizzo)
        logger.warning("[ACCESSO] tentativo fallito da %s%s", indirizzo,
                       f", prossimo fra {attesa}s" if attesa else "")
        return False, "nome utente o password non corretti"

    _dimentica(indirizzo)
    dati = utente.leggi()
    session.clear()
    session[CHIAVE_NOME] = dati["nome"]
    session[CHIAVE_GENERAZIONE] = int(dati.get("generazione", 1))
    # Non permanente: e' cio' che rende il cookie di sola sessione.
    session.permanent = False
    logger.info("[ACCESSO] %s e' entrato da %s", dati["nome"], indirizzo)
    return True, "accesso riuscito"


def esci() -> None:
    """Butta via la sessione. Il cookie muore con essa."""
    session.clear()
