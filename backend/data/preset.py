"""
preset.py — i verdetti dei preset: misurati, non scritti a mano.
# feat: `manage.py preset` li rigioca tutti e riscrive il file.

## Il difetto che questo modulo esiste per impedire

La prima versione dei preset aveva i numeri scritti a mano accanto ai criteri.
Funzionava finche' nessuno toccava niente — e sarebbe diventata falsa **in
silenzio** al primo cambio di soglia del paragone, o semplicemente al primo mese
di dati in piu'. Un verdetto che non sa quando e' stato misurato non si puo'
smentire: si puo' solo credere.

Qui ogni verdetto porta con se' la data, le soglie e la finestra di dati con cui
e' stato prodotto, e `stato()` confronta quei tre valori con quelli di ADESSO.
Se qualcosa non combacia lo dice, invece di lasciare che il numero vecchio
sembri nuovo.

## Perche' il file sta in git

E' l'unico JSON di `data/` che ci sta, e non e' una svista. Gli altri sono tuoi
— la watchlist, i grafici, le impostazioni — e nessuno li puo' ricostruire. Un
verdetto invece e' una **misura**: chi clona il repo deve poter vedere subito
che il buon drawdown perde, senza prima derivare tre tabelle e aspettare settanta
secondi. E rigiocarlo produce un diff, che si legge.
"""
import json
import logging
from datetime import UTC, datetime

import config
from core.db import db_read
from data import rigioco
from domain import scansione

logger = logging.getLogger(__name__)

# Le forme che un verdetto puo' avere, guardando i tre orizzonti insieme.
# Sono l'unica cosa che i tre numeri dicono e che un numero solo non direbbe.
VINCE_SEMPRE = "vince a tutti gli orizzonti"
LENTO = "lento: perde a breve e vince a lungo"
PERDE_SEMPRE = "perde a tutti gli orizzonti"
MISTO = "misto: non c'e' una direzione sola"
NON_GIUDICABILE = "non giudicabile: troppo pochi mesi con abbastanza titoli"


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _finestra_dati() -> dict:
    """Da quando a quando arrivano i prezzi mensili, adesso."""
    with db_read() as conn:
        riga = conn.execute(
            "SELECT MIN(mese) AS dal, MAX(mese) AS al, COUNT(DISTINCT mese) AS mesi "
            "FROM universe_prezzi_mensili"
        ).fetchone()
    return {"dal": riga["dal"], "al": riga["al"], "mesi": riga["mesi"] or 0}


def _forma(per_orizzonte: dict) -> str:
    """Che forma ha il verdetto, guardando i tre orizzonti insieme."""
    giudicabili = [r for r in per_orizzonte.values() if r["vantaggio"] is not None]
    if not giudicabili:
        return NON_GIUDICABILE

    positivi = [r["vantaggio"] > 0 for r in giudicabili]
    if all(positivi):
        return VINCE_SEMPRE
    if not any(positivi):
        return PERDE_SEMPRE

    # Lento significa una cosa precisa: il breve perde e il lungo vince. Il
    # contrario — vince subito e poi perde — non e' lentezza, e' rumore.
    ordinati = sorted(per_orizzonte.items(), key=lambda voce: int(voce[0]))
    primo, ultimo = ordinati[0][1]["vantaggio"], ordinati[-1][1]["vantaggio"]
    if primo is not None and ultimo is not None and primo <= 0 < ultimo:
        return LENTO
    return MISTO


