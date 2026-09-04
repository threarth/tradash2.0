"""
spinoff.py — l'elenco degli spin-off recenti, e il pulsante per riprenderlo.
# feat: l'unico dato che non viene da Defeatbeta.

Due route e nessuna scorciatoia: si legge cio' che e' salvato, e si riscarica
**solo** con una POST, cioe' solo quando qualcuno preme. Nessun aggiornamento
all'avvio, a scadenza o «se il file e' vecchio»: un fetch che parte da solo e'
esattamente cio' che qui non si fa.
"""
import logging

from flask import Blueprint

from api import fail, ok
from data import spinoff_elenco
from data.spinoff_elenco import SpinoffError

logger = logging.getLogger(__name__)

bp = Blueprint("spinoff", __name__, url_prefix="/api/spinoff")


@bp.get("")
def elenco():
    """Chi si e' separato da chi, secondo l'elenco salvato, e quando l'abbiamo preso."""
    return ok(spinoff_elenco.elenco())


@bp.post("/calcola")
def calcola():
    """Misura i sei segnali su tutti i candidati salvati. Parte solo da qui.

    Ritorna subito il `run_id`: sono decine di letture da Defeatbeta, ognuna
    lenta la prima volta, e una richiesta HTTP appesa per minuti sarebbe
    un'altra forma di lavoro che non si puo' fermare. Il pannello in alto lo
    mostra mentre avanza, con dentro il titolo che sta guardando.
    """
    try:
        run_id = spinoff_elenco.calcola_in_background()
    except SpinoffError as exc:
        return fail(str(exc))
    return ok({"run_id": run_id, "stop": f"/api/ops/stop/{run_id}"})


@bp.post("/aggiorna")
def aggiorna():
    """Riscarica la pagina e salva l'elenco. Parte solo da qui."""
    try:
        return ok(spinoff_elenco.aggiorna())
    except SpinoffError as exc:
        # Non e' un guasto del server: e' una pagina che non ha risposto o che
        # ha cambiato forma. L'elenco di prima e' ancora al suo posto.
        logger.warning("[SPINOFF] aggiornamento non riuscito: %s", exc)
        return fail(str(exc))
