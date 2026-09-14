"""
utente.py — chi puo' entrare, e cosa ha deciso sui cookie.
# feat (Blocco 10): un utente solo, in un file che sopravvive al rebuild.

## Perche' un file e non una tabella

Per lo stesso motivo della watchlist e delle impostazioni: `manage.py rebuild`
cancella il database, e un accesso che torna al predefinito dopo una
ricostruzione sarebbe **peggio di nessun accesso**, perche' riaprirebbe la porta
senza dirlo. Il file si legge e si corregge con un editor di testo, e non sta in
git.

## Cosa c'e' dentro, e cosa NON c'e'

C'e' il nome, l'hash della password, una generazione, e la scelta sui cookie.
**La password non c'e'**, in nessuna forma reversibile: si conserva l'hash
scrypt che `werkzeug.security` produce, quello stesso che Flask si porta gia'
dietro — nessuna dipendenza nuova per una cosa che si sbaglia facilmente
scrivendosela da soli.

## La generazione, e a cosa serve

Il cookie di sessione e' firmato ma **stateless**: dentro c'e' scritto chi sei,
e il server non tiene un elenco delle sessioni aperte. Senza altro, cambiare
password non caccerebbe fuori nessuno — chi ha gia' un cookie resta dentro per
sempre, che e' esattamente cio' che uno cambia la password per evitare.

Quindi il cookie porta anche il numero di generazione, che sale a ogni cambio di
password. Un cookie con la generazione vecchia non vale piu'. E' una riga di
codice, e trasforma «cambio la password» da gesto simbolico in gesto efficace.
"""
import json
import logging
import os
import threading
from datetime import UTC, datetime

from werkzeug.security import check_password_hash, generate_password_hash

import config

logger = logging.getLogger(__name__)

_lucchetto = threading.Lock()

# I permessi del file: dentro c'e' un hash di password, e un hash si attacca
# offline. Leggibile solo dal proprietario.
PERMESSI = 0o600


class UtenteError(ValueError):
    """Una richiesta che non si puo' accettare, col motivo scritto."""


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def esiste() -> bool:
    """C'e' un utente configurato? Se no, non si entra da nessuna parte."""
    return leggi() is not None


def leggi() -> dict | None:
    """L'utente salvato, o `None` se non e' mai stato creato.

    Un file illeggibile NON si ignora, al contrario delle impostazioni: li'
    ripiegare su un predefinito e' innocuo, qui vorrebbe dire decidere da soli
    chi puo' entrare. Si dichiara e si rifiuta l'accesso.
    """
    percorso = config.UTENTE_PATH
    if not percorso.exists():
        return None

    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("[UTENTE] %s illeggibile: nessuno potra' entrare", percorso)
        return None

    if not isinstance(dati, dict) or not dati.get("password_hash"):
        logger.error("[UTENTE] %s non contiene un utente valido", percorso)
        return None

    return dati


def _scrivi(dati: dict) -> None:
    """Salva il file in modo atomico e con i permessi stretti."""
    percorso = config.UTENTE_PATH
    percorso.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = percorso.with_suffix(percorso.suffix + ".tmp")

    temporaneo.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    os.chmod(temporaneo, PERMESSI)
    temporaneo.replace(percorso)


def crea(nome: str, password: str) -> dict:
    """Crea il primo utente. Rifiuta di sovrascriverne uno che c'e' gia'."""
    with _lucchetto:
        if leggi() is not None:
            raise UtenteError(
                f"un utente esiste gia' in {config.UTENTE_PATH}. Per cambiargli la "
                f"password usa `manage.py utente --password`, o l'applicazione."
            )
        _valida(nome, password)
        dati = {
            "versione": config.UTENTE_FILE_VERSIONE,
            "nome": nome.strip(),
            "password_hash": generate_password_hash(password),
            "generazione": 1,
            "creato_il": _adesso(),
            "password_cambiata_il": _adesso(),
            # Nessuna decisione ancora presa: il banner la chiedera'.
            "consenso": None,
        }
        _scrivi(dati)

    logger.info("[UTENTE] creato %r in %s", nome.strip(), config.UTENTE_PATH)
    return {"nome": dati["nome"], "dove": str(config.UTENTE_PATH)}


