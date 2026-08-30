"""
verdetto.py — cosa dicono insieme le altre analisi, e dove si contraddicono.
# feat (Blocco 9): il settimo metodo, quello che non ha una fonte propria.

Il verdetto non guarda nessun dato: guarda i **referti** degli altri sei. Ed e'
per questo che la sua parte piu' utile non e' la sintesi — quella la farebbe
chiunque leggendo di seguito — ma le **contraddizioni**: la lettura tecnica che
vede forza mentre i segnali fondamentali si deteriorano, il DCF che dice caro
mentre l'earnings call racconta un'accelerazione.

## L'eta' di ogni referto e' parte del referto

Un verdetto che mette insieme una lettura tecnica di tre mesi fa e una
fondamentale di stamattina produce una sintesi coerente e sbagliata: il difetto
non si vede, perche' il testo non dice quando e' stato scritto. Qui ogni
referto arriva al modello **con la sua eta' in giorni**, e quelli oltre la
soglia sono marcati come vecchi nel testo stesso.

## Non produce un punteggio

Il vecchio sistema chiudeva con un giudizio sintetico. Un numero unico che
riassume sei analisi discordanti nasconde esattamente cio' che l'utente deve
vedere — che discordano. Qui il verdetto dice dove convergono, dove no, e cosa
lo farebbe cambiare.
"""
import json
import logging

import config
from core import llm
from data import materiale
from data.materiale import AnalisiError

logger = logging.getLogger(__name__)

METODO = "verdetto"

# Quanti referti bastano perche' una sintesi sia una sintesi. Con uno solo non
# c'e' niente da confrontare, e il verdetto sarebbe una parafrasi.
REFERTI_MINIMI = 2

# I campi che non si mandano: sono i dati grezzi su cui i referti poggiano —
# griglie, metriche, citazioni, menzioni — e qui servirebbero solo a riempire
# il contesto di numeri che il verdetto non deve ricalcolare.
CAMPI_PESANTI = frozenset({
    "metriche", "misure", "segnali", "metriche_mancanti", "confronto_industria",
    "citations", "citazioni_scartate", "senza_riscontro", "copertura",
    "menzioni_notizie", "menzioni_call", "dcf", "classificazione_scartata",
})


def _sintesi(contenuto: dict) -> dict:
    """Un referto ridotto alla sua prosa: quello che si legge, non su cosa poggia."""
    ridotto = {}
    for chiave, valore in (contenuto or {}).items():
        if chiave in CAMPI_PESANTI:
            continue
        if isinstance(valore, str) and valore.strip():
            ridotto[chiave] = _tronca(valore)
        elif isinstance(valore, list) and valore:
            ridotto[chiave] = [_tronca(str(v)) for v in valore[:config.VERDETTO_VOCI_MASSIME]]
        elif chiave == "classificazione" and isinstance(valore, dict):
            ridotto[chiave] = {nome: (dati or {}).get("etichette")
                               for nome, dati in valore.items()}
    return ridotto


def _tronca(testo: str) -> str:
    """Un testo tagliato alla lunghezza utile, che dichiara il taglio."""
    limite = config.VERDETTO_TESTO_CARATTERI
    return testo if len(testo) <= limite else testo[:limite] + " […]"


def _eta_in_giorni(quando: str) -> int | None:
    """Quanti giorni ha questo referto. `None` se la data non si legge."""
    from datetime import UTC, datetime  # noqa: PLC0415

    try:
        scritto = datetime.fromisoformat(quando)
    except (TypeError, ValueError):
        logger.warning("[VERDETTO] data del referto illeggibile: %r", quando)
        return None
    if scritto.tzinfo is None:
        scritto = scritto.replace(tzinfo=UTC)
    return (datetime.now(UTC) - scritto).days


def referti_da_sintetizzare(tutti: list[dict], metodi: dict) -> tuple[list[dict], list[str]]:
    """L'ultimo referto di ogni metodo, con la sua eta'. E quali metodi mancano.

    Riceve i referti e il registro dei metodi invece di andarseli a prendere:
    e' cio' che tiene questo modulo fuori dall'anello con `analisi.py`, che lo
    importa per eseguirlo. Solo l'ultimo per metodo: due letture tecniche della
    stessa settimana non aggiungono niente e raddoppiano il contesto.
    """
    ultimi: dict[str, dict] = {}
    for referto in tutti:
        if referto["metodo"] != METODO:
            ultimi.setdefault(referto["metodo"], referto)

    scelti = []
    for metodo, referto in ultimi.items():
        eta = _eta_in_giorni(referto["creato_il"])
        scelti.append({
            "metodo": metodo,
            "nome": metodi.get(metodo, {}).get("nome", metodo),
            "scritto_il": referto["creato_il"],
            "eta_in_giorni": eta,
            "vecchio": eta is not None and eta > config.VERDETTO_GIORNI_VECCHIO,
            "contenuto": _sintesi(referto["contenuto"]),
        })

    mancanti = [f"{dati['nome']}: nessun referto"
                for metodo, dati in metodi.items()
                if metodo != METODO and metodo not in ultimi]
    return sorted(scelti, key=lambda r: r["metodo"]), mancanti


def esegui(simbolo: str, lavoro, tutti: list[dict], metodi: dict) -> dict:
    """Mette i referti uno accanto all'altro e chiede dove si contraddicono."""
    run_id = lavoro.run_id
    scelti, mancanti = referti_da_sintetizzare(tutti, metodi)

    if len(scelti) < REFERTI_MINIMI:
        raise AnalisiError(
            f"per il verdetto su {simbolo} servono almeno {REFERTI_MINIMI} referti "
            f"di metodi diversi, ce ne sono {len(scelti)}. Con uno solo la sintesi "
            f"sarebbe una parafrasi. Mancano — {'; '.join(mancanti)}"
        )

    sistema = materiale.prompt(
        "analisi_verdetto",
        contesto=materiale.contesto(simbolo, run_id),
        referti=json.dumps(scelti, indent=2, ensure_ascii=False),
        mancanti="\n".join(f"- {m}" for m in mancanti) or "nessuno: ci sono tutti",
    )

    risposta = llm.chiedi(fase="analisi_verdetto", sistema=sistema,
                          messaggio=f"Metti insieme i referti su {simbolo}.",
                          scope=simbolo, run_id=run_id)
    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**materiale.leggi_json(risposta["testo"]),
                          "referti_letti": [{"metodo": r["metodo"],
                                             "scritto_il": r["scritto_il"],
                                             "eta_in_giorni": r["eta_in_giorni"],
                                             "vecchio": r["vecchio"]} for r in scelti],
                          "metodi_senza_referto": mancanti},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}
