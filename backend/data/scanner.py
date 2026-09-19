"""
scanner.py — cercare titoli che soddisfano dei criteri, sul passato.
# feat (Blocco 9): un lavoro lungo, quindi tracciato e fermabile.

Il vecchio tradash aveva scanner che nessuno vedeva partire e che non si
potevano fermare. Qui ogni scansione e' un lavoro del registro: si vede in
`/api/ops/active`, si ferma con Stop, e ogni titolo letto lascia la sua riga
nel log delle chiamate con la provenienza.

**Sul passato** vuol dire due cose diverse, e vanno tenute distinte:

* i prezzi si tagliano alla data chiesta — quello e' un fatto, la data di
  chiusura e' proprio la colonna che abbiamo;
* i FONDAMENTALI, se un giorno entreranno nei criteri, andranno tagliati sul
  DEPOSITO e non sulla fine periodo, con `domain/publication_dates.py`.
  Oggi i criteri guardano solo i prezzi, e questa nota esiste perche' il primo
  criterio fondamentale non nasca sbagliato.
"""
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import date

import config
from core import registry
from core.db import db_read
from data import defeatbeta, raffica, settori
from data import fondamentali as fondamentali_universo
from domain import publication_dates, scansione

logger = logging.getLogger(__name__)

JOB_KIND = "scanner"

# Ogni quanto la sentinella controlla se e' stato chiesto lo Stop.
INTERVALLO_CONTROLLO_STOP_S = 0.25

# Quanto si aspetta che il lavoro dichiari il proprio run_id.
ATTESA_AVVIO_S = 5.0

# Gli esiti di una scansione, tenuti in memoria: sono il risultato di UN lavoro,
# non un dato da conservare. Chi li vuole conservare li esporta.
_esiti: dict[str, dict] = {}
_lucchetto = threading.Lock()


def _candidati(filtri: dict) -> list[str]:
    """I simboli su cui scandagliare, presi dall'universo con i suoi filtri.

    Partire dall'universo e non dalla watchlist e' il senso di uno scanner: si
    cerca fra i titoli che NON stai gia' guardando.
    """
    condizioni, parametri = [], []
    if filtri.get("sector"):
        condizioni.append("sector = ?")
        parametri.append(filtri["sector"])
    if filtri.get("min_market_cap") is not None:
        condizioni.append("market_cap >= ?")
        parametri.append(float(filtri["min_market_cap"]))
    if filtri.get("min_volume") is not None:
        condizioni.append("avg_volume_30d >= ?")
        parametri.append(float(filtri["min_volume"]))

    dove = f"WHERE {' AND '.join(condizioni)}" if condizioni else ""
    limite = min(int(filtri.get("limite") or config.SCANNER_TITOLI_MAX),
                 config.SCANNER_TITOLI_MAX)

    with db_read() as conn:
        righe = conn.execute(
            f"SELECT symbol FROM universe {dove} ORDER BY market_cap DESC NULLS LAST LIMIT ?",
            [*parametri, limite],
        ).fetchall()
    return [r["symbol"] for r in righe]


def _chiusure(simbolo: str, fino_a: str | None, run_id: str) -> tuple[list, list]:
    """Prezzi e volumi di un titolo, tagliati alla data. Vuoti se non ce ne sono.

    Un simbolo rotto non ferma il giro (regola 4): torna vuoto, il chiamante lo
    conta fra quelli senza dati e va avanti. Solo un guasto del PROVIDER —
    `DefeatbetaUnavailable` — interrompe, perche' quello riguarda tutti.
    """
    lettura = defeatbeta.prices(simbolo, run_id=run_id)
    if not lettura.available:
        return [], []

    frame = lettura.frame
    if fino_a:
        frame = frame[frame["report_date"].astype(str) <= fino_a]

    return frame["close"].tolist(), frame["volume"].tolist()


def _fondamentali(simbolo: str, fino_a: str | None) -> dict:
    """Le misure di bilancio di un titolo, tagliate a cio' che era PUBBLICO.

    Si leggono dalla tabella dell'universo — una query per chiave, non una
    lettura da Defeatbeta — e il taglio usa le date di deposito vere dove ci
    sono. Dove non ci sono, `publication_dates` ricade sul ritardo prudente da
    solo: meglio non vedere un dato che c'era, che vederne uno che non c'era.

    Senza tabella derivata torna tutto vuoto, e i criteri di bilancio non
    passano: e' la stessa regola dei prezzi mancanti, non un caso speciale.
    """
    voci = fondamentali_universo.voci_di(simbolo)
    if not voci:
        return scansione.fondamentali({}, [])

    quando = fino_a or date.today().isoformat()
    depositi = fondamentali_universo.depositi_di(simbolo)
    periodi = sorted(voci.get("total_revenue", {}))
    pubblici = [p for p in periodi if publication_dates.was_public(depositi, p, quando)]
    return scansione.fondamentali(voci, pubblici)