def _valida(nome: str, password: str) -> None:
    """Le due condizioni minime, con il motivo scritto per esteso."""
    if not (nome or "").strip():
        raise UtenteError("il nome utente non puo' essere vuoto")
    if len(password or "") < config.PASSWORD_LUNGHEZZA_MINIMA:
        raise UtenteError(
            f"la password deve avere almeno {config.PASSWORD_LUNGHEZZA_MINIMA} caratteri"
        )


def verifica(nome: str, password: str) -> bool:
    """La coppia nome/password e' quella giusta?

    Il confronto passa sempre da `check_password_hash`, anche quando il nome e'
    sbagliato: rispondere subito «nome inesistente» direbbe a chi prova quali
    nomi esistono, e lo direbbe anche con il tempo di risposta.
    """
    dati = leggi()
    atteso = dati["password_hash"] if dati else _hash_finto()
    giusto = check_password_hash(atteso, password or "")
    return bool(dati) and giusto and (nome or "").strip() == dati["nome"]


def _hash_finto() -> str:
    """Un hash su cui perdere lo stesso tempo, quando l'utente non esiste."""
    return generate_password_hash("una password che non e' di nessuno")


def cambia_password(vecchia: str, nuova: str) -> dict:
    """Cambia la password e invalida ogni sessione aperta altrove."""
    with _lucchetto:
        dati = leggi()
        if dati is None:
            raise UtenteError("non c'e' nessun utente a cui cambiare la password")
        if not check_password_hash(dati["password_hash"], vecchia or ""):
            raise UtenteError("la password attuale non e' giusta")
        if (nuova or "") == (vecchia or ""):
            raise UtenteError("la password nuova e' uguale a quella di adesso")
        _valida(dati["nome"], nuova)

        dati["password_hash"] = generate_password_hash(nuova)
        dati["generazione"] = int(dati.get("generazione", 1)) + 1
        dati["password_cambiata_il"] = _adesso()
        _scrivi(dati)

    logger.warning("[UTENTE] password cambiata: le sessioni aperte non valgono piu'")
    return {"generazione": dati["generazione"]}


def imposta_password(password: str) -> dict:
    """Riscrive la password senza chiedere quella vecchia. Solo da `manage.py`.

    E' la via di scampo per quando la password si dimentica: chi puo' lanciare
    `manage.py` ha gia' accesso al file, quindi chiedergli la vecchia sarebbe
    una formalita' che non protegge niente e che chiude fuori chi ha davvero
    perso la password.
    """
    with _lucchetto:
        dati = leggi()
        if dati is None:
            raise UtenteError("non c'e' nessun utente: crealo con `manage.py utente`")
        _valida(dati["nome"], password)

        dati["password_hash"] = generate_password_hash(password)
        dati["generazione"] = int(dati.get("generazione", 1)) + 1
        dati["password_cambiata_il"] = _adesso()
        _scrivi(dati)

    logger.warning("[UTENTE] password riscritta da manage.py")
    return {"nome": dati["nome"], "generazione": dati["generazione"]}


def generazione() -> int:
    """La generazione attuale. Un cookie che ne porta una piu' vecchia e' scaduto."""
    dati = leggi()
    return int(dati.get("generazione", 1)) if dati else 0


def consenso() -> dict | None:
    """Cosa ha deciso l'utente sulle preferenze salvate nel browser.

    Sta QUI e non in `localStorage` per un motivo che sembra una battuta e non lo
    e': ricordare in `localStorage` la scelta di non usare `localStorage` sarebbe
    la prima cosa che quella scelta vieta.
    """
    dati = leggi()
    return dati.get("consenso") if dati else None


def imposta_consenso(preferenze: bool) -> dict:
    """Registra la scelta sul banner. `True` consente, `False` rifiuta."""
    with _lucchetto:
        dati = leggi()
        if dati is None:
            raise UtenteError("non c'e' nessun utente a cui registrare una scelta")
        dati["consenso"] = {"preferenze": bool(preferenze), "deciso_il": _adesso()}
        _scrivi(dati)

    return dati["consenso"]
