"""
glossary.py — i 171 termini del glossario, serviti dal file curato a mano.
# feat (Blocco 5): copiato dal vecchio tradash, con l'inviluppo di qui.

Il file `data/glossary.json` e' curato a mano e non viene mai riscritto dal
programma: si corregge con un editor, come la watchlist. Per questo la cache in
memoria guarda la data di modifica e ricarica quando il file cambia — senza,
una voce aggiunta a server acceso non comparirebbe mai, ed e' l'intera classe
di "ho modificato il glossario ma non vedo niente".

Il vecchio sistema generava anche una voce per ogni metrica di `feature_engine`.
Qui succede la stessa cosa, da due sorgenti: le **voci di bilancio**
(`domain/voci.py`) e le **metriche di Defeatbeta** (`data/defeatbeta.METRICHE`).

**Generate e non scritte a mano**, perche' altrimenti sarebbero un secondo
elenco da tenere allineato: si aggiunge una metrica e ci si dimentica della sua
voce, oppure resta la voce di una metrica che non esiste piu'. Cosi' invece il
glossario segue da solo cio' che il sistema sa davvero calcolare.

**Le curate vincono sempre sull'id.** Alcune ci sono gia' scritte per esteso —
`ebit`, `free_cash_flow`, `roic`, `peg_ratio` — con formula, esempio e contesto:
una voce generata di una riga non deve sostituirle.
"""
import json
import logging
from pathlib import Path

from flask import Blueprint

from api import HTTP_NOT_FOUND, fail, ok
from core import calls
from data import defeatbeta
from domain import voci as voci_bilancio

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


# Da dove viene una voce: scritta a mano, o generata da cio' che il sistema
# calcola. Si dichiara nella voce stessa, perche' una definizione di una riga e
# una scritta per esteso non danno lo stesso affidamento.
ORIGINE_CURATA = "curata"
ORIGINE_BILANCIO = "voce di bilancio"
ORIGINE_METRICA = "metrica calcolata"


def _una_voce_di_bilancio(nome: str, etichetta: str, spiegazione: str) -> dict:
    """Una voce di glossario per una riga dei prospetti.

    Le voci su cui si sbaglia davvero — ricavi, margine lordo, reddito
    operativo, EBIT, EBITDA, utile, cassa libera, patrimonio, debito,
    circolante — hanno una spiegazione estesa, la loro formula e, dove c'e', la
    trappola. Le altre tengono la riga sola: centottanta paragrafi generici non
    sarebbero informazione, sarebbero testo.
    """
    dettaglio = voci_bilancio.dettaglio(nome) or {}
    contesto = f"Compare nei Fondamentali col nome originale «{nome.replace('_', ' ')}»."
    if dettaglio.get("attenzione"):
        contesto += f" Attenzione: {dettaglio['attenzione']}"

    return {
        "id": nome, "label": etichetta, "short": spiegazione,
        "full": dettaglio.get("esteso") or spiegazione,
        "formula": dettaglio.get("formula"), "example": None,
        "context": contesto,
        "source_label": "Defeatbeta", "source_url": None,
        "related": [], "origine": ORIGINE_BILANCIO, "nome_originale": nome,
        "approfondita": bool(dettaglio),
    }


def _da_voci_di_bilancio() -> list[dict]:
    """Una voce di glossario per ogni riga dei prospetti che sappiamo tradurre."""
    return [_una_voce_di_bilancio(nome, etichetta, spiegazione)
            for nome, (etichetta, spiegazione) in voci_bilancio.VOCI.items()]


def _da_metriche() -> list[dict]:
    """Una voce per ogni metrica che la libreria sa calcolare."""
    return [{
        "id": nome, "label": nome.replace("_", " "), "short": descrizione.capitalize() + ".",
        "full": descrizione.capitalize() + ".",
        "formula": None, "example": None,
        "context": ("Si chiede dalla sezione Metriche della scheda titolo, una alla volta."
                    + (" E' fra le lente: puo' prendere decine di secondi."
                       if nome in defeatbeta.METRICHE_LENTE else "")),
        "source_label": "Defeatbeta", "source_url": None,
        "related": [], "origine": ORIGINE_METRICA, "nome_originale": nome,
    } for nome, descrizione in defeatbeta.METRICHE.items()]


def tutte() -> tuple[list[dict], str | None]:
    """Le voci curate piu' quelle generate. A parita' di id, vince la curata."""
    curate, errore = termini()
    per_id = {v["id"]: {**v, "origine": ORIGINE_CURATA} for v in curate}

    for generata in _da_voci_di_bilancio() + _da_metriche():
        per_id.setdefault(generata["id"], generata)

    return sorted(per_id.values(), key=lambda v: v["label"].lower()), errore


@bp.get("")
def elenco():
    """Tutti i termini. Il frontend li chiede una volta e ci costruisce l'indice."""
    with calls.track(PROVIDER_LOCALE, ENDPOINT_ELENCO) as chiamata:
        voci, errore = tutte()
        chiamata.from_local()

    if errore:
        return fail(errore)
    return ok(voci)


@bp.get("/<termine>")
def singolo(termine: str):
    """Un termine solo, per chi arriva da un collegamento diretto."""
    voci, errore = tutte()
    if errore:
        return fail(errore)

    trovato = next((v for v in voci if v["id"] == termine), None)
    if trovato is None:
        return fail(f"il termine '{termine}' non esiste nel glossario", HTTP_NOT_FOUND)
    return ok(trovato)
