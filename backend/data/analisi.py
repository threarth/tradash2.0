"""
analisi.py — le sette analisi: quali ci sono, cosa serve loro, come girano.
# feat (Blocco 8): il registro dei metodi, e il primo che funziona davvero.

**Nessun loop di tool.** Nel vecchio tradash l'analisi girava come una
conversazione in cui il modello chiamava strumenti fino a decidere di aver
finito — e con tutto in un loop solo il contesto riaccodato a ogni tentativo
cresceva senza limite: una run e' rimasta "running" venti minuti senza una sola
risposta HTTP nuova prima che il watchdog la marcasse "hung".

Qui il conto e' rovesciato: **si calcola prima, si chiede dopo, una volta
sola.** Il modello riceve i numeri gia' pronti e puo' soltanto sintetizzarli.
La regola "non ricalcolare niente" del vecchio prompt diventa cosi' strutturale
invece che raccomandata: senza strumenti da chiamare, non ha modo di inventare
un numero.

**Un metodo che non ha la sua fonte primaria si FERMA, non degrada.** E' la
regola che il PIANO fissa per l'analisi qualitativa — senza le sezioni del
filing non produce un'analisi povera, non ne produce nessuna — e vale come
principio per tutti: meglio niente che un referto costruito sul vuoto.
"""
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import config
from core import llm, registry
from core.db import db_read, db_session
from core.tipi import python_puro
from data import defeatbeta
from domain import pannello, prospetti, scansione, segnali, trascrizione

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

JOB_KIND = "analisi"

# Quanti prezzi servono perche' una lettura tecnica abbia senso. Sotto, le medie
# lunghe non esistono e la lettura sarebbe costruita su niente.
SEDUTE_MINIME_TECNICA = 60

# I sette metodi. Quelli non ancora costruiti restano QUI, con scritto cosa
# serve loro: toglierli dall'elenco li farebbe sparire, e un'analisi che manca
# senza dirlo e' indistinguibile da un'analisi che non serve.
METODI = {
    "tecnica": {
        "nome": "Lettura tecnica",
        "natura": "deterministica + sintesi del modello",
        "pronta": True,
        "fonte": "i prezzi, gia' letti da Defeatbeta",
    },
    "fondamentale": {
        "nome": "Qualita' fondamentale",
        "natura": "deterministica + sintesi del modello",
        "pronta": True,
        "fonte": "i cinque segnali F1-F5 e le metriche di Defeatbeta, "
                 "col confronto di settore",
    },
    "qualitativa": {
        "nome": "Report qualitativo a 10 sezioni",
        "natura": "quattro fasi separate del modello",
        "pronta": False,
        "fonte": "il TESTO dei documenti SEC, che scarichi tu e salvi in data/filings",
        "manca": "le quattro fasi. I documenti pero' si possono gia' preparare: "
                 "la scheda del titolo dice quali servono e con che nome salvarli",
    },
    "forward": {
        "nome": "Forward analysis",
        "natura": "pipeline deterministica, non conversazione",
        "pronta": False,
        "fonte": "proiezioni e DCF sui bilanci",
        "manca": "il pacchetto forward_analysis, 3.295 righe MAI girate nel vecchio sistema",
    },
    "earnings": {
        "nome": "Earnings review",
        "natura": "modello sulle trascrizioni",
        "pronta": True,
        "fonte": "le trascrizioni delle earnings call, divise in parte preparata "
                 "e domande degli analisti",
    },
    "spin_off": {
        "nome": "Analisi spin-off",
        "natura": "modello",
        "pronta": False,
        "fonte": "documenti societari",
        "manca": "tutto: zero referti storici, e' il candidato a essere tolto",
    },
    "verdetto": {
        "nome": "Verdetto finale",
        "natura": "sintesi trasversale",
        "pronta": False,
        "fonte": "i referti degli altri metodi",
        "manca": "gli altri metodi",
    },
}


class AnalisiError(ValueError):
    """Un metodo non si puo' eseguire: manca la fonte, o il metodo non esiste."""


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def elenco() -> list[dict]:
    """I sette metodi, con lo stato di ciascuno. Anche quelli che non ci sono."""
    return [{"metodo": chiave, **dati} for chiave, dati in METODI.items()]


# --- la lettura tecnica -----------------------------------------------------

