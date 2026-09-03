"""
rischio.py — raccoglie gli ingredienti del punteggio di rischio e li mette in fila.
# feat: la parte che legge; il giudizio sta in `domain/rischio.py`.

**Nessuna chiamata a un modello.** Tutto quello che serve e' gia' calcolato
altrove: i cinque segnali dai bilanci, la discesa dai prezzi, il peso della coda
e la crescita implicita dal DCF di Defeatbeta. Questo modulo li chiede e li
passa al giudizio.

Un ingrediente che manca non ferma il punteggio: quel componente risulta «non
calcolabile», il rischio si decide sugli altri, e la **confidenza** scende. Cio'
che non si sa non deve far sembrare un titolo piu' sicuro.
"""
import logging

from data import defeatbeta, forward, materiale
from domain import drawdown, rischio

logger = logging.getLogger(__name__)


def _discesa(simbolo: str, run_id: str | None) -> dict | None:
    """Il profilo della discesa dai prezzi. `None` se non ce ne sono abbastanza."""
    lettura = defeatbeta.prices(simbolo, run_id=run_id)
    if not lettura.available:
        return None
    return drawdown.profilo(lettura.frame["close"].tolist())


def _dal_dcf(simbolo: str, run_id: str | None) -> dict:
    """Peso della coda e crescita, dal DCF. Vuoto se il DCF non si puo' fare.

    Un titolo senza bilanci sufficienti non ha un DCF, e non e' un guasto: e' un
    titolo di cui quei due componenti non si sanno.
    """
    try:
        misurato = forward.misure(simbolo, run_id)
    except (materiale.AnalisiError, defeatbeta.DefeatbetaUnavailable) as exc:
        # Il motivo si conserva e si mostra: «questo titolo non ha un DCF» e
        # «il DCF non ha risposto adesso» sono due cose diverse, e la seconda
        # cambia se si riprova. Senza, il rischio cambiava banda fra una
        # ricarica e l'altra senza dire perche'.
        logger.info("[RISCHIO] niente DCF per %s: %s", simbolo, exc)
        return {"motivo": str(exc)}

    return {
        "peso_terminale": misurato["peso_del_valore_terminale"],
        "crescita_implicita": misurato["crescita_implicita_nel_prezzo"],
        "crescita_storica": misurato["storia_della_crescita"]["ricavi_cagr_3a"],
    }


def _segnali(simbolo: str, run_id: str | None) -> dict:
    """I cinque segnali di bilancio. Vuoto se i bilanci non ci sono."""
    try:
        return materiale.segnali_fondamentali(simbolo, run_id)
    except materiale.AnalisiError as exc:
        logger.info("[RISCHIO] niente segnali per %s: %s", simbolo, exc)
        return {}


def calcola(simbolo: str, run_id: str | None = None) -> dict:
    """Il punteggio di rischio di un titolo. Deterministico: nessun modello."""
    ambito = simbolo.strip().upper()
    dal_dcf = _dal_dcf(ambito, run_id)

    componenti = [
        rischio.da_segnali(_segnali(ambito, run_id)),
        rischio.da_discesa(_discesa(ambito, run_id)),
        rischio.da_coda(dal_dcf.get("peso_terminale"), dal_dcf.get("motivo")),
        rischio.da_crescita(dal_dcf.get("crescita_implicita"),
                            dal_dcf.get("crescita_storica"), dal_dcf.get("motivo")),
    ]

    return {"symbol": ambito, **rischio.punteggio(componenti),
            "natura": "deterministico: calcolato dai dati, senza nessun modello"}
