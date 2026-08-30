"""
titolo.py — la scheda di un singolo titolo.
# feat (Blocco 6): il guscio, il grafico, e le sezioni che dichiarano di essere vuote.

Il precedente da non ripetere sono le 1.342 righe di `app/ticker/[symbol]/page.tsx`
del vecchio tradash: una pagina che sapeva tutto. Qui il backend espone pezzi
separati, e la pagina li mette insieme — cosi' i blocchi 7 e 8 aggiungono le
loro sezioni senza toccare quelle che ci sono gia'.

Le sezioni non ancora costruite non spariscono: rispondono `available: false`
con dentro il blocco che le portera' (regola 5).
"""
import logging
from datetime import UTC, datetime, timedelta

from flask import Blueprint, request

import config
from api import HTTP_NOT_FOUND, fail, ok
from core.tipi import python_puro
from data import defeatbeta, grafici
from data.grafici import GraficiError
from domain import indicators

logger = logging.getLogger(__name__)

bp = Blueprint("titolo", __name__, url_prefix="/api/titolo")

# Le sezioni promesse dal PIANO e non ancora costruite. Dichiararle qui e' il
# modo di non farle sparire: la pagina le mostra vuote, col blocco che le porta.
SEZIONI_FUTURE = {
    "fondamentali": {"blocco": 7, "cosa": "bilanci, margini e crescite"},
    "filings": {"blocco": 7, "cosa": "i documenti depositati alla SEC"},
    "news": {"blocco": 7, "cosa": "le notizie sul titolo"},
    "analisi": {"blocco": 8, "cosa": "le sette analisi, ognuna nella sua sezione"},
}

ACTION_SEZIONE_FUTURA = "questa sezione arriva con il blocco {blocco} del piano"


def _profilo(simbolo: str) -> dict:
    """L'anagrafica del titolo, o il motivo per cui non c'e'."""
    lettura = defeatbeta.profile(simbolo)
    if not lettura.available:
        return {"available": False, "reason": lettura.reason, "action": lettura.action}

    riga = lettura.frame.iloc[0]
    campi = ("sector", "industry", "country", "long_business_summary",
             "full_time_employees", "web_site", "city")
    return {"available": True, "source": lettura.source,
            **{campo: python_puro(riga.get(campo)) for campo in campi}}


def _intervallo(nome: str | None) -> tuple[str | None, str | None]:
    """La data da cui partire per l'intervallo chiesto. Ritorna (data, errore)."""
    scelto = nome or config.INTERVALLO_GRAFICO_PREDEFINITO
    if scelto not in config.INTERVALLI_GRAFICO:
        return None, (f"intervallo sconosciuto: {scelto!r}. "
                      f"Ammessi: {', '.join(config.INTERVALLI_GRAFICO)}")

    giorni = config.INTERVALLI_GRAFICO[scelto]
    if giorni is None:
        return None, None
    return (datetime.now(UTC) - timedelta(days=giorni)).strftime("%Y-%m-%d"), None


@bp.get("/<simbolo>")
def scheda(simbolo: str):
    """L'intestazione della scheda: chi e' questo titolo, e cosa non c'e' ancora."""
    return ok({
        "symbol": simbolo.strip().upper(),
        "profilo": _profilo(simbolo),
        "sezioni_future": {
            nome: {"available": False,
                   "reason": f"{dati['cosa']}: non ancora costruita",
                   "action": ACTION_SEZIONE_FUTURA.format(blocco=dati["blocco"]),
                   "blocco": dati["blocco"]}
            for nome, dati in SEZIONI_FUTURE.items()
        },
    })


def _barre(frame) -> list[dict]:
    """Le barre OHLCV nella forma che il motore degli indicatori si aspetta."""
    return [
        {"timestamp": str(r["report_date"]),
         **{campo: python_puro(r[campo]) for campo in ("open", "high", "low", "close", "volume")}}
        for _, r in frame.iterrows()
    ]


def _taglia(barre: list[dict], serie: dict, da: str | None) -> tuple[list[dict], dict]:
    """Tiene solo la parte visibile, dopo che il calcolo ha visto tutto.

    Il taglio e' sulla POSIZIONE, non sulla data: barre e serie sono allineate
    per indice, e ritagliarle con due criteri diversi le sfaserebbe di un giorno
    senza che niente lo segnali.

    Assume che le barre siano in ordine di data crescente, che e' come le
    ritorna `defeatbeta.prices` (ORDER BY report_date). Su barre disordinate il
    taglio cadrebbe alla prima data buona incontrata, non all'ultima.
    """
    if da is None:
        return barre, serie

    primo = next((i for i, b in enumerate(barre) if b["timestamp"] >= da), len(barre))
    return barre[primo:], {chiave: punti[primo:] for chiave, punti in serie.items()}


@bp.get("/<simbolo>/prezzi")
def prezzi(simbolo: str):
    """Le barre OHLCV e le serie degli indicatori, gia' calcolate.

    Il taglio dell'intervallo si fa qui e non nella query: il costo e' leggere
    il parquet dei prezzi, e leggerlo una volta per tenersi tutta la storia
    rende gratis il cambio di periodo.
    """
    da, errore = _intervallo(request.args.get("intervallo"))
    if errore:
        return fail(errore)

    lettura = defeatbeta.prices(simbolo)
    if not lettura.available:
        return fail(lettura.reason, HTTP_NOT_FOUND)

    tutte = _barre(lettura.frame)
    configurazione = grafici.configurazione(simbolo)
    try:
        # Si calcola su TUTTA la storia e si taglia dopo. Calcolare sul solo
        # intervallo mostrato darebbe, a un mese di grafico, una "media a 50
        # giorni" costruita su ventidue sedute: un numero che sembra giusto e
        # non lo e'. Le medie mobili hanno bisogno del passato che non si vede.
        serie = indicators.compute(tutte, configurazione)
    except indicators.IndicatorConfigError as exc:
        logger.exception("[TITOLO] configurazione del grafico rotta per %s", simbolo)
        return fail(f"la configurazione del grafico non e' valida: {exc}")

    barre, serie = _taglia(tutte, serie, da)
    return ok({"symbol": simbolo.strip().upper(), "barre": barre, "serie": serie,
               "configurazione": configurazione, "source": lettura.source,
               "sedute_calcolate": len(tutte),
               "intervalli": list(config.INTERVALLI_GRAFICO)})


@bp.get("/<simbolo>/grafico")
def grafico(simbolo: str):
    """La configurazione in uso per questo titolo, e i tipi di indicatore possibili."""
    try:
        return ok({"configurazione": grafici.configurazione(simbolo),
                   "kind_ammessi": sorted(indicators.VALID_KINDS)})
    except GraficiError as exc:
        return fail(str(exc))


@bp.put("/<simbolo>/grafico")
def salva_grafico(simbolo: str):
    """Salva la configurazione del grafico per questo titolo."""
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict) or "nodes" not in corpo:
        return fail("serve un oggetto JSON con dentro 'nodes'")
    try:
        return ok(grafici.imposta(simbolo, corpo))
    except GraficiError as exc:
        return fail(str(exc))


@bp.delete("/<simbolo>/grafico")
def dimentica_grafico(simbolo: str):
    """Torna alla configurazione predefinita per questo titolo."""
    try:
        return ok({"dimenticata": grafici.dimentica(simbolo)})
    except GraficiError as exc:
        return fail(str(exc))