def _mese_del_taglio(fino_a: str | None) -> str | None:
    """Il mese `AAAA-MM` a cui ancorare il paragone di settore.

    Con un taglio nel passato il paragone dev'essere di ALLORA: confrontare un
    prezzo del 2022 con la mediana di settore di oggi non misura la forza
    relativa, misura il tempo passato in mezzo. Senza taglio vale `None`, e il
    riferimento usa l'ultimo mese disponibile.
    """
    return fino_a[:7] if fino_a else None


@dataclass(frozen=True)
class Contesto:
    """Cio' che la scansione legge UNA volta, prima di guardare un titolo solo.

    Sono le misure che non stanno nei prezzi giornalieri del titolo: il
    paragone col settore, i depositi 8-K, il numero di azioni mese per mese.
    Stavano sciolti dentro al giro, e ogni indicatore nuovo ne aggiungeva uno:
    e' lo stesso percorso che aveva portato `_misura_mese` del rigioco a sette
    argomenti.

    **Il numero di azioni mancava del tutto.** Lo riempiva solo il rigioco, e
    qui nessuno: `azioni_variazione_massima` — il criterio piu' solido di tutto
    il progetto, 88-96% dei mesi vinti — dal vivo risultava non calcolabile
    per chiunque, e non passava mai. Chi lo metteva nello scanner otteneva zero
    risultati senza una parola, e il preset «Evita i guai», che lo contiene,
    non trovava niente.
    """
    settore: dict        # il riferimento di `settori.riferimenti()`
    depositi_8k: dict    # {simbolo: {mese: quanti 8-K}}
    mensili: dict        # {simbolo: {mese: {azioni, ...}}}
    mese: str | None     # il mese a cui si ancorano depositi e azioni


def _contesto(simboli: list[str], fino_a: str | None) -> Contesto:
    """Tutte le letture che non sono i prezzi del singolo titolo, in un punto solo.

    L'ancora e' il mese del taglio, oppure l'ultimo che lo storico mensile
    copre — non la data di oggi: se la derivazione e' vecchia di un mese,
    contare fino a oggi metterebbe un vuoto al posto di un mese che nessuno ha
    ancora letto. Il mese in corso e' parziale: la raffica esce semmai
    SOTTOSTIMATA, e per un filtro di esclusione e' il verso prudente.
    """
    taglio = _mese_del_taglio(fino_a)
    depositi_8k = raffica.per_mese(simboli)
    mensili = fondamentali_universo.mercato_mensile(simboli)
    ultimo = max((m for serie in (*depositi_8k.values(), *mensili.values())
                  for m in serie), default=None)
    return Contesto(settore=settori.riferimenti(taglio), depositi_8k=depositi_8k,
                    mensili=mensili, mese=taglio or ultimo)


def _misura_titolo(simbolo: str, chiusure: list, volumi: list,
                   contesto: Contesto, fino_a: str | None) -> dict:
    """Tutte le misure di un titolo: quelle dei suoi prezzi e quelle del contesto.

    Ogni criterio di `scansione.CRITERI` legge una casella di questo
    dizionario. Un test della suite le passa tutte e controlla che nessuna
    resti vuota: il difetto del numero di azioni non si vedeva da nessuna
    parte, perche' un criterio su una casella vuota non da' errore — non passa.
    """
    misurato = scansione.misure(chiusure, volumi)
    misurato["fondamentali"] = _fondamentali(simbolo, fino_a)

    # Azioni e depositi hanno la loro storia nelle tabelle mensili: senza un
    # mese a cui ancorarli non c'e' niente da confrontare, e valgono vuoti.
    if contesto.mese:
        misurato["azioni"] = scansione.azioni(
            contesto.mensili.get(simbolo, {}), contesto.mese)
        misurato["depositi"] = scansione.depositi(
            contesto.depositi_8k.get(simbolo, {}), contesto.mese)
    else:
        misurato["azioni"], misurato["depositi"] = None, {"raffica": None}

    # La forza relativa ha i suoi due capi nella serie giornaliera di TUTTI:
    # il perche' sta in `data/settori.py`, e in breve e' che il titolo e la
    # mediana del settore devono avere le stesse date.
    settore = contesto.settore
    misurato["settore"] = scansione.forza_settore(
        settore["variazioni"].get(simbolo),
        settore["riferimenti"].get(settore["settori"].get(simbolo)))
    return misurato


