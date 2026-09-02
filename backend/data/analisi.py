"""
analisi.py — le sette analisi: quali ci sono, cosa serve loro, come girano.
# feat (Blocco 8): il registro dei metodi, e il primo che funziona davvero.

**Nessun loop di tool.** Nel vecchio tradash l'analisi girava come una
conversazione in cui il modello chiamava strumenti fino a decidere di aver
finito — e con tutto in un loop solo il contesto riaccodato a ogni tentativo
cresceva senza limite: una run e' rimasta "running" venti minuti senza una sola
risposta HTTP nuova prima che il watchdog la marcasse "hung".

Qui il conto e' rovesciato: **si calcola prima, si chiede dopo.** Il modello
riceve i numeri gia' pronti e puo' soltanto sintetizzarli. La regola "non
ricalcolare niente" del vecchio prompt diventa cosi' strutturale invece che
raccomandata: senza strumenti da chiamare, non ha modo di inventare un numero.

Un metodo puo' chiedere piu' di una volta — il report qualitativo lo fa quattro
volte, una per fase — ma ogni domanda e' secca e il suo materiale e' gia'
raccolto: il contesto non cresce fra una e l'altra. Chi chiede piu' volte
dichiara i suoi `passi`, e avanza il lavoro a ogni fase, cosi' lo Stop trova
dove agire.

**Un metodo che non ha la sua fonte primaria si FERMA, non degrada.** E' la
regola che il PIANO fissa per l'analisi qualitativa — senza le sezioni del
filing non produce un'analisi povera, non ne produce nessuna — e vale come
principio per tutti: meglio niente che un referto costruito sul vuoto.
"""
import json
import logging
from datetime import UTC, datetime

import config
from core import llm, registry
from core.db import db_read, db_session
from core.tipi import python_puro
from data import defeatbeta, forward, qualitativa, verdetto
from data.materiale import (
    AnalisiError,
    contesto,
    impronta_prompt,
    leggi_json,
    pannello_metriche,
    prompt,
    segnali_fondamentali,
)
from domain import scansione, spinoff, trascrizione

logger = logging.getLogger(__name__)

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
        "pronta": True,
        "passi": 4,
        "fonte": "il TESTO dei documenti SEC, che scarichi tu e salvi in data/filings. "
                 "Senza l'ultimo 10-K non parte: la scheda del titolo dice quale "
                 "serve e con che nome salvarlo",
    },
    "forward": {
        "nome": "Forward analysis",
        "natura": "DCF deterministico + lettura delle ipotesi",
        "pronta": True,
        "fonte": "il DCF di Defeatbeta — WACC col CAPM, crescita dagli utili, tasso "
                 "terminale dal Tesoro a 5 anni — rifatto in proprio per poterlo "
                 "rifare con altre ipotesi. NON e' il pacchetto forward_analysis del "
                 "vecchio sistema: quelle 3.295 righe non sono mai girate",
    },
    "earnings": {
        "nome": "Earnings review",
        "natura": "modello sulle trascrizioni",
        "pronta": True,
        "fonte": "le trascrizioni delle earnings call, divise in parte preparata "
                 "e domande degli analisti",
    },
    "spin_off": {
        "nome": "Rilevatore di spin-off",
        "natura": "rilevatore di menzioni + lettura del modello",
        "pronta": True,
        "fonte": "le notizie che ne parlano e le earnings call, da Defeatbeta. "
                 "NON e' un calendario: le fonti che lo erano — stockanalysis.com "
                 "e la ricerca su EDGAR — sono fuori dal perimetro",
    },
    "verdetto": {
        "nome": "Verdetto finale",
        "natura": "sintesi trasversale, non un punteggio",
        "pronta": True,
        "fonte": "i referti degli altri metodi, l'ultimo per ciascuno, ognuno con "
                 "la sua eta'. Ne servono almeno due di metodi diversi: con uno "
                 "solo la sintesi sarebbe una parafrasi",
    },
}


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


def _tecnica(simbolo: str, lavoro) -> dict:
    """Calcola, chiede, e ritorna il referto col suo costo."""
    run_id = lavoro.run_id
    misure = _misure_tecniche(simbolo, run_id)
    sistema = prompt("analisi_tecnica",
                     contesto=contesto(simbolo, run_id),
                     misure=json.dumps(misure, indent=2, ensure_ascii=False))

    risposta = llm.chiedi(fase="analisi_tecnica", sistema=sistema,
                          messaggio=f"Produci la lettura tecnica di {simbolo}.",
                          scope=simbolo, run_id=run_id)

    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**leggi_json(risposta["testo"]), "misure": misure,
                          "prompt": impronta_prompt("analisi_tecnica")},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}


# --- l'analisi fondamentale -------------------------------------------------

