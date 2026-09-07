"""
rigioco.py — un criterio rigiocato all'indietro, contro cio' che avrebbe fatto
             non usarlo affatto.
# feat: la domanda «questo criterio ha mai funzionato?» prima di accenderlo.

## Perche' esiste

I sei pesi del rilevatore spin-off sono nati da un caso — SanDisk — e quando
sono stati rigiocati hanno detto di no: tolto quel caso, la fascia alta rendeva
meno delle altre. Quella verifica e' arrivata **dopo** che il punteggio era gia'
in pagina. Questo modulo la mette prima, e la rende possibile per qualunque
criterio dello scanner.

## Il pezzo che al rigioco degli spin-off mancava: il paragone

Confrontare fra loro le fasce di punteggio dice solo che una fascia va meglio di
un'altra. Non dice la cosa che conta: **meglio di non filtrare affatto?** Un
criterio che trova titoli col +12% in sei mesi sembra bravo, finche' non si
scopre che in quei sei mesi tutto il mercato ha fatto +15%.

Qui ogni mese porta due numeri: la mediana di chi il criterio ha trovato, e la
mediana di tutti i titoli che a quella data avevano un prezzo. La differenza fra
i due e' l'unica misura onesta di cosa aggiunge il criterio.

## Cosa NON e'

Non e' un backtest di strategia: non si compra e non si vende, non ci sono costi
ne' pesi di portafoglio. E' la domanda «cosa avresti trovato quel mese, e come
sarebbe andata» ripetuta su tutti i mesi che i dati coprono.

E resta point-in-time davvero: i bilanci di un mese sono quelli che a quella
data erano gia' DEPOSITATI, con le date vere dell'indice dei filing dove ci
sono. Un rigioco che guarda i bilanci per fine periodo invece che per data di
deposito si racconta meglio di com'e' andato, di circa quaranta giorni.
"""
import logging
import queue
import threading
from datetime import date

from core import registry
from core.db import db_read
from data import fondamentali
from domain import publication_dates, scansione

logger = logging.getLogger(__name__)

# Su quanti mesi si misura il rendimento successivo.
ORIZZONTE_MESI = 6

# Quanti titoli deve trovare un mese perche' la sua mediana significhi qualcosa.
# Sotto questa soglia il mese si conta ma non entra nel riepilogo: la mediana di
# due titoli e' un aneddoto con l'aria di una misura.
TROVATI_MINIMI = 5


def _mesi_disponibili() -> list[str]:
    with db_read() as conn:
        righe = conn.execute(
            "SELECT DISTINCT mese FROM universe_prezzi_mensili ORDER BY mese"
        ).fetchall()
    return [r["mese"] for r in righe]


def _fine_mese(mese: str) -> str:
    """L'ultimo giorno del mese, in ISO: e' la data a cui si taglia il passato."""
    anno, numero = int(mese[:4]), int(mese[5:7])
    prossimo = date(anno + (numero == 12), numero % 12 + 1, 1)
    return date.fromordinal(prossimo.toordinal() - 1).isoformat()


def _mese_piu(mese: str, quanti: int) -> str:
    anno, numero = int(mese[:4]), int(mese[5:7])
    totale = (anno * 12 + numero - 1) + quanti
    return f"{totale // 12:04d}-{totale % 12 + 1:02d}"


def _mediana(valori: list[float]) -> float | None:
    if not valori:
        return None
    ordinati = sorted(valori)
    meta = len(ordinati) // 2
    if len(ordinati) % 2:
        return ordinati[meta]
    return (ordinati[meta - 1] + ordinati[meta]) / 2


def _bilanci_di_tutti() -> dict[str, tuple[dict, dict]]:
    """Voci e depositi di ogni titolo, letti una volta sola.

    Una lettura per titolo dentro al giro dei mesi sarebbe la stessa query
    ripetuta ottanta volte a testa: qui si prende tutto una volta e il rigioco
    diventa aritmetica.
    """
    with db_read() as conn:
        righe = conn.execute(
            "SELECT symbol, report_date, voce, valore, filing_date "
            "FROM universe_fondamentali WHERE valore IS NOT NULL"
        ).fetchall()

    per_simbolo: dict[str, tuple[dict, dict]] = {}
    for riga in righe:
        voci, depositi = per_simbolo.setdefault(riga["symbol"], ({}, {}))
        voci.setdefault(riga["voce"], {})[riga["report_date"]] = riga["valore"]
        if riga["filing_date"]:
            depositi[riga["report_date"]] = (riga["filing_date"], "filing_index")
    return per_simbolo


def _rendimento(chiusure: dict[str, float], mese: str, orizzonte: int) -> float | None:
    """Quanto ha reso dal fine mese a `orizzonte` mesi dopo. `None` se manca un capo."""
    adesso = chiusure.get(mese)
    dopo = chiusure.get(_mese_piu(mese, orizzonte))
    if not adesso or not dopo:
        return None
    return dopo / adesso - 1