def _misure_tecniche(simbolo: str, run_id: str | None) -> dict:
    """Tutto quello che si sa del titolo guardando i prezzi. Gia' calcolato.

    Se la storia non basta, questa funzione SOLLEVA invece di ritornare misure
    a meta': un referto costruito su venti sedute costa quanto uno costruito su
    seimila e vale molto meno.
    """
    lettura = defeatbeta.prices(simbolo, run_id=run_id)
    if not lettura.available:
        raise AnalisiError(f"nessun prezzo per {simbolo}: {lettura.reason}")

    chiusure = lettura.frame["close"].tolist()
    if len(chiusure) < SEDUTE_MINIME_TECNICA:
        raise AnalisiError(
            f"{simbolo} ha {len(chiusure)} sedute, ne servono almeno "
            f"{SEDUTE_MINIME_TECNICA}: la lettura si ferma invece di degradare"
        )

    misurato = scansione.misure(chiusure, lettura.frame["volume"].tolist())
    ultimo = lettura.frame["report_date"].astype(str).tolist()[-1]
    return {**misurato, "ultima_seduta": ultimo}


def _contesto(simbolo: str, run_id: str | None) -> str:
    """Chi e' questo titolo, in due righe. Serve al modello per inquadrare."""
    profilo = defeatbeta.profile(simbolo, run_id=run_id)
    if not profilo.available:
        return f"{simbolo} — nessun profilo disponibile: {profilo.reason}"

    riga = profilo.frame.iloc[0]
    return (f"{simbolo} — settore {riga.get('sector')}, industria "
            f"{riga.get('industry')}, paese {riga.get('country')}")


def _prompt(nome: str, **pezzi) -> str:
    """Compone un prompt dal suo file. I segnaposti si sostituiscono a mano,
    perche' il testo contiene graffe di esempio JSON che `format` interpreterebbe."""
    testo = (PROMPT_DIR / f"{nome}.txt").read_text(encoding="utf-8")
    for chiave, valore in pezzi.items():
        testo = testo.replace(f"{{{chiave}}}", valore)
    return testo


def _leggi_json(testo: str) -> dict:
    """Il JSON dentro la risposta del modello, o un errore che lo dice.

    Un modello puo' incorniciare il JSON in un blocco di codice: si cerca fra
    la prima graffa e l'ultima invece di pretendere una risposta pulita.
    """
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio < 0 or fine <= inizio:
        raise AnalisiError("il modello non ha risposto con un JSON")
    try:
        return json.loads(testo[inizio:fine + 1])
    except json.JSONDecodeError as exc:
        raise AnalisiError(f"il JSON del modello non e' leggibile: {exc}") from exc


def _tecnica(simbolo: str, run_id: str | None) -> dict:
    """Calcola, chiede, e ritorna il referto col suo costo."""
    misure = _misure_tecniche(simbolo, run_id)
    sistema = _prompt("analisi_tecnica",
                      contesto=_contesto(simbolo, run_id),
                      misure=json.dumps(misure, indent=2, ensure_ascii=False))

    risposta = llm.chiedi(fase="analisi_tecnica", sistema=sistema,
                          messaggio=f"Produci la lettura tecnica di {simbolo}.",
                          scope=simbolo, run_id=run_id)

    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**_leggi_json(risposta["testo"]), "misure": misure},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}


# --- l'analisi fondamentale -------------------------------------------------

# Le metriche del pannello, e la loro gemella di settore dove esiste. Il
# confronto vale quanto il numero: "ROE del 15%" non si legge da solo.
PANNELLO_FONDAMENTALE = {
    "roe": "industry_roe",
    "roic": "industry_roic",
    "quarterly_gross_margin": "industry_quarterly_gross_margin",
    "quarterly_net_margin": "industry_quarterly_net_margin",
    "quarterly_operating_margin": None,
    "quarterly_revenue_yoy_growth": None,
    "net_debt_ttm": None,
    "debt_to_equity": None,
    "ttm_pe": None,
}


def _metrica_compressa(simbolo: str, nome: str, run_id: str | None) -> dict | None:
    """Una metrica ridotta ai tre numeri che si leggono. `None` se non c'e'.

    Una metrica che manca non ferma il pannello: le altre otto continuano a
    dire quello che sanno, e la sua assenza finisce fra i dati mancanti.
    """
    try:
        lettura = defeatbeta.metrica(simbolo, nome, run_id=run_id)
    except defeatbeta.DefeatbetaUnavailable:
        logger.warning("[ANALISI] metrica %s non disponibile per %s", nome, simbolo)
        return None

    if not lettura.available:
        return None

    colonne = [c for c in lettura.frame.columns if c != "symbol"]
    righe = [{c: python_puro(r[c]) for c in colonne} for _, r in lettura.frame.iterrows()]
    return pannello.comprimi(righe, colonne)


