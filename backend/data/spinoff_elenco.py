"""
spinoff_elenco.py — chi si e' separato da chi, e quando.
# feat: l'unico dato che non viene da Defeatbeta, e solo quando lo chiedi tu.

## Perche' esiste

Defeatbeta non sa dire chi e' nato da uno spin-off. L'indice dei filing e'
recente-only — verificato su SNDK il 04/09/2026: 182 depositi, il piu' vecchio
del 2026-01-21, nessun modulo 10-12B, che sarebbe **il** documento con cui uno
spin-off si registra. Senza sapere chi si e' separato non c'e' niente da
cercare, e questo elenco e' l'unica cosa che il sistema non puo' derivare da se'.

## Il confine

La decisione del 30/08 diceva fonte unica e niente provider esterni. Qui si
prende un elenco di NOMI, non dei prezzi — quelli restano di Defeatbeta — e si
prende **solo quando premi il pulsante**. Niente in background, niente
all'avvio, niente a scadenza: una pagina scaricata, letta, salvata, e finita li'.

L'elenco salvato dice **quando e' stato preso**. Un elenco di tre mesi fa non e'
sbagliato: e' incompleto, e chi lo guarda deve poterlo sapere senza indovinare.

## I segnali, quando li chiedi

Il fetch prende i nomi. Il **calcolo** e' un secondo pulsante, e legge da
Defeatbeta i prezzi e i bilanci di ogni candidato per misurare i sei segnali di
`domain/spinoff_segnali.py`. Anche quello parte solo se lo premi: sono decine di
letture, ognuna lenta la prima volta, e farle partire da sole vorrebbe dire
spendere il tempo di qualcuno senza che lo abbia chiesto.

Il risultato si salva accanto all'elenco, nello stesso file: sono lo stesso
oggetto guardato due volte, e tenerli in due posti vorrebbe dire poterli
disallineare.

## Cosa si legge

La pagina ha una tabella sola, cinque colonne: data, simbolo della madre,
simbolo della nata, nome della madre, nome della nata. Si legge con la libreria
standard — nessuna dipendenza nuova per cinque colonne — e se la pagina cambia
forma il risultato e' zero righe, non righe sbagliate: allora **il file di prima
resta dov'e'**, perche' sovrascrivere un elenco buono con uno vuoto sarebbe
perdere l'unico dato non ricostruibile di questo modulo.
"""
import json
import logging
import os
import queue
import threading
import urllib.request
from datetime import UTC, date, datetime
from html.parser import HTMLParser

import config
from core import calls, registry
from data import defeatbeta
from domain import prospetti, spinoff_segnali

logger = logging.getLogger(__name__)

PROVIDER = "stockanalysis"
JOB_KIND = "spinoff"
JOB_LABEL = "elenco degli spin-off"
JOB_KIND_SEGNALI = "spinoff_segnali"
JOB_LABEL_SEGNALI = "segnali degli spin-off"

# Quanto si aspetta che il thread consegni il proprio run_id.
ATTESA_AVVIO_S = 5.0

# Quante colonne ha la riga che ci interessa, e cosa c'e' in ognuna.
COLONNE = 5
COL_DATA, COL_MADRE, COL_NATA, COL_NOME_MADRE, COL_NOME_NATA = range(COLONNE)

# I mesi come li scrive la pagina. Sono in inglese e non cambiano: un elenco
# esplicito e' piu' onesto di una libreria di localizzazione chiamata per tre
# lettere.
MESI = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


class SpinoffError(RuntimeError):
    """L'elenco non si e' potuto aggiornare, col motivo scritto."""