def _misura(nome: str, criteri: dict) -> dict:
    """Rigioca un preset e ne estrae il verdetto, senza il dettaglio mensile."""
    esito = rigioco.rigioca(criteri)
    per_orizzonte = {}
    for orizzonte in esito["orizzonti_mesi"]:
        conto = esito["riepilogo"][str(orizzonte)]
        per_orizzonte[str(orizzonte)] = {
            "mesi_utili": conto["mesi_utili"],
            "vinti": conto["vinti"],
            "quota_vinti": conto["quota_vinti"],
            "vantaggio": conto["vantaggio_mediano"],
            "trovati_per_mese": conto.get("trovati_per_mese"),
        }

    riferimento = per_orizzonte.get(str(config.PRESET_ORIZZONTE_DI_RIFERIMENTO), {})
    vantaggio = riferimento.get("vantaggio")
    return {
        "nome": nome,
        "orizzonti": per_orizzonte,
        "forma": _forma(per_orizzonte),
        # «Vince» si decide sull'orizzonte di riferimento, e vale `None` quando
        # li' non c'e' abbastanza da giudicare: non e' un no, e' un non lo so.
        "vince": None if vantaggio is None else vantaggio > 0,
        "mesi_giudicabili": riferimento.get("mesi_utili", 0),
    }


def rigioca_tutti() -> dict:
    """Rigioca ogni preset e scrive il file dei verdetti. Ritorna cosa ha scritto."""
    verdetti = {nome: _misura(nome, dati["criteri"])
                for nome, dati in scansione.PRESET.items()}

    documento = {
        "versione": config.PRESET_VERDETTI_VERSIONE,
        "misurato_il": _adesso(),
        "soglie": rigioco.soglie(),
        "orizzonti_mesi": list(config.RIGIOCO_ORIZZONTI_MESI),
        "orizzonte_di_riferimento": config.PRESET_ORIZZONTE_DI_RIFERIMENTO,
        "finestra_dati": _finestra_dati(),
        "verdetti": verdetti,
    }

    percorso = config.PRESET_VERDETTI_PATH
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(documento, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    logger.info("[PRESET] %d verdetti scritti in %s", len(verdetti), percorso)
    return documento


def leggi() -> dict | None:
    """I verdetti salvati, o `None` se non sono mai stati misurati."""
    percorso = config.PRESET_VERDETTI_PATH
    if not percorso.exists():
        return None
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("[PRESET] %s illeggibile: i preset restano senza verdetto",
                         percorso)
        return None


def _invecchiato(documento: dict) -> list[str]:
    """Cosa e' cambiato da quando i verdetti sono stati misurati.

    Tre domande, e sono le tre che rendono vecchio un verdetto senza che si
    veda: sono cambiate le soglie del paragone? gli orizzonti? ci sono mesi di
    dati che allora non c'erano?
    """
    motivi = []
    soglie_adesso = rigioco.soglie()
    for chiave in ("capitalizzazione_minima", "scambiato_minimo_al_giorno"):
        if documento.get("soglie", {}).get(chiave) != soglie_adesso[chiave]:
            motivi.append(f"la soglia «{chiave}» e' cambiata")

    if documento.get("orizzonti_mesi") != list(config.RIGIOCO_ORIZZONTI_MESI):
        motivi.append("gli orizzonti misurati non sono quelli di adesso")

    allora = (documento.get("finestra_dati") or {}).get("al")
    adesso = _finestra_dati()["al"]
    if allora and adesso and adesso > allora:
        motivi.append(f"ci sono dati fino a {adesso}, i verdetti si fermano a {allora}")

    return motivi


def con_verdetto() -> dict:
    """I preset con il loro verdetto, e se quel verdetto e' ancora attuale.

    E' cio' che l'API serve alla pagina: la definizione sta nel dominio, la
    misura nel file, e il giudizio su quanto sia fresca si fa qui.
    """
    documento = leggi()
    invecchiati = _invecchiato(documento) if documento else []
    verdetti = (documento or {}).get("verdetti", {})

    elenco = []
    for nome, dati in scansione.PRESET.items():
        elenco.append({"nome": nome, **dati, "verdetto": verdetti.get(nome)})

    return {
        "preset": elenco,
        "misurato_il": (documento or {}).get("misurato_il"),
        "soglie": (documento or {}).get("soglie"),
        "finestra_dati": (documento or {}).get("finestra_dati"),
        "da_rimisurare": bool(invecchiati) or documento is None,
        "perche": invecchiati or ([] if documento else
                                  ["i preset non sono mai stati rigiocati"]),
        "azione": "python manage.py preset",
    }
