"""
glossary.py — i 171 termini del glossario, serviti dal file curato a mano.
# feat (Blocco 5): copiato dal vecchio tradash, con l'inviluppo di qui.

Il file `data/glossary.json` e' curato a mano e non viene mai riscritto dal
programma: si corregge con un editor, come la watchlist. Per questo la cache in
memoria guarda la data di modifica e ricarica quando il file cambia — senza,
una voce aggiunta a server acceso non comparirebbe mai, ed e' l'intera classe
di "ho modificato il glossario ma non vedo niente".

Il vecchio sistema generava anche una voce per ogni metrica di `feature_engine`.
Quel modulo qui non esiste ancora (arriva col Blocco 7): quando ci sara', le
voci generate si uniscono a queste, e le curate vincono sempre sull'id.
"""
import json
import logging
from pathlib import Path

from flask import Blueprint

from api import HTTP_NOT_FOUND, fail, ok
from core import calls

logger = logging.getLogger(__name__)

bp = Blueprint("glossary", __name__, url_prefix="/api/glossario")

PERCORSO = Path(__file__).resolve().parent.parent / "data" / "glossary.json"

PROVIDER_LOCALE = "glossario"
ENDPOINT_ELENCO = "termini"

# Cosa e' stato letto, e da quale versione del file. Nessuna delle due da sola
# basta: la cache serve a non rileggere, la data a sapere quando invece si deve.
_cache: dict = {"voci": None, "mtime": None}


def _mtime() -> float | None:
    """Quando e' stato modificato il file. `None` se non c'e' o non si legge."""
    try:
        return PERCORSO.stat().st_mtime
    except OSError:
        return None


def termini() -> tuple[list[dict], str | None]:
    """I termini del glossario. Ritorna `(voci, errore)`, mai un `None` muto."""
    attuale = _mtime()
    if attuale is None:
        return _cache["voci"] or [], f"{PERCORSO.name} non e' accessibile"

    if _cache["voci"] is None or _cache["mtime"] != attuale:
        try:
            _cache["voci"] = json.loads(PERCORSO.read_text(encoding="utf-8"))
            _cache["mtime"] = attuale
            logger.info("[GLOSSARIO] caricati %d termini", len(_cache["voci"]))
        except (OSError, json.JSONDecodeError) as exc:
            logger.exception("[GLOSSARIO] file illeggibile")
            return _cache["voci"] or [], f"{PERCORSO.name} non e' leggibile: {exc}"

    return _cache["voci"], None


@bp.get("")
def elenco():
    """Tutti i termini. Il frontend li chiede una volta e ci costruisce l'indice."""
    with calls.track(PROVIDER_LOCALE, ENDPOINT_ELENCO) as chiamata:
        voci, errore = termini()
        chiamata.from_local()

    if errore:
        return fail(errore)
    return ok(voci)


@bp.get("/<termine>")
def singolo(termine: str):
    """Un termine solo, per chi arriva da un collegamento diretto."""
    voci, errore = termini()
    if errore:
        return fail(errore)

    trovato = next((v for v in voci if v["id"] == termine), None)
    if trovato is None:
        return fail(f"il termine '{termine}' non esiste nel glossario", HTTP_NOT_FOUND)
    return ok(trovato)
