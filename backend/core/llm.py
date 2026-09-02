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

## Due fornitori, un punto solo

Si parla con OpenAI **e** con Anthropic, e il fornitore si sceglie dal nome del
modello: `gpt-*` va da OpenAI, `claude-*` da Anthropic. Non c'e' un interruttore
da ricordarsi di girare — chiedere `gpt-5.5` e ottenere una risposta di Claude
perche' un valore di configurazione era rimasto indietro sarebbe un difetto
invisibile nei referti.

Le due API non si somigliano — una vuole `system` e `messages`, l'altra
`instructions` e `input`; una decide da sola quanto ragionare, l'altra vuole un
livello — e ogni adattatore restituisce la stessa forma: testo, come si e'
fermato, se ha rifiutato, e i token. Tutto il resto del modulo non sa quale dei
due ha risposto.
"""
import logging
import threading
from datetime import UTC, datetime

import config
from core import calls
from core.db import db_read, db_session

logger = logging.getLogger(__name__)

# Come i due fornitori dicono "ho smesso perche' avevo finito lo spazio". E'
# l'informazione che distingue una risposta sbagliata da una risposta TAGLIATA,
# e senza si da' la colpa al JSON illeggibile invece che al tetto.
MOTIVO_TAGLIO_OPENAI = "max_output_tokens"
MOTIVO_TAGLIO_ANTHROPIC = "max_tokens"

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"

# Da che nome si riconosce il fornitore. E' un prefisso e non un elenco chiuso
# di modelli: i nomi nuovi escono di continuo, e un elenco chiuso vorrebbe dire
# aggiornare il codice per provare `gpt-5.6`.
PREFISSI = ((("gpt-", "o1", "o3", "o4"), PROVIDER_OPENAI),
            (("claude-",), PROVIDER_ANTHROPIC))

# Cosa succede quando manca la chiave. Non e' un guasto: e' una configurazione
# assente, e va detto con il nome della variabile da riempire.
CHIAVI = {PROVIDER_OPENAI: "OPENAI_API_KEY", PROVIDER_ANTHROPIC: "ANTHROPIC_API_KEY"}

_stato: dict = {"client": {}}
_lucchetto = threading.Lock()


class LlmNonDisponibile(RuntimeError):
    """Non si puo' chiamare il modello: chiave assente, libreria assente, rete giu'.

    Come `DefeatbetaUnavailable`, e per lo stesso motivo: distingue "il
    fornitore non risponde" da "questo caso non ha prodotto niente".
    """


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def provider_di(modello: str) -> str:
    """Quale fornitore risponde a questo modello. Sbagliarlo e' peggio che fermarsi."""
    nome = (modello or "").lower()
    for prefissi, fornitore in PREFISSI:
        if nome.startswith(prefissi):
            return fornitore
    raise LlmNonDisponibile(
        f"non so di chi sia il modello {modello!r}: i nomi riconosciuti "
        f"cominciano per gpt- (OpenAI) o claude- (Anthropic)"
    )


def _client(fornitore: str):
    """Il client del fornitore, costruito al primo uso reale."""
    if _stato["client"].get(fornitore) is not None:
        return _stato["client"][fornitore]

    with _lucchetto:
        if _stato["client"].get(fornitore) is not None:
            return _stato["client"][fornitore]
        _stato["client"][fornitore] = _costruisci(fornitore)

    return _stato["client"][fornitore]


def _costruisci(fornitore: str):
    """Importa la libreria giusta e costruisce il client.

    Il costruttore senza argomenti risolve la chiave dall'ambiente: non la si
    passa a mano, cosi' non puo' finire in un sorgente.
    """
    try:
        if fornitore == PROVIDER_OPENAI:
            from openai import OpenAI  # noqa: PLC0415
            costruttore = OpenAI
        else:
            from anthropic import Anthropic  # noqa: PLC0415
            costruttore = Anthropic
    except ImportError as exc:
        raise LlmNonDisponibile(
            f"la libreria di {fornitore} non e' installata. E' in "
            f"requirements.txt: `uv pip install -r requirements.txt`"
        ) from exc

    try:
        return costruttore()
    except Exception as exc:
        raise LlmNonDisponibile(
            f"manca la chiave di {fornitore}: mettila in .env come "
            f"{CHIAVI[fornitore]}. Senza, le analisi che usano un modello non "
            f"partono ({type(exc).__name__})"
        ) from exc


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


def _registra(dove: dict, risposta: dict | None, esito: dict) -> float:
    """Scrive la riga di dettaglio. Ritorna il costo, che serve a chi chiama.

    `dove` dice modello, fase, ambito e lavoro; `esito` dice com'e' andata. Due
    dizionari invece di otto parametri: a otto, chi chiama sbaglia l'ordine.

    I token arrivano gia' normalizzati dall'adattatore: qui non si sa, e non si
    deve sapere, quale libreria ha risposto.
    """
    modello, fase = dove["modello"], dove["fase"]
    entrata = (risposta or {}).get("entrata", 0) or 0
    uscita = (risposta or {}).get("uscita", 0) or 0
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