def _fondamentale(simbolo: str, lavoro) -> dict:
    """Calcola il pannello e i segnali, poi chiede al modello di leggerli.

    Si ferma invece di degradare se non c'e' nemmeno una metrica: una lettura
    fondamentale senza numeri non e' una lettura povera, e' una lettura
    inventata.
    """
    run_id = lavoro.run_id
    rischi = segnali_fondamentali(simbolo, run_id)
    misure, mancanti = pannello_metriche(simbolo, run_id)

    if not misure:
        raise AnalisiError(
            f"nessuna metrica disponibile per {simbolo}: l'analisi si ferma "
            f"invece di degradare"
        )

    sistema = prompt("analisi_fondamentale",
                     contesto=contesto(simbolo, run_id),
                     segnali=json.dumps(rischi, indent=2, ensure_ascii=False),
                     metriche=json.dumps(misure, indent=2, ensure_ascii=False))

    risposta = llm.chiedi(fase="analisi_fondamentale", sistema=sistema,
                          messaggio=f"Produci la lettura fondamentale di {simbolo}.",
                          scope=simbolo, run_id=run_id)

    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**leggi_json(risposta["testo"]),
                          "segnali": rischi, "metriche": misure,
                          "metriche_mancanti": mancanti,
                          "prompt": impronta_prompt("analisi_fondamentale")},
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


def _earnings(simbolo: str, lavoro) -> dict:
    """Legge le ultime due call: l'ultima per intero, la precedente per le domande.

    Due e non una perche' la domanda che conta e' "cosa e' cambiato": le
    preoccupazioni degli analisti si spostano, e vederle spostarsi dice piu' di
    una fotografia sola.
    """
    run_id = lavoro.run_id
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
        f"Titolo: {contesto(simbolo, run_id)}\n\n"
        f"## La call piu' recente\n"
        f"{json.dumps(call, indent=2, ensure_ascii=False)}\n\n"
        f"## Le domande della call precedente\n{prima_json}"
    )
    sistema = prompt("analisi_earnings")

    risposta = llm.chiedi(fase="analisi_earnings", sistema=sistema, messaggio=messaggio,
                          scope=simbolo, run_id=run_id)
    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**leggi_json(risposta["testo"]),
                          "call": call["periodo"],
                          "call_precedente": precedente["periodo"] if precedente else None,
                          "testi_troncati": call["testi_troncati"],
                          "caratteri_originali": ultima["caratteri"],
                          "prompt": impronta_prompt("analisi_earnings")},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}


# --- il rilevatore di spin-off ---------------------------------------------

# Quante notizie si scorrono cercando le menzioni. Il filtro e' gia' sul titolo:
# questo e' il tetto di quante ne tornano.
NOTIZIE_SPINOFF = 30


def _nome_societa(simbolo: str) -> str | None:
    """Il nome della societa', dall'universo che lo ha gia' derivato."""
    with db_read() as conn:
        riga = conn.execute("SELECT name FROM universe WHERE symbol = ?",
                            (simbolo.strip().upper(),)).fetchone()
    return riga["name"] if riga else None


def _menzioni_notizie(simbolo: str, run_id: str | None) -> list[dict]:
    """Le menzioni di spin-off DI QUESTA societa'. Elenco vuoto se non ce ne sono."""
    trovate: list[dict] = []
    viste: set[str] = set()
    nome = _nome_societa(simbolo)

    for parola in spinoff.PAROLE:
        lettura = defeatbeta.news_che_nominano(simbolo, parola, limit=NOTIZIE_SPINOFF,
                                               run_id=run_id)
        if not lettura.available:
            continue
        righe = [{c: r[c] for c in lettura.frame.columns} for _, r in lettura.frame.iterrows()]
        for menzione in spinoff.menzioni_nelle_notizie(righe, simbolo, nome):
            # Le tre parole trovano spesso gli stessi articoli: si tiene il
            # titolo una volta sola.
            if menzione["titolo"] not in viste:
                viste.add(menzione["titolo"])
                trovate.append(menzione)

    return sorted(trovate, key=lambda m: m["quando"], reverse=True)


def _menzioni_call(simbolo: str, run_id: str | None) -> list[dict]:
    """Dove, nelle ultime call, si parla di spin-off."""
    try:
        lettura = defeatbeta.transcripts(simbolo, run_id=run_id)
    except defeatbeta.DefeatbetaUnavailable:
        return []
    if not lettura.available:
        return []

    trovate = []
    for _, riga in lettura.frame.iterrows():
        struttura = trascrizione.struttura(riga["transcripts"])
        for menzione in spinoff.menzioni_nella_call(struttura):
            trovate.append({"call": f"{riga['fiscal_year']} "
                                    f"Q{python_puro(riga['fiscal_quarter'])}", **menzione})
    return trovate