def _pannello(simbolo: str, run_id: str | None) -> tuple[dict, list[str]]:
    """Tutte le metriche del pannello, col settore accanto. E cosa non c'era."""
    misure, mancanti = {}, []

    for nome, gemella in PANNELLO_FONDAMENTALE.items():
        titolo = _metrica_compressa(simbolo, nome, run_id)
        if titolo is None:
            mancanti.append(nome)
            continue
        settore = _metrica_compressa(simbolo, gemella, run_id) if gemella else None
        misure[nome] = pannello.confronta(titolo, settore)

    return misure, mancanti


def _segnali_fondamentali(simbolo: str, run_id: str | None) -> dict:
    """I cinque segnali di rischio, dagli stessi bilanci della scheda."""
    lettura = defeatbeta.statements(simbolo, run_id=run_id)
    if not lettura.available:
        raise AnalisiError(f"nessun bilancio per {simbolo}: {lettura.reason}")

    tabelle = {
        nome: prospetti.tabella(lettura.frame, nome, prospetti.TRIMESTRALE)
        for nome in prospetti.PROSPETTI
    }
    return segnali.tutti(tabelle)


def _fondamentale(simbolo: str, run_id: str | None) -> dict:
    """Calcola il pannello e i segnali, poi chiede al modello di leggerli.

    Si ferma invece di degradare se non c'e' nemmeno una metrica: una lettura
    fondamentale senza numeri non e' una lettura povera, e' una lettura
    inventata.
    """
    rischi = _segnali_fondamentali(simbolo, run_id)
    misure, mancanti = _pannello(simbolo, run_id)

    if not misure:
        raise AnalisiError(
            f"nessuna metrica disponibile per {simbolo}: l'analisi si ferma "
            f"invece di degradare"
        )

    sistema = _prompt("analisi_fondamentale",
                      contesto=_contesto(simbolo, run_id),
                      segnali=json.dumps(rischi, indent=2, ensure_ascii=False),
                      metriche=json.dumps(misure, indent=2, ensure_ascii=False))

    risposta = llm.chiedi(fase="analisi_fondamentale", sistema=sistema,
                          messaggio=f"Produci la lettura fondamentale di {simbolo}.",
                          scope=simbolo, run_id=run_id)

    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**_leggi_json(risposta["testo"]),
                          "segnali": rischi, "metriche": misure,
                          "metriche_mancanti": mancanti},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}


# --- l'earnings review, sulle trascrizioni ---------------------------------

def _tronca(testo: str) -> tuple[str, bool]:
    """Un testo tagliato alla lunghezza utile, e se e' stato tagliato.

    Il secondo valore non e' un dettaglio: un testo troncato mostrato senza
    dirlo si legge come se quella fosse tutta la risposta.
    """
    limite = config.TRASCRIZIONE_RISPOSTA_CARATTERI
    if len(testo) <= limite:
        return testo, False
    return testo[:limite] + " […]", True


def _call_leggibile(struttura: dict, con_risposte: bool) -> dict:
    """Una call ridotta a cio' che serve leggere, dichiarando cosa e' stato tagliato."""
    troncati = 0
    scambi = []

    for scambio in struttura["scambi"]:
        domanda, tagliata = _tronca(scambio["domanda"])
        troncati += int(tagliata)
        voce = {"analista": scambio["analista"], "domanda": domanda}

        if con_risposte:
            risposte = []
            for risposta in scambio["risposte"]:
                testo, tagliata = _tronca(risposta["testo"])
                troncati += int(tagliata)
                risposte.append({"chi": risposta["chi"], "testo": testo})
            voce["risposte"] = risposte

        scambi.append(voce)

    return {"preparata": struttura["preparata"] if con_risposte else [],
            "scambi": scambi, "management": struttura["management"],
            "testi_troncati": troncati}


