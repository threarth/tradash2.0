"""
impostazioni.py — le scelte che fai tu, viste dal frontend.
# feat: il selettore del modello, globale.

Route sottili: la validazione sta nel modulo, qui c'e' solo il giro HTTP. Un
nome di modello che nessun fornitore riconosce e' un errore d'uso — 400 con
scritto cosa non andava — non un guasto del server.
"""
import logging

from flask import Blueprint, request

import config
from api import fail, ok
from core import impostazioni, llm
from core.impostazioni import ImpostazioniError

logger = logging.getLogger(__name__)

bp = Blueprint("impostazioni", __name__, url_prefix="/api/impostazioni")


def _catalogo() -> list[dict]:
    """I modelli che si possono scegliere, col fornitore e il loro listino.

    Vengono dal listino perche' e' l'unico elenco che il sistema possiede
    davvero: sono quelli di cui sa dire quanto costano. Non e' una gabbia — il
    file accetta anche un nome fuori elenco, purche' un fornitore lo riconosca —
    ma e' cio' che la tendina propone, e ogni riga porta il proprio prezzo,
    perche' scegliere un modello e' scegliere quanto si paga.
    """
    modelli = []
    for nome, prezzi in sorted(config.LLM_PREZZI.items()):
        try:
            fornitore = llm.provider_di(nome)
        except llm.LlmNonDisponibile:
            # Un prezzo per un modello di cui non si sa il fornitore non e'
            # scegliibile: si salta invece di proporlo e fallire al primo uso.
            logger.warning("[IMPOSTAZIONI] %s ha un listino ma nessun fornitore", nome)
            continue
        modelli.append({"nome": nome, "fornitore": fornitore,
                        "ingresso": prezzi["ingresso"], "uscita": prezzi["uscita"]})
    return modelli


@bp.get("/llm")
def llm_leggi():
    """Quale modello risponde alle analisi, e fra quali si puo' scegliere."""
    attuale = impostazioni.modello()
    return ok({
        "modello": attuale,
        "predefinito": config.LLM_MODELLO,
        "scelto_da_te": impostazioni.scelto_da_te(),
        "modelli": _catalogo(),
        # Un modello senza listino non prende un costo inventato: prende zero, e
        # il totale speso lo dichiara. Va detto QUI, prima di sceglierlo.
        "senza_listino": attuale not in config.LLM_PREZZI,
        "dove": str(config.IMPOSTAZIONI_PATH),
    })


@bp.put("/llm")
def llm_scegli():
    """Cambia il modello per tutte le analisi. Vale dalla prossima chiamata."""
    corpo = request.get_json(silent=True) or {}
    try:
        return ok(impostazioni.imposta_modello(corpo.get("modello"), llm.provider_di))
    except ImpostazioniError as exc:
        return fail(str(exc))
