"""
impostazioni.py — le scelte che fai tu, e che devono sopravviverti.
# feat: il selettore del modello, globale.

Oggi c'e' una cosa sola qui dentro: **quale modello risponde alle analisi**. Il
modello si poteva gia' cambiare, ma solo con una variabile d'ambiente e solo
riavviando il processo — e il `.env` non veniva nemmeno letto, perche' manca
`python-dotenv` e Flask lo dice a ogni avvio. Una scelta che per cambiare vuole
un riavvio non e' una scelta: e' una configurazione.

## Perche' un file e non una tabella

Per lo stesso motivo della watchlist: `manage.py rebuild` cancella il database,
e una scelta che torna al predefinito dopo una ricostruzione **e' peggio di una
che non si puo' fare**, perche' cambia il conto senza dirlo. Il file si legge e
si corregge con un editor di testo, come tutto cio' che decidi tu.

## Il modello si valida, ma non si chiude in un elenco

Un nome che nessun fornitore riconosce viene rifiutato: `llm.chiedi` lo
scoprirebbe comunque, ma a chiamata gia' avviata e dentro un'analisi. Un nome
riconosciuto ma **senza listino** invece si accetta, e si dichiara: i prezzi si
aggiungono dopo e `manage.py costi` ricalcola all'indietro, mentre impedire un
modello nuovo perche' non conosciamo ancora il suo prezzo vorrebbe dire non
poterlo mai provare.
"""
import json
import logging
import os
import threading

import config

logger = logging.getLogger(__name__)

# La chiave del modello dentro al file. Una costante perche' la scrivono in tre:
# chi legge, chi salva, e chi migra un file scritto a mano.
CHIAVE_MODELLO = "llm_modello"

# I prefissi riconosciuti stanno in `core.llm`, che pero' importa questo modulo:
# chiederglieli qui creerebbe un anello. La domanda si gira al chiamante — chi
# valida passa la funzione — e cosi' i due moduli restano uno sopra l'altro.
_lucchetto = threading.Lock()


class ImpostazioniError(ValueError):
    """Una scelta che non si puo' accettare, col motivo scritto."""


def _vuote() -> dict:
    """Un file appena nato: dichiara la propria versione e nient'altro."""
    return {"versione": config.IMPOSTAZIONI_VERSIONE}


def leggi() -> dict:
    """Le impostazioni salvate. Un file assente non e' un errore: sono vuote.

    Un file illeggibile invece si dichiara e si ignora: le impostazioni hanno un
    predefinito sensato per tutto, e fermare il sistema perche' un file di
    preferenze e' rotto sarebbe una punizione sproporzionata.
    """
    if not config.IMPOSTAZIONI_PATH.exists():
        return _vuote()

    try:
        contenuto = json.loads(config.IMPOSTAZIONI_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[IMPOSTAZIONI] %s illeggibile (%s): valgono i predefiniti",
                       config.IMPOSTAZIONI_PATH.name, exc)
        return _vuote()

    return contenuto if isinstance(contenuto, dict) else _vuote()


def _salva(stato: dict) -> None:
    """Scrive le impostazioni in modo atomico: prima accanto, poi al posto."""
    config.IMPOSTAZIONI_PATH.parent.mkdir(parents=True, exist_ok=True)
    provvisorio = config.IMPOSTAZIONI_PATH.with_suffix(".json.tmp")
    provvisorio.write_text(json.dumps(stato, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    os.replace(provvisorio, config.IMPOSTAZIONI_PATH)


def modello() -> str:
    """Quale modello risponde alle analisi, adesso.

    Il file vince sul predefinito; il predefinito vince sul niente. Si rilegge a
    ogni chiamata e non si tiene in memoria: cambiare modello deve valere
    dall'analisi successiva, non dal prossimo riavvio, ed e' esattamente il
    difetto che questo modulo esiste per chiudere.
    """
    scelto = leggi().get(CHIAVE_MODELLO)
    return scelto if isinstance(scelto, str) and scelto.strip() else config.LLM_MODELLO


def scelto_da_te() -> bool:
    """Se il modello attuale e' una scelta salvata o solo il predefinito."""
    return isinstance(leggi().get(CHIAVE_MODELLO), str)


def imposta_modello(nome: str, riconosce) -> dict:
    """Salva il modello per tutte le analisi. Ritorna cosa e' cambiato.

    `riconosce` e' la funzione che dice di chi e' un modello — la passa chi
    chiama, perche' vive in `core.llm` e `core.llm` legge da qui: chiedergliela
    direttamente chiuderebbe un anello fra i due moduli.
    """
    pulito = (nome or "").strip()
    if not pulito:
        raise ImpostazioniError("serve il nome di un modello")

    try:
        fornitore = riconosce(pulito)
    except Exception as exc:
        raise ImpostazioniError(str(exc)) from exc

    with _lucchetto:
        stato = leggi()
        prima = stato.get(CHIAVE_MODELLO)
        stato["versione"] = config.IMPOSTAZIONI_VERSIONE
        stato[CHIAVE_MODELLO] = pulito
        _salva(stato)

    logger.info("[IMPOSTAZIONI] modello: %s -> %s", prima or config.LLM_MODELLO, pulito)
    return {"modello": pulito, "fornitore": fornitore, "prima": prima,
            "senza_listino": pulito not in config.LLM_PREZZI}