def rigioca(criteri: dict, orizzonte: int = ORIZZONTE_MESI) -> dict:
    """Rigioca un insieme di criteri su tutti i mesi che i dati coprono.

    Ritorna, per ogni mese: quanti titoli il criterio avrebbe trovato, come sono
    andati, e come e' andato **tutto il resto** nello stesso periodo.
    """
    sconosciuti = sorted(set(criteri) - set(scansione.CRITERI))
    if sconosciuti:
        raise ValueError(f"criteri sconosciuti: {', '.join(sconosciuti)}")

    prezzi = fondamentali.chiusure_mensili()
    if not prezzi:
        raise ValueError("lo storico mensile non e' stato derivato: "
                         "senza, non c'e' niente da rigiocare")

    bilanci = _bilanci_di_tutti()
    mesi = _mesi_disponibili()
    # Gli ultimi mesi non hanno un futuro da misurare: si fermano prima.
    misurabili = [m for m in mesi if _mese_piu(m, orizzonte) <= mesi[-1]]

    per_mese = []
    for mese in misurabili:
        quando = _fine_mese(mese)
        trovati, tutti = [], []

        for simbolo, chiusure in prezzi.items():
            resa = _rendimento(chiusure, mese, orizzonte)
            if resa is None:
                continue
            tutti.append(resa)

            voci, depositi = bilanci.get(simbolo, ({}, {}))
            if not voci:
                continue
            periodi = sorted(voci.get("total_revenue", {}))
            pubblici = [p for p in periodi
                        if publication_dates.was_public(depositi, p, quando)]
            misurato = {"fondamentali": scansione.fondamentali(voci, pubblici)}
            soddisfa, _ = scansione.valuta(misurato, criteri)
            if soddisfa:
                trovati.append(resa)

        per_mese.append({
            "mese": mese,
            "trovati": len(trovati),
            "universo": len(tutti),
            "mediana_trovati": _mediana(trovati),
            "mediana_universo": _mediana(tutti),
        })

    return {"criteri": criteri, "orizzonte_mesi": orizzonte,
            "mesi": per_mese, "riepilogo": riepiloga(per_mese)}


def riepiloga(per_mese: list[dict]) -> dict:
    """Il conto finale: in quanti mesi il criterio ha battuto il non-filtrare.

    Si contano i MESI vinti e non la media delle differenze: una media si fa
    dominare da un mese solo, e la domanda «funziona?» e' «funziona spesso?».
    """
    validi = [m for m in per_mese
              if m["trovati"] >= TROVATI_MINIMI
              and m["mediana_trovati"] is not None
              and m["mediana_universo"] is not None]
    if not validi:
        return {"mesi_utili": 0, "vinti": 0, "quota_vinti": None,
                "vantaggio_mediano": None,
                "reason": f"nessun mese con almeno {TROVATI_MINIMI} titoli trovati: "
                          f"il criterio e' troppo stretto per essere giudicato"}

    differenze = [m["mediana_trovati"] - m["mediana_universo"] for m in validi]
    vinti = sum(1 for d in differenze if d > 0)
    return {
        "mesi_utili": len(validi),
        "vinti": vinti,
        "quota_vinti": round(vinti / len(validi), 3),
        "vantaggio_mediano": round(_mediana(differenze), 4),
        "trovati_per_mese": round(sum(m["trovati"] for m in validi) / len(validi), 1),
        "reason": None,
    }


# --- il giro in un thread, per il pulsante ----------------------------------

JOB_KIND = "rigioco"

# Quanto si aspetta che il thread consegni il proprio run_id.
ATTESA_AVVIO_S = 5.0

_esiti: dict[str, dict] = {}
_lucchetto = threading.Lock()


def _esegui(criteri: dict, orizzonte: int, consegna: queue.Queue) -> dict:
    """Un rigioco dentro il registro dei lavori: si vede e si ferma."""
    etichetta = f"rigioco di {len(criteri)} criteri su {orizzonte} mesi"
    with registry.job(JOB_KIND, etichetta, total=1) as lavoro:
        consegna.put(lavoro.run_id)
        esito = rigioca(criteri, orizzonte)
        esito["run_id"] = lavoro.run_id
        lavoro.advance(detail=f"{esito['riepilogo']['mesi_utili']} mesi giudicabili")

    with _lucchetto:
        _esiti[lavoro.run_id] = esito
    return esito


def avvia(criteri: dict, orizzonte: int | None = None) -> str:
    """Avvia un rigioco in un thread e ritorna il run_id con cui seguirlo.

    I criteri si controllano PRIMA di partire: un errore sollevato dentro al
    thread non tornerebbe a chi ha premuto, che resterebbe ad aspettare un
    run_id che non arriva mai.
    """
    sconosciuti = sorted(set(criteri) - set(scansione.CRITERI))
    if sconosciuti:
        raise ValueError(f"criteri sconosciuti: {', '.join(sconosciuti)}")
    if not _mesi_disponibili():
        raise ValueError("lo storico mensile non e' stato derivato: senza, non "
                         "c'e' niente da rigiocare")

    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_esegui,
                     args=(criteri, orizzonte or ORIZZONTE_MESI, consegna),
                     name="rigioco", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def esito(run_id: str) -> dict | None:
    """Il risultato di un rigioco finito, o None se non c'e' (ancora)."""
    with _lucchetto:
        return _esiti.get(run_id)