def _spin_off(simbolo: str, lavoro) -> dict:
    """Cerca le menzioni, poi le fa leggere. Se non ce ne sono, non chiede niente.

    Non chiamare il modello quando non c'e' niente da leggere non e' solo
    risparmio: un modello a cui si chiede di analizzare il vuoto produce
    comunque una risposta, e quella risposta sembra un'analisi.
    """
    run_id = lavoro.run_id
    notizie = _menzioni_notizie(simbolo, run_id)
    call = _menzioni_call(simbolo, run_id)

    if not notizie and not call:
        return {"contenuto": {
            "c_e_uno_spinoff": "no",
            "lettura": f"Nessuna menzione di spin-off per {simbolo} nelle notizie "
                       f"di Defeatbeta ne' nelle ultime earnings call.",
            "menzioni_trovate": 0,
            "dati_mancanti": ["il sistema legge le menzioni, non un calendario di "
                              "spin-off: un'operazione di cui non si e' ancora "
                              "parlato non risulterebbe"],
            "confidenza": "bassa",
        }, "modello": None, "costo_usd": 0.0}

    sistema = prompt("analisi_spinoff")
    messaggio = (
        f"Titolo: {contesto(simbolo, run_id)}\n\n"
        f"## Menzioni nelle notizie ({len(notizie)})\n"
        f"{json.dumps(notizie, indent=2, ensure_ascii=False)}\n\n"
        f"## Menzioni nelle earnings call ({len(call)})\n"
        f"{json.dumps(call, indent=2, ensure_ascii=False) if call else 'nessuna'}"
    )

    risposta = llm.chiedi(fase="analisi_spinoff", sistema=sistema, messaggio=messaggio,
                          scope=simbolo, run_id=run_id)
    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**leggi_json(risposta["testo"]),
                          "prompt": impronta_prompt("analisi_spinoff"),
                          "menzioni_trovate": len(notizie) + len(call),
                          "menzioni_notizie": notizie,
                          "menzioni_call": call},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}


def _verdetto(simbolo: str, lavoro) -> dict:
    """Il verdetto legge i referti degli altri, e il registro glieli passa.

    Passarglieli invece di lasciare che se li prenda tiene fuori l'anello: il
    verdetto e' un metodo del registro, e un metodo che importa il registro che
    lo importa e' un import che funziona finche' nessuno cambia l'ordine.
    """
    return verdetto.esegui(simbolo, lavoro,
                           referti(simbolo, limite=config.CALLS_PAGE_LIMIT_MAX),
                           METODI)


ESECUTORI = {"tecnica": _tecnica, "fondamentale": _fondamentale,
             "earnings": _earnings, "spin_off": _spin_off,
             "qualitativa": qualitativa.esegui, "forward": forward.esegui,
             "verdetto": _verdetto}

# Quanti passi ha un metodo, quando non lo dichiara: uno. Serve alla barra di
# avanzamento e allo Stop — un metodo che dura quattro chiamate al modello deve
# potersi fermare fra l'una e l'altra, non solo alla fine.
PASSI_PREDEFINITI = 1


# --- eseguire e conservare --------------------------------------------------

def _identita(simbolo: str, metodo: str, quando: str, lavoro: str | None) -> tuple:
    """Cosa distingue un referto da un altro: il lavoro che l'ha prodotto.

    L'istante da solo non basta — ha la precisione del secondo — e simbolo e
    metodo si ripetono per costruzione.
    """
    return (simbolo, metodo, quando, lavoro)