def _scandaglia(lavoro, simboli: list[str], criteri: dict, fino_a: str | None) -> dict:
    """Il giro vero e proprio: un titolo alla volta, fermabile a ogni passo.

    Il riferimento di settore si legge UNA volta prima del giro: e' una mediana
    per settore su tutti gli investibili, e non dipende da quali titoli si sta
    scandagliando. Calcolarla sui soli simboli scelti farebbe dire «ha battuto
    il suo settore» a chi ha solo battuto gli altri nove titoli che hai scelto
    tu, che e' un'altra frase.
    """
    trovati, senza_dati = [], []
    contesto = _contesto(simboli, fino_a)

    for simbolo in simboli:
        chiusure, volumi = _chiusure(simbolo, fino_a, lavoro.run_id)
        if not chiusure:
            senza_dati.append(simbolo)
        else:
            misurato = _misura_titolo(simbolo, chiusure, volumi, contesto, fino_a)
            soddisfa, perche = scansione.valuta(misurato, criteri)
            if soddisfa:
                trovati.append({"symbol": simbolo, "perche": perche,
                                "misure": _misure_leggibili(misurato)})

        # `advance` conta il passo E controlla lo Stop: sono la stessa cosa,
        # perche' un lavoro che avanza senza guardare non si ferma mai.
        lavoro.advance(detail=f"{simbolo}: {len(trovati)} trovati")

    return {
        "trovati": trovati,
        "senza_dati": senza_dati,
        "paragone_settore": {
            "base": contesto.settore["base"],
            "ancora": contesto.settore["ancora"],
            "settori": len(contesto.settore["riferimenti"]),
        },
    }


def _misure_leggibili(misurato: dict) -> dict:
    """Le misure da mostrare, arrotondate. Il resto resta nel calcolo."""
    return {
        "ultimo_prezzo": misurato["ultimo_prezzo"],
        "variazione_1a": misurato["variazione_1a"],
        "sedute": misurato["sedute"],
        "drawdown": misurato["drawdown"],
        "fondamentali": misurato["fondamentali"],
    }


def _esegui(criteri: dict, filtri: dict, fino_a: str | None = None,
            consegna: queue.Queue | None = None) -> dict:
    """Una scansione, dentro il registro dei lavori. Ritorna sempre un esito esplicito."""
    simboli = _candidati(filtri)
    etichetta = f"scansione su {len(simboli)} titoli" + (f" al {fino_a}" if fino_a else "")

    esito = {"run_id": None, "completata": False, "trovati": [], "senza_dati": [],
             "esaminati": 0, "totale": len(simboli), "fino_a": fino_a,
             "paragone_settore": None,
             "motivo": "fermata prima di completare"}

    with registry.job(JOB_KIND, etichetta, total=len(simboli)) as lavoro:
        esito["run_id"] = lavoro.run_id
        if consegna is not None:
            consegna.put(lavoro.run_id)

        risultato = _scandaglia(lavoro, simboli, criteri, fino_a)
        esito.update({"completata": True, "esaminati": lavoro.done,
                      "motivo": "completata", **risultato})

    # Anche una scansione fermata a meta' conserva quello che aveva trovato: e'
    # meno di quanto chiesto, non niente.
    esito["esaminati"] = esito["esaminati"] or 0
    with _lucchetto:
        _esiti[esito["run_id"]] = esito
    logger.info("[SCANNER] %s — %d trovati su %d esaminati",
                esito["motivo"], len(esito["trovati"]), esito["esaminati"])
    return esito


def avvia(criteri: dict, filtri: dict, fino_a: str | None = None) -> str:
    """Avvia una scansione in un thread e ritorna il run_id con cui fermarla."""
    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_esegui, args=(criteri, filtri, fino_a, consegna),
                     name="scanner", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def esito(run_id: str) -> dict | None:
    """Il risultato di una scansione, se e' finita. `None` se non se ne sa niente."""
    with _lucchetto:
        return _esiti.get(run_id)
