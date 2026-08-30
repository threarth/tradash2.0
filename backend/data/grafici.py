"""
grafici.py — quali indicatori hai scelto, e per quale titolo.
# feat (Blocco 6): impostazioni tue, quindi in un file, non in una tabella.

Stesso trattamento della watchlist, e per lo stesso motivo: la configurazione
del grafico non si ricostruisce da nessuna parte. Sta in `data/grafici.json`,
leggibile e correggibile a mano, fuori da git, e `manage.py rebuild` non la
tocca perche' non e' nel database.

Piu' semplice della watchlist di un pezzo: qui non serve una copia in SQLite,
perche' nessuno fa JOIN sulle impostazioni di un grafico.
"""
import json
import logging
import os
import threading
from datetime import UTC, datetime

import config
from domain import indicators

logger = logging.getLogger(__name__)

# La chiave sotto cui sta la configurazione usata quando un titolo non ne ha una sua.
CHIAVE_PREDEFINITA = "predefinita"

_lucchetto = threading.Lock()


class GraficiError(ValueError):
    """Configurazione del grafico non valida, o file illeggibile."""


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _vuoto() -> dict:
    """Nessuna impostazione salvata: si parte dalla configurazione di serie."""
    return {"versione": config.GRAFICI_FILE_VERSION, "aggiornato_il": _adesso(),
            CHIAVE_PREDEFINITA: indicators.DEFAULT_CONFIG, "per_titolo": {}}


def _carica() -> dict:
    """Legge le impostazioni. File assente = nessuna impostazione, non un errore."""
    if not config.GRAFICI_PATH.exists():
        return _vuoto()
    try:
        contenuto = json.loads(config.GRAFICI_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise GraficiError(f"{config.GRAFICI_PATH.name} non e' leggibile: {exc}") from exc

    versione = contenuto.get("versione")
    if versione != config.GRAFICI_FILE_VERSION:
        raise GraficiError(
            f"le impostazioni dichiarano la versione {versione}, questo codice legge "
            f"la {config.GRAFICI_FILE_VERSION}"
        )
    return contenuto


def _salva(stato: dict) -> None:
    """Scrittura atomica: un file troncato a meta' perderebbe tutte le impostazioni."""
    stato["aggiornato_il"] = _adesso()
    config.GRAFICI_PATH.parent.mkdir(parents=True, exist_ok=True)
    provvisorio = config.GRAFICI_PATH.with_suffix(".json.tmp")
    provvisorio.write_text(json.dumps(stato, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    os.replace(provvisorio, config.GRAFICI_PATH)


def configurazione(simbolo: str | None = None) -> dict:
    """La configurazione di un titolo, o quella predefinita se non ne ha una sua."""
    stato = _carica()
    if simbolo:
        sua = stato.get("per_titolo", {}).get(simbolo.strip().upper())
        if sua:
            return sua
    return stato.get(CHIAVE_PREDEFINITA) or indicators.DEFAULT_CONFIG


def imposta(simbolo: str | None, configurazione_nuova: dict) -> dict:
    """Salva la configurazione di un titolo, o quella predefinita se `simbolo` e' vuoto.

    Prima di scrivere si prova a calcolarla: una configurazione che il motore
    rifiuta — un ciclo, un `source` che non esiste — non deve poter finire nel
    file, dove romperebbe il grafico a ogni apertura invece che una volta sola.
    """
    try:
        indicators.compute([], configurazione_nuova)
        indicators.valida(configurazione_nuova)
    except indicators.IndicatorConfigError as exc:
        raise GraficiError(f"configurazione non valida: {exc}") from exc

    with _lucchetto:
        stato = _carica()
        if simbolo:
            stato.setdefault("per_titolo", {})[simbolo.strip().upper()] = configurazione_nuova
        else:
            stato[CHIAVE_PREDEFINITA] = configurazione_nuova
        _salva(stato)

    logger.info("[GRAFICI] impostazioni salvate per %s", simbolo or "tutti i titoli")
    return configurazione_nuova


def dimentica(simbolo: str) -> bool:
    """Toglie le impostazioni di un titolo: torna a usare quella predefinita."""
    with _lucchetto:
        stato = _carica()
        tolto = stato.get("per_titolo", {}).pop(simbolo.strip().upper(), None) is not None
        if tolto:
            _salva(stato)
    return tolto