def _chiedi_a_openai(cliente, scelto: str, sistema: str, messaggio: str,
                     tetto: int) -> dict:
    """Una domanda a un modello OpenAI, attraverso l'API delle risposte.

    Lo sforzo di ragionamento e' esplicito: questi modelli vogliono un livello,
    e senza lo scelgono loro. I token di ragionamento sono gia' dentro
    `output_tokens`, quindi il costo li comprende — misurato: 34 token di uscita
    di cui 23 di ragionamento, su una risposta di undici.
    """
    risposta = cliente.responses.create(
        model=scelto,
        instructions=sistema,
        input=messaggio,
        max_output_tokens=tetto,
        reasoning={"effort": config.LLM_SFORZO},
    )
    uso = risposta.usage
    incompleta = getattr(risposta, "incomplete_details", None)
    motivo = None if incompleta is None else getattr(incompleta, "reason", "?")
    return {
        "testo": risposta.output_text or "",
        "stop_reason": risposta.status if motivo is None
                       else f"{risposta.status}: {motivo}",
        "tagliata": motivo == MOTIVO_TAGLIO_OPENAI,
        "rifiutata": _rifiutata_openai(risposta),
        "entrata": getattr(uso, "input_tokens", 0) or 0,
        "uscita": getattr(uso, "output_tokens", 0) or 0,
    }


def _rifiutata_openai(risposta) -> bool:
    """Un rifiuto e' un pezzo di contenuto suo, non uno stato della risposta."""
    for voce in getattr(risposta, "output", []) or []:
        for pezzo in getattr(voce, "content", []) or []:
            if getattr(pezzo, "type", None) == "refusal":
                return True
    return False


def _chiedi_ad_anthropic(cliente, scelto: str, sistema: str, messaggio: str,
                         tetto: int) -> dict:
    """Una domanda a un modello Anthropic.

    Il pensiero e' in modalita' adattiva: il modello decide da solo quanto
    ragionare, invece di un tetto fisso di token che va indovinato.
    """
    risposta = cliente.messages.create(
        model=scelto,
        max_tokens=tetto,
        thinking={"type": "adaptive"},
        system=sistema,
        messages=[{"role": "user", "content": messaggio}],
    )
    return {
        "testo": "".join(b.text for b in risposta.content if b.type == "text"),
        "stop_reason": risposta.stop_reason,
        "tagliata": risposta.stop_reason == MOTIVO_TAGLIO_ANTHROPIC,
        "rifiutata": risposta.stop_reason == "refusal",
        "entrata": risposta.usage.input_tokens,
        "uscita": risposta.usage.output_tokens,
    }


ADATTATORI = {PROVIDER_OPENAI: _chiedi_a_openai,
              PROVIDER_ANTHROPIC: _chiedi_ad_anthropic}


def chiedi(fase: str, sistema: str, messaggio: str, scope: str | None = None,
           run_id: str | None = None, modello: str | None = None) -> dict:
    """Una domanda al modello. Ritorna testo, costo e come si e' fermato.

    `fase` non e' decorativa: e' il nome con cui la chiamata comparira' nel
    registro, e le quattro fasi dell'analisi qualitativa si distinguono solo da
    li'.

    Il fornitore lo decide il nome del modello, non una configurazione a parte.

    Il tetto di token in uscita **dipende dalla fase**, e non e' un dettaglio:
    la fase delle citazioni deve produrre una risposta molto piu' lunga delle
    altre, e col tetto normale usciva TAGLIATA a meta' di un JSON.
    """
    scelto = modello or config.LLM_MODELLO
    tetto = config.LLM_TOKEN_PER_FASE.get(fase, config.LLM_TOKEN_MASSIMI)
    fornitore = provider_di(scelto)
    dove = {"modello": scelto, "fase": fase, "scope": scope, "run_id": run_id}
    cliente = _client(fornitore)

    with calls.track(fornitore, f"messaggio:{fase}", scope=scope, run_id=run_id) as chiamata:
        chiamata.from_network()
        try:
            esito = ADATTATORI[fornitore](cliente, scelto, sistema, messaggio, tetto)
        except Exception as exc:
            _registra(dove, None, {"stato": calls.STATUS_ERROR,
                                   "errore": f"{type(exc).__name__}: {exc}"})
            raise LlmNonDisponibile(
                f"chiamata a {scelto} fallita: {type(exc).__name__}: {exc}"
            ) from exc

    speso = _registra(dove, esito, {"stato": calls.STATUS_OK,
                                    "stop_reason": esito["stop_reason"]})

    # Un rifiuto non e' una risposta vuota: va distinto, perche' significa che
    # il modello ha DECISO di non rispondere, e riprovare non serve.
    return {"testo": esito["testo"], "modello": scelto, "costo_usd": speso,
            "fornitore": fornitore, "stop_reason": esito["stop_reason"],
            "rifiutata": esito["rifiutata"], "tagliata": esito["tagliata"],
            "tetto_token": tetto,
            "token": {"entrata": esito["entrata"], "uscita": esito["uscita"]}}