class _LettoreTabella(HTMLParser):
    """Prende le celle di ogni riga della prima tabella della pagina.

    Scritto a mano e non con una libreria: sono cinque colonne, e una
    dipendenza in piu' andrebbe dichiarata, aggiornata e fidata per sempre.
    """

    def __init__(self):
        super().__init__()
        self.righe: list[list[str]] = []
        self._nella_tabella = False
        self._riga: list[str] | None = None
        self._cella: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._nella_tabella = True
        elif tag == "tr" and self._nella_tabella:
            self._riga = []
        elif tag == "td" and self._riga is not None:
            self._cella = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._nella_tabella = False
        elif tag == "td" and self._cella is not None:
            self._riga.append("".join(self._cella).strip())
            self._cella = None
        elif tag == "tr" and self._riga is not None:
            if len(self._riga) == COLONNE:
                self.righe.append(self._riga)
            self._riga = None

    def handle_data(self, dato):
        if self._cella is not None:
            self._cella.append(dato)


def _data_iso(scritta: str) -> str | None:
    """«Aug 4, 2026» diventa «2026-08-04». Una data che non si legge resta None."""
    pezzi = scritta.replace(",", " ").split()
    if len(pezzi) != 3:
        return None
    mese = MESI.get(pezzi[0][:3].lower())
    if mese is None:
        return None
    try:
        return date(int(pezzi[2]), mese, int(pezzi[1])).isoformat()
    except ValueError:
        return None


def analizza(html: str) -> list[dict]:
    """Le righe della tabella, ripulite. Funzione pura: si prova senza rete.

    Una riga senza data o senza il simbolo della nata viene scartata: sono i due
    dati per cui l'elenco esiste, e una riga a meta' e' un candidato che non si
    puo' ne' cercare ne' datare.
    """
    lettore = _LettoreTabella()
    lettore.feed(html)

    trovate = []
    for riga in lettore.righe:
        quando = _data_iso(riga[COL_DATA])
        nata = riga[COL_NATA].strip().upper()
        if not quando or not nata:
            continue
        trovate.append({
            "symbol": nata,
            "data": quando,
            "parent": riga[COL_MADRE].strip().upper() or None,
            "nome": riga[COL_NOME_NATA].strip() or None,
            "nome_parent": riga[COL_NOME_MADRE].strip() or None,
        })
    return trovate


def _scarica(anno: int, run_id: str | None) -> str:
    """Una pagina, una volta. Ogni lettura lascia la sua riga nel registro."""
    url = config.SPINOFF_URL_MODELLO.format(anno=anno)
    richiesta = urllib.request.Request(
        url, headers={"User-Agent": config.SPINOFF_USER_AGENT}
    )

    with calls.track(PROVIDER, f"spinoffs/{anno}", run_id=run_id) as chiamata:
        chiamata.from_network()
        try:
            with urllib.request.urlopen(richiesta, timeout=config.SPINOFF_TIMEOUT_S) as risposta:
                grezzo = risposta.read(config.SPINOFF_MAX_BYTE)
        except Exception as exc:
            raise SpinoffError(f"{url} non risponde: {type(exc).__name__}: {exc}") from exc

    return grezzo.decode("utf-8", errors="replace")


def _anni_da_leggere() -> list[int]:
    """L'anno in corso e quelli prima: la pagina e' per anno, la finestra no."""
    oggi = datetime.now(UTC).year
    return [oggi - indietro for indietro in range(config.SPINOFF_ANNI_INDIETRO + 1)]


def elenco() -> dict:
    """L'elenco salvato, con la data in cui e' stato preso. Mai un None muto."""
    if not config.SPINOFF_PATH.exists():
        return {"disponibile": False, "preso_il": None, "calcolato_il": None,
                "anni": [], "righe": [], "pesi": spinoff_segnali.PESI,
                "motivo": "l'elenco non e' mai stato scaricato",
                "azione": "premi «Aggiorna l'elenco»: scarica la pagina di "
                          "stockanalysis.com e la salva qui"}

    try:
        contenuto = json.loads(config.SPINOFF_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"disponibile": False, "preso_il": None, "calcolato_il": None,
                "anni": [], "righe": [], "pesi": spinoff_segnali.PESI,
                "motivo": f"{config.SPINOFF_PATH.name} non e' leggibile: {exc}",
                "azione": "riscaricalo col pulsante, oppure aprilo e correggilo"}

    righe = contenuto.get("righe", [])
    return {"disponibile": bool(righe), "preso_il": contenuto.get("preso_il"),
            "calcolato_il": contenuto.get("calcolato_il"),
            "anni": contenuto.get("anni") or [],
            "righe": righe, "fonte": contenuto.get("fonte"),
            "pesi": spinoff_segnali.PESI,
            "motivo": None if righe else "l'elenco salvato e' vuoto",
            "azione": None if righe else "riprova ad aggiornarlo"}