def _earnings(simbolo: str, run_id: str | None) -> dict:
    """Legge le ultime due call: l'ultima per intero, la precedente per le domande.

    Due e non una perche' la domanda che conta e' "cosa e' cambiato": le
    preoccupazioni degli analisti si spostano, e vederle spostarsi dice piu' di
    una fotografia sola.
    """
    lettura = defeatbeta.transcripts(simbolo, run_id=run_id)
    if not lettura.available:
        raise AnalisiError(
            f"nessuna trascrizione per {simbolo}: {lettura.reason}. "
            f"Defeatbeta ne ha per 6.495 simboli, non per tutti"
        )

    righe = list(lettura.frame.iterrows())
    ultima = trascrizione.struttura(righe[0][1]["transcripts"])
    if not ultima["preparata"] and not ultima["scambi"]:
        raise AnalisiError("la trascrizione e' vuota: l'analisi si ferma "
                           "invece di degradare")

    call = {"periodo": f"{righe[0][1]['fiscal_year']} "
                       f"Q{python_puro(righe[0][1]['fiscal_quarter'])}",
            "data": python_puro(righe[0][1]["report_date"]),
            **_call_leggibile(ultima, con_risposte=True)}

    precedente = None
    if len(righe) > 1:
        prima = trascrizione.struttura(righe[1][1]["transcripts"])
        precedente = {"periodo": f"{righe[1][1]['fiscal_year']} "
                                 f"Q{python_puro(righe[1][1]['fiscal_quarter'])}",
                      **_call_leggibile(prima, con_risposte=False)}

    prima_json = (json.dumps(precedente, indent=2, ensure_ascii=False)
                  if precedente else "non disponibile")
    messaggio = (
        f"Titolo: {_contesto(simbolo, run_id)}\n\n"
        f"## La call piu' recente\n"
        f"{json.dumps(call, indent=2, ensure_ascii=False)}\n\n"
        f"## Le domande della call precedente\n{prima_json}"
    )
    sistema = _prompt("analisi_earnings")

    risposta = llm.chiedi(fase="analisi_earnings", sistema=sistema, messaggio=messaggio,
                          scope=simbolo, run_id=run_id)
    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**_leggi_json(risposta["testo"]),
                          "call": call["periodo"],
                          "call_precedente": precedente["periodo"] if precedente else None,
                          "testi_troncati": call["testi_troncati"],
                          "caratteri_originali": ultima["caratteri"]},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}


ESECUTORI = {"tecnica": _tecnica, "fondamentale": _fondamentale,
             "earnings": _earnings}


# --- eseguire e conservare --------------------------------------------------

def _salva(simbolo: str, metodo: str, referto: dict, run_id: str) -> int:
    """Conserva il referto. Il contenuto e' un documento annidato, e SQLite regge."""
    with db_session() as conn:
        cursore = conn.execute(
            """INSERT INTO referti (symbol, metodo, as_of, contenuto, modello,
                                    costo_usd, run_id, creato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (simbolo, metodo, None,
             json.dumps(referto["contenuto"], ensure_ascii=False),
             referto.get("modello"), referto.get("costo_usd", 0.0), run_id, _adesso()),
        )
        return cursore.lastrowid


def esegui(metodo: str, simbolo: str) -> dict:
    """Esegue un'analisi dentro il registro dei lavori, e ne conserva il referto."""
    definizione = METODI.get(metodo)
    if definizione is None:
        raise AnalisiError(f"metodo sconosciuto: {metodo!r}. "
                           f"Ci sono: {', '.join(METODI)}")
    if not definizione["pronta"]:
        raise AnalisiError(
            f"{definizione['nome']} non e' ancora costruita. Le manca: "
            f"{definizione['manca']}"
        )

    ambito = simbolo.strip().upper()
    esito = {"metodo": metodo, "symbol": ambito, "run_id": None, "referto_id": None,
             "costo_usd": 0.0, "motivo": "fermata prima di completare"}

    with registry.job(JOB_KIND, f"{definizione['nome']} su {ambito}", total=1) as lavoro:
        esito["run_id"] = lavoro.run_id
        referto = ESECUTORI[metodo](ambito, lavoro.run_id)
        esito["referto_id"] = _salva(ambito, metodo, referto, lavoro.run_id)
        esito.update({"costo_usd": referto.get("costo_usd", 0.0),
                      "contenuto": referto["contenuto"], "motivo": "completata"})
        lavoro.advance(detail=f"referto {esito['referto_id']}, "
                              f"${esito['costo_usd']:.4f}")

    return esito


def referti(simbolo: str | None = None, metodo: str | None = None,
            limite: int = 20) -> list[dict]:
    """I referti prodotti, dal piu' recente."""
    condizioni, parametri = [], []
    if simbolo:
        condizioni.append("symbol = ?")
        parametri.append(simbolo.strip().upper())
    if metodo:
        condizioni.append("metodo = ?")
        parametri.append(metodo)

    dove = f"WHERE {' AND '.join(condizioni)}" if condizioni else ""
    with db_read() as conn:
        righe = conn.execute(
            f"SELECT * FROM referti {dove} ORDER BY creato_il DESC LIMIT ?",
            [*parametri, min(limite, config.CALLS_PAGE_LIMIT_MAX)],
        ).fetchall()

    return [{**dict(r), "contenuto": json.loads(r["contenuto"])} for r in righe]