def ricalcola_costi() -> dict:
    """Riapplica il listino alle chiamate gia' registrate. Ritorna cosa e' cambiato.

    Serve al caso normale, non a un caso strano: un modello nuovo si comincia a
    usare **prima** di avere il suo listino, e le chiamate di quel periodo
    restano registrate con costo zero. I token pero' sono salvati, quindi il
    costo si puo' calcolare dopo — e senza rifare una sola chiamata.

    Non tocca le righe il cui costo non cambia: cosi' il conto di cosa e'
    cambiato e' vero, e non «tutte».
    """
    with db_read() as conn:
        righe = [dict(r) for r in conn.execute(
            "SELECT id, modello, token_entrata, token_uscita, costo_usd FROM llm_calls"
        )]

    aggiornate, ancora_ignote = [], set()
    for riga in righe:
        if riga["modello"] not in config.LLM_PREZZI:
            ancora_ignote.add(riga["modello"])
            continue
        nuovo_costo = costo(riga["modello"], riga["token_entrata"], riga["token_uscita"])
        if abs(nuovo_costo - (riga["costo_usd"] or 0.0)) > 1e-9:
            aggiornate.append((nuovo_costo, riga["id"]))

    if aggiornate:
        with db_session() as conn:
            conn.executemany("UPDATE llm_calls SET costo_usd = ? WHERE id = ?",
                             aggiornate)

    referti = _ricalcola_referti()

    return {"righe_totali": len(righe), "righe_aggiornate": len(aggiornate),
            "referti_aggiornati": referti,
            "modelli_ancora_senza_listino": sorted(ancora_ignote),
            "speso": speso_totale()}


def _ricalcola_referti() -> int:
    """Rimette nei referti il costo delle chiamate che li hanno prodotti.

    Un referto porta il costo com'era al momento del salvataggio. Se il listino
    e' arrivato dopo — ed e' il caso normale con un modello nuovo — quel numero
    resta a zero: quattro referti su nove dicevano di non essere costati niente,
    mentre le loro chiamate erano registrate per intero.

    Il costo si ricalcola dalla somma delle chiamate dello stesso lavoro, che e'
    l'unico legame fra un referto e cio' che e' costato produrlo.
    """
    with db_read() as conn:
        da_correggere = [dict(r) for r in conn.execute("""
            SELECT r.id, r.costo_usd AS scritto, SUM(l.costo_usd) AS vero
            FROM referti r JOIN llm_calls l ON l.run_id = r.run_id
            WHERE r.run_id IS NOT NULL
            GROUP BY r.id
            HAVING ABS(COALESCE(r.costo_usd, 0) - SUM(l.costo_usd)) > 1e-9
        """)]

    if da_correggere:
        with db_session() as conn:
            conn.executemany("UPDATE referti SET costo_usd = ? WHERE id = ?",
                             [(r["vero"], r["id"]) for r in da_correggere])
    return len(da_correggere)


def speso_totale(run_id: str | None = None) -> dict:
    """Quanto si e' speso, in tutto o dentro un lavoro.

    Dice anche **quante chiamate non sanno quanto sono costate**, e con quali
    modelli. Senza, un listino mancante si legge come "gratis": il totale
    resterebbe a zero mentre i soldi escono, ed e' il difetto peggiore che
    questo modulo possa avere — nasconde proprio la cosa che esiste per mostrare.
    """
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
        per_modello = conn.execute(
            f"SELECT modello, COUNT(*) AS chiamate, "
            f"       COALESCE(SUM(token_entrata), 0) AS entrata, "
            f"       COALESCE(SUM(token_uscita), 0) AS uscita "
            f"FROM llm_calls {dove} GROUP BY modello", parametri,
        ).fetchall()

    ignoti = [dict(r) for r in per_modello if r["modello"] not in config.LLM_PREZZI]

    return {"chiamate": riga["chiamate"], "costo_usd": round(riga["costo"], 4),
            "token_entrata": riga["entrata"], "token_uscita": riga["uscita"],
            "chiamate_senza_listino": sum(r["chiamate"] for r in ignoti),
            "modelli_senza_listino": sorted(r["modello"] for r in ignoti),
            "token_senza_listino": sum(r["entrata"] + r["uscita"] for r in ignoti)}