def _sul_file(riga: dict) -> None:
    """Scrive il referto nel file che ne e' la verita'. Append-only.

    Il database e' una vista ricostruibile — tranne che per i referti, che sono
    stati PAGATI e che nessuna fonte sa riprodurre. Qui vale la stessa regola
    della watchlist: la verita' e' un file, SQLite ne tiene una copia di lavoro.

    Se la scrittura fallisce l'analisi NON fallisce: il referto e' gia' stato
    prodotto e pagato, e perderlo per un errore di disco sarebbe il doppio del
    danno. Ma l'errore si vede nel log, perche' vuol dire che la copia di
    sicurezza non c'e'.
    """
    try:
        config.REFERTI_PATH.parent.mkdir(parents=True, exist_ok=True)
        with config.REFERTI_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(riga, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("[ANALISI] referto NON scritto su file: resta solo in SQLite")


def _salva(simbolo: str, metodo: str, referto: dict, run_id: str) -> int:
    """Conserva il referto: prima sul file che e' la verita', poi in SQLite."""
    riga = {"symbol": simbolo, "metodo": metodo, "as_of": None,
            "contenuto": referto["contenuto"], "modello": referto.get("modello"),
            "costo_usd": referto.get("costo_usd", 0.0), "run_id": run_id,
            "creato_il": _adesso()}
    _sul_file(riga)

    with db_session() as conn:
        cursore = conn.execute(
            """INSERT INTO referti (symbol, metodo, as_of, contenuto, modello,
                                    costo_usd, run_id, creato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (riga["symbol"], riga["metodo"], riga["as_of"],
             json.dumps(riga["contenuto"], ensure_ascii=False),
             riga["modello"], riga["costo_usd"], riga["run_id"], riga["creato_il"]),
        )
        return cursore.lastrowid


def ripristina_dal_file() -> dict:
    """Rimette in SQLite i referti che stanno nel file. Si usa dopo un rebuild.

    Salta quelli gia' presenti. L'identita' e' il **lavoro** che li ha prodotti,
    non l'istante: `creato_il` ha la precisione del secondo, e due analisi
    finite nello stesso secondo si sarebbero fuse in una — successo alla prima
    prova, con due referti su due che diventavano uno.

    Il lavoro d'origine viene conservato dentro il contenuto quando la sua riga
    in `jobs` non c'e' piu': la colonna deve diventare NULL per via della chiave
    esterna, ma l'identita' del referto non deve perdersi con lei, o al secondo
    ripristino si duplicherebbe.
    """
    if not config.REFERTI_PATH.is_file():
        return {"letti": 0, "rimessi": 0, "gia_presenti": 0, "illeggibili": 0,
                "reason": f"nessun file in {config.REFERTI_PATH}"}

    letti = rimessi = illeggibili = orfani = 0
    with db_read() as conn:
        esistenti = set()
        for r in conn.execute("SELECT symbol, metodo, creato_il, run_id, contenuto "
                              "FROM referti"):
            contenuto = json.loads(r["contenuto"])
            esistenti.add(_identita(r["symbol"], r["metodo"], r["creato_il"],
                                    r["run_id"] or contenuto.get("run_id_originale")))
        # Dopo un rebuild la tabella dei lavori e' VUOTA, e `run_id` e' una
        # chiave esterna: rimettere un referto col suo lavoro d'origine farebbe
        # fallire l'inserimento. Il lavoro e' ricostruibile, il referto no —
        # quindi si perde il collegamento, non il referto, e si dice quanti.
        lavori = {r["run_id"] for r in conn.execute("SELECT run_id FROM jobs")}

    with db_session() as conn:
        for riga_grezza in config.REFERTI_PATH.read_text(encoding="utf-8").splitlines():
            if not riga_grezza.strip():
                continue
            letti += 1
            try:
                riga = json.loads(riga_grezza)
            except json.JSONDecodeError:
                illeggibili += 1
                logger.warning("[ANALISI] riga di referto illeggibile, saltata")
                continue
            chiave = _identita(riga["symbol"], riga["metodo"], riga["creato_il"],
                               riga.get("run_id"))
            if chiave in esistenti:
                continue

            lavoro = riga.get("run_id")
            contenuto = riga["contenuto"]
            if lavoro is not None and lavoro not in lavori:
                contenuto = {**contenuto, "run_id_originale": lavoro}
                lavoro = None
                orfani += 1

            conn.execute(
                """INSERT INTO referti (symbol, metodo, as_of, contenuto, modello,
                                        costo_usd, run_id, creato_il)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (riga["symbol"], riga["metodo"], riga.get("as_of"),
                 json.dumps(contenuto, ensure_ascii=False),
                 riga.get("modello"), riga.get("costo_usd", 0.0),
                 lavoro, riga["creato_il"]),
            )
            esistenti.add(chiave)
            rimessi += 1

    return {"letti": letti, "rimessi": rimessi,
            "gia_presenti": letti - rimessi - illeggibili,
            "illeggibili": illeggibili, "senza_lavoro": orfani, "reason": None}


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

    passi = definizione.get("passi", PASSI_PREDEFINITI)
    with registry.job(JOB_KIND, f"{definizione['nome']} su {ambito}", total=passi) as lavoro:
        esito["run_id"] = lavoro.run_id
        referto = ESECUTORI[metodo](ambito, lavoro)
        esito["referto_id"] = _salva(ambito, metodo, referto, lavoro.run_id)
        esito.update({"costo_usd": referto.get("costo_usd", 0.0),
                      "contenuto": referto["contenuto"], "motivo": "completata"})
        dettaglio = f"referto {esito['referto_id']}, ${esito['costo_usd']:.4f}"
        # I metodi a piu' passi hanno gia' avanzato loro, uno per fase.
        if passi == PASSI_PREDEFINITI:
            lavoro.advance(detail=dettaglio)
        else:
            lavoro.detail = dettaglio

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