def _salva(righe: list[dict], anni: list[int], preso_il: str | None = None,
           calcolato: bool = False) -> str:
    """Scrive il file in modo atomico e ritorna l'istante che ha appena segnato.

    Le due date vivono insieme e dicono cose diverse: `preso_il` e' quando e'
    stato scaricato l'elenco, `calcolato_il` quando sono stati misurati i
    segnali. Chi ricalcola non tocca la prima — l'elenco e' quello di prima — e
    chi riscarica azzera la seconda, perche' i segnali di ieri su un elenco di
    oggi sarebbero una misura appiccicata a righe che non l'hanno avuta.
    """
    adesso = datetime.now(UTC).isoformat(timespec="seconds")
    stato = {"versione": config.SPINOFF_FILE_VERSION,
             "preso_il": preso_il or adesso,
             "calcolato_il": adesso if calcolato else None,
             "anni": anni,
             "fonte": [config.SPINOFF_URL_MODELLO.format(anno=a) for a in anni],
             "righe": righe}

    config.SPINOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    provvisorio = config.SPINOFF_PATH.with_suffix(".json.tmp")
    provvisorio.write_text(json.dumps(stato, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    os.replace(provvisorio, config.SPINOFF_PATH)
    return adesso


def aggiorna() -> dict:
    """Scarica l'elenco e lo salva. Parte SOLO da qui, cioe' solo dal pulsante.

    Un anno che non risponde non fa fallire gli altri: si prende quello che c'e'
    e si dice cosa manca. Zero righe in tutto invece non si salvano — il file di
    prima resta dov'e', perche' sostituire un elenco buono con uno vuoto sarebbe
    perdere l'unica cosa che questo modulo non sa ricostruire.
    """
    anni = _anni_da_leggere()
    trovate: dict[str, dict] = {}
    falliti = []

    with registry.job(JOB_KIND, JOB_LABEL, total=len(anni)) as lavoro:
        for anno in anni:
            try:
                righe = analizza(_scarica(anno, lavoro.run_id))
            except SpinoffError as problema:
                falliti.append({"anno": anno, "motivo": str(problema)})
                lavoro.advance(detail=f"{anno}: non risponde")
                continue
            # Lo stesso simbolo su due pagine e' lo stesso spin-off: vince la
            # riga piu' recente, che e' quella dell'anno che stiamo leggendo.
            for riga in righe:
                trovate[riga["symbol"]] = riga
            lavoro.advance(detail=f"{anno}: {len(righe)} spin-off")

    ordinate = sorted(trovate.values(), key=lambda r: r["data"], reverse=True)
    if not ordinate:
        raise SpinoffError(
            "nessuna riga letta: la pagina potrebbe aver cambiato forma. "
            "L'elenco di prima non e' stato toccato"
            + (f" ({falliti[0]['motivo']})" if falliti else "")
        )

    preso_il = _salva(ordinate, anni)
    logger.info("[SPINOFF] elenco aggiornato: %d righe da %d pagine",
                len(ordinate), len(anni) - len(falliti))
    return {"righe": len(ordinate), "preso_il": preso_il, "anni": anni,
            "falliti": falliti, "primi": ordinate[:5]}


# --- il calcolo dei segnali, sul secondo pulsante ---------------------------

def _barre(frame) -> list[dict]:
    """Le sedute nella forma che vuole il dominio: data, chiusura, volume."""
    return [{"data": str(riga["report_date"])[:10],
             "chiusura": float(riga["close"]) if riga["close"] is not None else 0.0,
             "volume": float(riga["volume"] or 0)}
            for _, riga in frame.iterrows()
            if riga["close"] is not None]


def _conto_economico(frame) -> dict:
    """Le voci trimestrali del conto economico, come `{voce: {periodo: valore}}`."""
    return prospetti.tabella(frame, prospetti.CONTO_ECONOMICO, prospetti.TRIMESTRALE)["voci"]


def _misura(riga: dict, run_id: str | None) -> dict:
    """I segnali di un candidato, o il motivo per cui non se ne possono avere."""
    simbolo = riga["symbol"]
    prezzi = defeatbeta.prices(simbolo, run_id=run_id)
    if not prezzi.available:
        return {"disponibile": False, "motivo": f"prezzi: {prezzi.reason}"}

    barre = _barre(prezzi.frame)
    non_scambiato = spinoff_segnali.fermo(barre)
    if non_scambiato:
        return {"disponibile": False, "motivo": non_scambiato,
                "stato": spinoff_segnali.NON_SCAMBIATO}

    bilanci = defeatbeta.statements(simbolo, run_id=run_id)
    voci = _conto_economico(bilanci.frame) if bilanci.available else {}

    esito = spinoff_segnali.segnali(barre, voci, riga["data"])
    return {
        "disponibile": True,
        "segnali": esito,
        "punteggio": spinoff_segnali.punteggio(esito),
        "stato": spinoff_segnali.stato(esito),
        "mesi": round(spinoff_segnali.mesi_dallo_spin(riga["data"]), 1),
        "prezzo": barre[-1]["chiusura"],
        "prima_seduta": barre[0]["data"],
        # Il ticker aveva gia' una storia prima della separazione: non e' nuovo,
        # e su di lui il ragionamento «quotato da poco» non vale.
        "storia_precedente": spinoff_segnali.storia_precedente(barre[0]["data"], riga["data"]),
        "senza_bilanci": not bilanci.available,
    }


def _calcola(consegna: queue.Queue | None = None) -> dict:
    """Misura i segnali di tutti i candidati salvati. Sta dentro il registro."""
    salvato = elenco()
    righe = salvato["righe"]

    with registry.job(JOB_KIND_SEGNALI, JOB_LABEL_SEGNALI, total=len(righe)) as lavoro:
        if consegna is not None:
            consegna.put(lavoro.run_id)

        for riga in righe:
            try:
                riga["misura"] = _misura(riga, lavoro.run_id)
            except Exception as problema:
                # Un titolo che non si legge non ferma gli altri: si dichiara e
                # si va avanti. Sono decine di letture, e una che va male non
                # deve costare tutte quelle gia' fatte.
                logger.warning("[SPINOFF] %s non misurato: %s", riga["symbol"], problema)
                riga["misura"] = {"disponibile": False,
                                  "motivo": f"{type(problema).__name__}: {problema}"}
            lavoro.advance(detail=f"{riga['symbol']}: " + (
                f"{riga['misura']['punteggio']['presi']:.0f} punti"
                if riga["misura"]["disponibile"] else riga["misura"]["motivo"][:40]))

        calcolato_il = _salva(righe, salvato.get("anni") or [],
                              preso_il=salvato.get("preso_il"), calcolato=True)

    misurati = sum(1 for r in righe if r.get("misura", {}).get("disponibile"))
    logger.info("[SPINOFF] segnali calcolati su %d candidati di %d", misurati, len(righe))
    return {"calcolato_il": calcolato_il, "misurati": misurati, "totali": len(righe)}


def calcola_in_background() -> str:
    """Avvia il calcolo in un thread e ritorna il run_id con cui seguirlo o fermarlo.

    Come la costruzione dell'universo e come lo scanner: una richiesta HTTP che
    resta appesa per minuti e' un'altra forma di lavoro che non si puo' fermare.
    """
    # Il controllo sta QUI e non nel thread: un errore sollevato la' dentro non
    # tornerebbe a chi ha premuto, che resterebbe ad aspettare un run_id che non
    # arriva mai. Cio' che si puo' dire subito si dice subito.
    if not elenco()["righe"]:
        raise SpinoffError("non c'e' nessun elenco su cui calcolare: "
                           "premi prima «Aggiorna l'elenco»")

    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_calcola, args=(consegna,),
                     name="spinoff-segnali", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)
