"""
llm.py — l'unico punto da cui si parla con un modello linguistico.
# feat (Blocco 8): ogni chiamata loggata, col suo costo.

La regola 1 dice "ogni chiamata API loggata", e per un modello linguistico
questo vuol dire una cosa in piu' delle altre: **quanto e' costata**. Nel
vecchio sistema una run e' rimasta "running" venti minuti senza che nessuno
potesse vedere cosa stava bruciando, e la risposta a "quanto mi e' costato
questo referto" non esisteva.

Qui ogni chiamata lascia due righe: una in `calls`, come tutte, e una in
`llm_calls` con modello, token e costo.

Il client si costruisce al PRIMO USO, non all'avvio: importare la libreria e
costruire il client non deve succedere in `create_app()` (regola 2), e chi non
usa le analisi non deve avere bisogno di una chiave.
"""
import logging
import threading
from datetime import UTC, datetime

import config
from core import calls
from core.db import db_read, db_session

logger = logging.getLogger(__name__)

PROVIDER = "anthropic"

# Cosa succede quando manca la chiave. Non e' un guasto: e' una configurazione
# assente, e va detto con il nome della variabile da riempire.
CHIAVE_MANCANTE = (
    "manca la chiave di Anthropic: esporta ANTHROPIC_API_KEY, oppure fai "
    "`ant auth login`. Senza, le analisi che usano un modello non partono."
)

_stato: dict = {"client": None}
_lucchetto = threading.Lock()


class LlmNonDisponibile(RuntimeError):
    """Non si puo' chiamare il modello: chiave assente, libreria assente, rete giu'.

    Come `DefeatbetaUnavailable`, e per lo stesso motivo: distingue "il
    fornitore non risponde" da "questo caso non ha prodotto niente".
    """


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _client():
    """Il client Anthropic, costruito al primo uso reale."""
    if _stato["client"] is not None:
        return _stato["client"]

    with _lucchetto:
        if _stato["client"] is not None:
            return _stato["client"]
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise LlmNonDisponibile(
                "la libreria `anthropic` non e' installata: pip install anthropic"
            ) from exc

        try:
            # Il costruttore senza argomenti risolve la chiave dall'ambiente o
            # da un profilo `ant auth login`: non la si passa a mano, cosi' non
            # puo' finire in un sorgente.
            _stato["client"] = anthropic.Anthropic()
        except Exception as exc:
            raise LlmNonDisponibile(f"{CHIAVE_MANCANTE} ({type(exc).__name__})") from exc

    return _stato["client"]


def costo(modello: str, token_entrata: int, token_uscita: int) -> float:
    """Quanto e' costata una chiamata, in dollari.

    Un modello senza listino torna zero e lo dice nel log: un costo inventato
    su prezzi che non abbiamo e' peggio di nessun costo, perche' sembra un dato.
    """
    prezzi = config.LLM_PREZZI.get(modello)
    if prezzi is None:
        logger.warning("[LLM] nessun listino per %s: il costo risultera' zero", modello)
        return 0.0

    return round(
        (token_entrata * prezzi["ingresso"] + token_uscita * prezzi["uscita"])
        / config.TOKEN_PER_MILIONE, 6,
    )


def _registra(dove: dict, uso, esito: dict) -> float:
    """Scrive la riga di dettaglio. Ritorna il costo, che serve a chi chiama.

    `dove` dice modello, fase, ambito e lavoro; `esito` dice com'e' andata. Due
    dizionari invece di otto parametri: a otto, chi chiama sbaglia l'ordine.
    """
    modello, fase = dove["modello"], dove["fase"]
    entrata = getattr(uso, "input_tokens", 0) or 0
    uscita = getattr(uso, "output_tokens", 0) or 0
    speso = costo(modello, entrata, uscita)

    try:
        with db_session() as conn:
            conn.execute(
                """INSERT INTO llm_calls (modello, fase, scope, token_entrata, token_uscita,
                                          costo_usd, stop_reason, status, error_msg,
                                          run_id, called_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (modello, fase, dove.get("scope"), entrata, uscita, speso,
                 esito.get("stop_reason"), esito["stato"], esito.get("errore"),
                 dove.get("run_id"), _adesso()),
            )
    except Exception:
        logger.exception("[LLM] chiamata non registrata: %s/%s", modello, fase)

    return speso


def chiedi(fase: str, sistema: str, messaggio: str, scope: str | None = None,
           run_id: str | None = None, modello: str | None = None) -> dict:
    """Una domanda al modello. Ritorna testo, costo e come si e' fermato.

    `fase` non e' decorativa: e' il nome con cui la chiamata comparira' nel
    registro, e le quattro fasi dell'analisi qualitativa si distinguono solo da
    li'.

    Il pensiero e' in modalita' adattiva: il modello decide da solo quanto
    ragionare, invece di un tetto fisso di token che va indovinato.
    """
    scelto = modello or config.LLM_MODELLO
    dove = {"modello": scelto, "fase": fase, "scope": scope, "run_id": run_id}
    cliente = _client()

    with calls.track(PROVIDER, f"messaggio:{fase}", scope=scope, run_id=run_id) as chiamata:
        chiamata.from_network()
        try:
            risposta = cliente.messages.create(
                model=scelto,
                max_tokens=config.LLM_TOKEN_MASSIMI,
                thinking={"type": "adaptive"},
                system=sistema,
                messages=[{"role": "user", "content": messaggio}],
            )
        except Exception as exc:
            _registra(dove, None, {"stato": calls.STATUS_ERROR,
                                   "errore": f"{type(exc).__name__}: {exc}"})
            raise LlmNonDisponibile(
                f"chiamata a {scelto} fallita: {type(exc).__name__}: {exc}"
            ) from exc

    speso = _registra(dove, risposta.usage,
                      {"stato": calls.STATUS_OK, "stop_reason": risposta.stop_reason})

    # Un rifiuto non e' una risposta vuota: va distinto, perche' significa che
    # il modello ha DECISO di non rispondere, e riprovare non serve.
    testo = "".join(b.text for b in risposta.content if b.type == "text")
    return {"testo": testo, "modello": scelto, "costo_usd": speso,
            "stop_reason": risposta.stop_reason,
            "rifiutata": risposta.stop_reason == "refusal",
            "token": {"entrata": risposta.usage.input_tokens,
                      "uscita": risposta.usage.output_tokens}}


def speso_totale(run_id: str | None = None) -> dict:
    """Quanto si e' speso, in tutto o dentro un lavoro."""
    dove = "WHERE run_id = ?" if run_id else ""
    parametri = [run_id] if run_id else []

    with db_read() as conn:
        riga = conn.execute(
            f"SELECT COUNT(*) AS chiamate, "
            f"       COALESCE(SUM(costo_usd), 0) AS costo, "
            f"       COALESCE(SUM(token_entrata), 0) AS entrata, "
            f"       COALESCE(SUM(token_uscita), 0) AS uscita "
            f"FROM llm_calls {dove}", parametri,
        ).fetchone()

    return {"chiamate": riga["chiamate"], "costo_usd": round(riga["costo"], 4),
            "token_entrata": riga["entrata"], "token_uscita": riga["uscita"]}
