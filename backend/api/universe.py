"""
universe.py — l'universo dei titoli, visto dal frontend.
# feat (Blocco 2): route sottili, nessuna logica qui dentro.

La costruzione non parte mai da sola: si chiede, e mentre gira si vede in
`/api/ops/active` e si ferma con `/api/ops/stop/<run_id>` come qualunque altro
lavoro. E' la regola 2 messa in pratica — il costo di una pagina non dipende da
quanto resta aperta.
"""
import logging

from flask import Blueprint, request

import config
from api import fail, ok
from data import fondamentali, raffica, universe

logger = logging.getLogger(__name__)

bp = Blueprint("universe", __name__, url_prefix="/api/universe")


def _numero(nome: str, grezzo: str | None) -> tuple[float | None, str | None]:
    """Converte un parametro numerico, dicendo quale non andava bene."""
    if grezzo is None:
        return None, None
    try:
        return float(grezzo), None
    except (TypeError, ValueError):
        return None, f"{nome} non e' un numero: {grezzo!r}"


@bp.get("")
def elenco():
    """I titoli dell'universo. Filtri: `sector`, `industry`, `min_market_cap`, `search`."""
    limite, errore = _numero("limit", request.args.get("limit"))
    if errore:
        return fail(errore)
    minimo, errore = _numero("min_market_cap", request.args.get("min_market_cap"))
    if errore:
        return fail(errore)

    try:
        titoli = universe.rows(
            sector=request.args.get("sector"),
            industry=request.args.get("industry"),
            min_market_cap=minimo,
            search=request.args.get("search"),
            limit=int(limite) if limite is not None else config.UNIVERSE_PAGE_LIMIT_DEFAULT,
        )
    except ValueError as exc:
        return fail(str(exc))

    stato = universe.stato()
    return ok({"titoli": titoli, "totale": stato.get("titoli", 0),
               "available": stato["available"], "reason": stato.get("reason"),
               "action": stato.get("action")})


@bp.get("/titolo/<simbolo>")
def titolo(simbolo: str):
    """Cosa sa l'universo di un titolo: nome, settore, industria, dimensione.

    E' l'anteprima che compare passando il mouse su un simbolo. Un titolo che
    l'universo non conosce non e' un errore del server: e' un'assenza, e si
    dichiara col motivo — capita ai simboli nuovi finche' l'universo non viene
    ricostruito, e a quelli che non stanno nel dataset.
    """
    trovata = universe.riga(simbolo)
    if trovata is None:
        return ok({"disponibile": False, "symbol": simbolo.strip().upper(),
                   "motivo": "non e' nell'universo: o e' troppo nuovo, o "
                             "l'universo non e' stato ancora ricostruito"})
    return ok({"disponibile": True, **trovata})


@bp.get("/fondamentali")
def fondamentali_stato():
    """Quanto copre la tabella dei fondamentali, e da quando."""
    return ok(fondamentali.stato())


@bp.post("/fondamentali")
def fondamentali_deriva():
    """Deriva i fondamentali di tutto l'universo. Parte solo da qui.

    Una lettura sola sul parquet dei bilanci — misurata in 56 secondi a freddo —
    e per questo torna subito il `run_id`: una richiesta HTTP appesa un minuto
    sarebbe un lavoro che non si puo' fermare.
    """
    run_id = fondamentali.costruisci_in_background()
    return ok({"run_id": run_id, "stop": f"/api/ops/stop/{run_id}"})


@bp.get("/storico")
def storico_stato():
    """Quanto copre lo storico mensile, e da quando."""
    return ok(fondamentali.stato_prezzi())


@bp.post("/storico")
def storico_deriva():
    """Deriva la chiusura di fine mese di tutti i titoli. Parte solo da qui.

    E' la tabella su cui poggia il rigioco: senza, un criterio non si puo'
    provare all'indietro. Una lettura sola — misurata in 68 secondi — e per
    questo torna subito il `run_id`.
    """
    run_id = fondamentali.costruisci_prezzi_in_background()
    return ok({"run_id": run_id, "stop": f"/api/ops/stop/{run_id}"})


@bp.get("/depositi")
def depositi_stato():
    """Quanti 8-K per mese conosciamo, e fino a quando."""
    return ok(raffica.stato())


@bp.post("/depositi")
def depositi_deriva():
    """Conta gli 8-K di tutto l'universo, mese per mese. Parte solo da qui.

    E' la tabella su cui poggia il criterio della raffica. Una lettura sola —
    misurata in 6,4 secondi, 447.956 righe — ma torna comunque subito il
    `run_id`, perche' anche un lavoro corto dev'essere visibile e fermabile
    (regola 1).
    """
    run_id = raffica.costruisci_in_background()
    return ok({"run_id": run_id, "stop": f"/api/ops/stop/{run_id}"})


@bp.get("/stato")
def stato():
    """Quanti titoli ci sono, quanto e' vecchio l'universo, e cosa gli manca."""
    return ok(universe.stato())


def _avvia(quale: str):
    """Fa partire una delle due meta' e torna subito il run_id per fermarla.

    Le due rotte sono identiche tranne per il nome della meta': la differenza
    sta tutta in `data/universe.py`, e qui resta una riga (regola 19).
    """
    forzato = request.args.get("force", "").strip() == "1"
    try:
        run_id = universe.build_in_background(quale, force=forzato)
    except Exception as exc:
        # Il dettaglio resta nel log del server: all'utente arriva il motivo,
        # non l'implementazione (regola 16).
        logger.exception("[UNIVERSO] avvio della costruzione di %s fallito", quale)
        return fail(f"la costruzione non e' partita: {type(exc).__name__}")
    return ok({"run_id": run_id, "meta": quale, "stop": f"/api/ops/stop/{run_id}"})


@bp.post("/anagrafica")
def costruisci_anagrafica():
    """Nome, settore, industria, paese, dipendenti, azioni. Ogni due settimane.

    Non legge il parquet dei prezzi: misurata in 2,7 secondi e 238 MB di picco.
    E' la meta' che si puo' rifare senza pensarci.
    """
    return _avvia("anagrafica")


@bp.post("/mercato")
def costruisci_mercato():
    """Ultima chiusura, sua data e volume medio. Ogni giorno.

    E' la meta' cara: 445 MB da scaricare la prima volta e oltre 3 GB di picco
    di memoria anche a cache calda. Ha bisogno che l'anagrafica esista, e se
    non c'e' il lavoro lo dice invece di scrivere zero righe in silenzio.
    """
    return _avvia("mercato")
