"""
ricostruzione.py — mette insieme cosa si sapeva a una data e cosa e' successo dopo.
# feat (Blocco 7, chiuso col Blocco 8): la pagina di confronto point-in-time.

Il calcolo puro sta in `domain/ricostruzione.py`; qui c'e' la parte che legge.

**Nessun modello.** Questa pagina non chiede niente a nessuno: mette in fila
misure deterministiche di allora e prezzi di poi. Il giudizio su come e' andata
lo fa chi guarda — che e' il motivo per cui vale la pena guardarla.

## I due tagli, che sono diversi

I **prezzi** si tagliano sulla data: le sedute fino a quel giorno compreso.
I **bilanci** si tagliano sulla data di DEPOSITO, non sulla fine del periodo —
un trimestre chiuso il 31 gennaio diventa pubblico a fine febbraio. Confonderli
e' il look-ahead classico, e produce ricostruzioni che sembrano brillanti.

E dove la data di deposito non si conosce si ricade su un ritardo stimato: la
risposta lo dichiara in `base_del_taglio`, perche' una ricostruzione fatta su
date vere e una fatta su stime non sono confrontabili.
"""
import logging

from core.tipi import python_puro
from data import defeatbeta, materiale
from domain import ricostruzione, scansione

logger = logging.getLogger(__name__)

# Sotto questa soglia le medie lunghe non esistono e la lettura tecnica di
# allora sarebbe costruita su niente. E' la stessa soglia dell'analisi tecnica.
SEDUTE_MINIME = 60


def _barre(frame) -> list[dict]:
    """I prezzi nella forma che il calcolo puro si aspetta."""
    return [{"data": str(python_puro(riga["report_date"]))[:10],
             "close": float(riga["close"]),
             "volume": float(riga["volume"] or 0)}
            for _, riga in frame.iterrows()]


def _misure_di_allora(prima: list[dict]) -> dict:
    """Cosa dicevano i prezzi a quella data. Vuoto se non erano abbastanza."""
    if len(prima) < SEDUTE_MINIME:
        return {"available": False,
                "reason": f"a quella data c'erano {len(prima)} sedute, ne servono "
                          f"almeno {SEDUTE_MINIME}: la lettura si ferma invece di "
                          f"degradare",
                "action": "scegli una data piu' recente"}

    misurato = scansione.misure([b["close"] for b in prima],
                                [b["volume"] for b in prima])
    return {"available": True, "reason": f"{len(prima)} sedute fino al "
                                         f"{prima[-1]['data']}", **misurato}


def _fondamentali_di_allora(simbolo: str, quando: str, run_id: str | None) -> dict:
    """I cinque segnali sui soli bilanci gia' depositati a quella data."""
    try:
        return {"available": True, **materiale.segnali_fondamentali(simbolo, run_id, quando)}
    except materiale.AnalisiError as exc:
        logger.info("[RICOSTRUZIONE] niente segnali per %s: %s", simbolo, exc)
        return {"available": False, "reason": str(exc),
                "action": "i segnali fondamentali richiedono i bilanci di Defeatbeta"}


def confronto(simbolo: str, quando: str, run_id: str | None = None) -> dict:
    """Cosa si poteva sapere il giorno `quando`, e cosa e' successo dopo."""
    ambito = simbolo.strip().upper()
    lettura = defeatbeta.prices(ambito, run_id=run_id)
    if not lettura.available:
        return {"symbol": ambito, "as_of": quando, "available": False,
                "reason": lettura.reason, "action": lettura.action}

    barre = _barre(lettura.frame)
    prima, dopo = ricostruzione.dividi(barre, quando)

    if not prima:
        return {"symbol": ambito, "as_of": quando, "available": False,
                "reason": f"nessuna seduta fino al {quando}: il primo prezzo che "
                          f"Defeatbeta ha per {ambito} e' del {barre[0]['data']}",
                "action": "scegli una data successiva"}

    partenza = prima[-1]
    esito = ricostruzione.cosa_e_successo(partenza["close"], dopo, quando)

    return {
        "symbol": ambito, "as_of": quando, "available": True,
        "reason": f"ricostruito su {len(prima)} sedute, con {len(dopo)} sedute dopo",
        "prezzo_alla_data": round(partenza["close"], 4),
        "ultima_seduta_utile": partenza["data"],
        "allora": {
            "tecnica": _misure_di_allora(prima),
            "fondamentale": _fondamentali_di_allora(ambito, quando, run_id),
        },
        "dopo": esito,
        "orizzonti_maturati": (
            ricostruzione.orizzonti_maturati(quando, barre[-1]["data"]) if dopo else []),
        "source": lettura.source,
    }
