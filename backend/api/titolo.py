"""
titolo.py — la scheda di un singolo titolo.
# feat (Blocco 6): il guscio, il grafico, e le sezioni che dichiarano di essere vuote.

Il precedente da non ripetere sono le 1.342 righe di `app/ticker/[symbol]/page.tsx`
del vecchio tradash: una pagina che sapeva tutto. Qui il backend espone pezzi
separati, e la pagina li mette insieme — cosi' i blocchi 7 e 8 aggiungono le
loro sezioni senza toccare quelle che ci sono gia'.

Le sezioni non ancora costruite non spariscono: rispondono `available: false`
con dentro il blocco che le portera' (regola 5).
"""
import logging
from datetime import UTC, datetime, timedelta

from flask import Blueprint, request

import config
from api import HTTP_NOT_FOUND, fail, ok
from core.db import db_read
from core.tipi import python_puro
from data import defeatbeta, depositi, filing_locali, grafici, materiale, ricostruzione
from data.grafici import GraficiError
from domain import (
    indicators,
    prospetti,
    publication_dates,
    salute,
    simulatore,
    voci,
)

logger = logging.getLogger(__name__)

bp = Blueprint("titolo", __name__, url_prefix="/api/titolo")

# Le sezioni promesse dal PIANO e non ancora costruite. Dichiararle qui e' il
# modo di non farle sparire: la pagina le mostra vuote, col blocco che le porta.
# Le sezioni della scheda non ancora costruite. **Adesso e' vuoto**: i sette
# metodi ci sono tutti e la ricostruzione point-in-time e' arrivata. Il
# meccanismo resta perche' la regola che lo ha prodotto vale ancora — una
# sezione che manca lo dice, con dentro quale blocco la portera', invece di far
# finta che quel dato non esista.
#
# Cio' che manca ora non e' una sezione: e' la verifica dal vivo delle chiamate
# al modello, e quella si dichiara dove sta — nel registro dei metodi.
SEZIONI_FUTURE: dict[str, dict] = {}

ACTION_SEZIONE_FUTURA = "questa sezione arriva con il blocco {blocco} del piano"

# Come si leggono le variazioni nel simulatore: la giornata, o la strada fatta
# dal giorno d'acquisto. La prima e' quello che si sente, la seconda quello che
# si ricorda.
BASE_GIORNO = "giorno"
BASE_PERIODO = "periodo"


def _capitale(grezzo: str | None) -> tuple[float, str | None]:
    """Il capitale investito, validato. Ritorna (valore, errore)."""
    if not grezzo:
        return config.SIMULATORE_CAPITALE_PREDEFINITO, None
    try:
        valore = float(grezzo)
    except ValueError:
        return 0.0, f"capitale non e' un numero: {grezzo!r}"
    if valore <= 0:
        return 0.0, "il capitale dev'essere maggiore di zero"
    return valore, None


def _profilo(simbolo: str) -> dict:
    """L'anagrafica del titolo, o il motivo per cui non c'e'."""
    lettura = defeatbeta.profile(simbolo)
    if not lettura.available:
        return {"available": False, "reason": lettura.reason, "action": lettura.action}

    riga = lettura.frame.iloc[0]
    campi = ("sector", "industry", "country", "long_business_summary",
             "full_time_employees", "web_site", "city")
    return {"available": True, "source": lettura.source,
            **{campo: python_puro(riga.get(campo)) for campo in campi}}


def _nome(simbolo: str) -> str | None:
    """Il nome della societa', preso dall'universo che lo ha gia' derivato.

    Non si rilegge da Defeatbeta: sta gia' in tabella, e chiederlo di nuovo
    sarebbe una lettura in piu' per un dato che non cambia.
    """
    with db_read() as conn:
        riga = conn.execute(
            "SELECT name FROM universe WHERE symbol = ?", (simbolo.strip().upper(),)
        ).fetchone()
    return riga["name"] if riga else None


def _intervallo(nome: str | None) -> tuple[str | None, str | None]:
    """La data da cui partire per l'intervallo chiesto. Ritorna (data, errore)."""
    scelto = nome or config.INTERVALLO_GRAFICO_PREDEFINITO
    if scelto not in config.INTERVALLI_GRAFICO:
        return None, (f"intervallo sconosciuto: {scelto!r}. "
                      f"Ammessi: {', '.join(config.INTERVALLI_GRAFICO)}")

    giorni = config.INTERVALLI_GRAFICO[scelto]
    if giorni is None:
        return None, None
    return (datetime.now(UTC) - timedelta(days=giorni)).strftime("%Y-%m-%d"), None


@bp.get("/<simbolo>")
def scheda(simbolo: str):
    """L'intestazione della scheda: chi e' questo titolo, e cosa non c'e' ancora."""
    return ok({
        "symbol": simbolo.strip().upper(),
        "name": _nome(simbolo),
        "profilo": _profilo(simbolo),
        "sezioni_future": {
            nome: {"available": False,
                   "reason": f"{dati['cosa']}: non ancora costruita",
                   "action": ACTION_SEZIONE_FUTURA.format(blocco=dati["blocco"]),
                   "blocco": dati["blocco"]}
            for nome, dati in SEZIONI_FUTURE.items()
        },
    })


def _barre(frame) -> list[dict]:
    """Le barre OHLCV nella forma che il motore degli indicatori si aspetta."""
    return [
        {"timestamp": str(r["report_date"]),
         **{campo: python_puro(r[campo]) for campo in ("open", "high", "low", "close", "volume")}}
        for _, r in frame.iterrows()
    ]


def _taglia(barre: list[dict], serie: dict, da: str | None) -> tuple[list[dict], dict]:
    """Tiene solo la parte visibile, dopo che il calcolo ha visto tutto.

    Il taglio e' sulla POSIZIONE, non sulla data: barre e serie sono allineate
    per indice, e ritagliarle con due criteri diversi le sfaserebbe di un giorno
    senza che niente lo segnali.

    Assume che le barre siano in ordine di data crescente, che e' come le
    ritorna `defeatbeta.prices` (ORDER BY report_date). Su barre disordinate il
    taglio cadrebbe alla prima data buona incontrata, non all'ultima.
    """
    if da is None:
        return barre, serie

    primo = next((i for i, b in enumerate(barre) if b["timestamp"] >= da), len(barre))
    return barre[primo:], {chiave: punti[primo:] for chiave, punti in serie.items()}


@bp.get("/<simbolo>/prezzi")
def prezzi(simbolo: str):
    """Le barre OHLCV e le serie degli indicatori, gia' calcolate.

    Il taglio dell'intervallo si fa qui e non nella query: il costo e' leggere
    il parquet dei prezzi, e leggerlo una volta per tenersi tutta la storia
    rende gratis il cambio di periodo.
    """
    da, errore = _intervallo(request.args.get("intervallo"))
    if errore:
        return fail(errore)

    lettura = defeatbeta.prices(simbolo)
    if not lettura.available:
        return fail(lettura.reason, HTTP_NOT_FOUND)

    tutte = _barre(lettura.frame)
    configurazione = grafici.configurazione(simbolo)
    try:
        # Si calcola su TUTTA la storia e si taglia dopo. Calcolare sul solo
        # intervallo mostrato darebbe, a un mese di grafico, una "media a 50
        # giorni" costruita su ventidue sedute: un numero che sembra giusto e
        # non lo e'. Le medie mobili hanno bisogno del passato che non si vede.
        serie = indicators.compute(tutte, configurazione)
    except indicators.IndicatorConfigError as exc:
        logger.exception("[TITOLO] configurazione del grafico rotta per %s", simbolo)
        return fail(f"la configurazione del grafico non e' valida: {exc}")

    barre, serie = _taglia(tutte, serie, da)
    return ok({"symbol": simbolo.strip().upper(), "barre": barre, "serie": serie,
               "configurazione": configurazione, "source": lettura.source,
               "sedute_calcolate": len(tutte),
               "ultimo_prezzo": tutte[-1]["close"] if tutte else None,
               "ultima_seduta": tutte[-1]["timestamp"] if tutte else None,
               # Le variazioni su tutti gli intervalli, non solo su quello
               # mostrato: costano zero — i prezzi sono gia' letti tutti — e
               # servono a rispondere a «e sul trimestre?» senza ricaricare.
               "variazioni": _variazioni(tutte),
               "intervalli": list(config.INTERVALLI_GRAFICO)})


def _variazioni(barre: list[dict]) -> dict:
    """Quanto si e' mosso il prezzo su ciascun intervallo.

    Il confronto e' con la PRIMA seduta dell'intervallo, non con quella di
    esattamente N giorni fa: se quel giorno la borsa era chiusa non esiste un
    prezzo, e prendere il piu' vicino sarebbe un confronto con una data diversa
    da quella dichiarata.

    Un intervallo piu' lungo della storia disponibile vale `None`, non zero: un
    titolo quotato da otto mesi non ha fatto lo 0% in cinque anni.
    """
    if not barre:
        return {}

    ultimo = barre[-1]["close"]
    fatte = {}
    for nome, giorni in config.INTERVALLI_GRAFICO.items():
        if giorni is None:
            dentro = barre
        else:
            da = (datetime.now(UTC) - timedelta(days=giorni)).strftime("%Y-%m-%d")
            dentro = [b for b in barre if b["timestamp"] >= da]

        # Serve almeno una seduta PRIMA dell'intervallo, altrimenti la storia
        # comincia dentro e il confronto sarebbe con se stessa.
        abbastanza = len(dentro) >= 2 and (giorni is None or len(dentro) < len(barre))
        primo = dentro[0]["close"] if dentro else None
        fatte[nome] = {
            "variazione": (round(ultimo / primo - 1, 6)
                           if abbastanza and primo else None),
            "da": dentro[0]["timestamp"] if dentro else None,
            "sedute": len(dentro),
            "reason": None if abbastanza else "la storia del titolo non copre "
                                              "tutto l'intervallo",
        }
    return fatte


@bp.get("/<simbolo>/grafico")
def grafico(simbolo: str):
    """La configurazione in uso per questo titolo, e i tipi di indicatore possibili."""
    try:
        return ok({"configurazione": grafici.configurazione(simbolo),
                   "kind_ammessi": sorted(indicators.VALID_KINDS)})
    except GraficiError as exc:
        return fail(str(exc))


@bp.put("/<simbolo>/grafico")
def salva_grafico(simbolo: str):
    """Salva la configurazione del grafico per questo titolo."""
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict) or "nodes" not in corpo:
        return fail("serve un oggetto JSON con dentro 'nodes'")
    try:
        return ok(grafici.imposta(simbolo, corpo))
    except GraficiError as exc:
        return fail(str(exc))


@bp.delete("/<simbolo>/grafico")
def dimentica_grafico(simbolo: str):
    """Torna alla configurazione predefinita per questo titolo."""
    try:
        return ok({"dimenticata": grafici.dimentica(simbolo)})
    except GraficiError as exc:
        return fail(str(exc))


# --- fondamentali, filing e news: il Blocco 7 ------------------------------

def _as_of(grezzo: str | None) -> tuple[str | None, str | None]:
    """La data a cui ricostruire, validata. Ritorna (data, errore).

    Una data scritta male non deve diventare "nessun taglio": senza taglio si
    vede il futuro, ed e' l'esatto contrario di quello che chiedeva chi l'ha
    scritta.
    """
    if not grezzo:
        return None, None
    try:
        datetime.strptime(grezzo, "%Y-%m-%d")
    except ValueError:
        return None, f"as_of non e' una data YYYY-MM-DD: {grezzo!r}"
    return grezzo, None


def _periodi_visibili(depositi: dict, tutti: list[str], quando: str | None,
                      trimestrale: bool) -> list[str] | None:
    """Quali periodi erano gia' depositati a quella data. `None` = nessun taglio."""
    if quando is None:
        return None
    return [p for p in tutti if publication_dates.was_public(depositi, p, quando, trimestrale)]


@bp.get("/<simbolo>/fondamentali")
def fondamentali(simbolo: str):
    """I bilanci, e — se chiedi una data — solo quelli che allora erano pubblici.

    La risposta porta sempre `base_del_taglio`: dice se il taglio poggia su date
    di deposito REALI o su un ritardo stimato. Un risultato costruito sulle une
    e uno costruito sulle altre non sono confrontabili, e chi legge deve poterlo
    sapere senza andare a indovinare.
    """
    quando, errore = _as_of(request.args.get("as_of"))
    if errore:
        return fail(errore)

    periodicita = request.args.get("periodicita", prospetti.TRIMESTRALE)
    if periodicita not in (prospetti.TRIMESTRALE, prospetti.ANNUALE):
        return fail(f"periodicita' sconosciuta: {periodicita!r}")

    lettura = defeatbeta.statements(simbolo)
    if not lettura.available:
        return fail(lettura.reason, HTTP_NOT_FOUND)

    tutti = prospetti.periodi(lettura.frame)
    mappa_depositi = depositi.mappa(simbolo)
    trimestrale = periodicita == prospetti.TRIMESTRALE
    visibili = _periodi_visibili(mappa_depositi, tutti, quando, trimestrale)
    tabelle = {
        nome: prospetti.tabella(lettura.frame, nome, periodicita, visibili)
        for nome in prospetti.PROSPETTI
    }

    return ok({
        "symbol": simbolo.strip().upper(),
        "as_of": quando,
        "periodicita": periodicita,
        "prospetti": tabelle,
        # Le etichette italiane accanto ai nomi originali, non al posto loro:
        # chi confronta col bilancio depositato deve ritrovare la stessa parola,
        # chi legge deve capire cosa sta guardando. Due bisogni, nessuno sacrificato.
        "nomi": voci.etichette({v for t in tabelle.values() for v in t["voci"]}),
        "periodi_totali": len(tutti),
        "periodi_visibili": len(visibili) if visibili is not None else len(tutti),
        "base_del_taglio": publication_dates.truncation_basis(
            mappa_depositi, visibili if visibili is not None else tutti, trimestrale
        ),
        "source": lettura.source,
    })


@bp.get("/<simbolo>/filings")
def filings(simbolo: str):
    """I documenti depositati alla SEC, dal piu' recente."""
    quando, errore = _as_of(request.args.get("as_of"))
    if errore:
        return fail(errore)

    lettura = defeatbeta.sec_filings(simbolo)
    if not lettura.available:
        return ok({"symbol": simbolo.strip().upper(), "available": False,
                   "reason": lettura.reason, "action": lettura.action, "documenti": []})

    documenti = [
        {campo: python_puro(riga.get(campo)) for campo in
         ("form_type", "form_type_description", "filing_date", "report_date", "filing_url")}
        for _, riga in lettura.frame.iterrows()
    ]
    if quando:
        # Un documento depositato DOPO la data non esisteva: qui il taglio e'
        # esatto, perche' la data di deposito e' proprio la colonna che abbiamo.
        documenti = [d for d in documenti if (d["filing_date"] or "") <= quando]

    return ok({"symbol": simbolo.strip().upper(), "available": True, "as_of": quando,
               "documenti": documenti[:config.FILINGS_MOSTRATI],
               "totale": len(documenti), "source": lettura.source})


@bp.get("/<simbolo>/news")
def news(simbolo: str):
    """Le notizie sul titolo, dalla piu' recente."""
    quando, errore = _as_of(request.args.get("as_of"))
    if errore:
        return fail(errore)

    lettura = defeatbeta.news(simbolo, limit=config.NEWS_MOSTRATE)
    if not lettura.available:
        return ok({"symbol": simbolo.strip().upper(), "available": False,
                   "reason": lettura.reason, "action": lettura.action, "notizie": []})

    notizie = [
        {campo: python_puro(riga.get(campo)) for campo in
         ("title", "publisher", "report_date", "link", "type")}
        for _, riga in lettura.frame.iterrows()
    ]
    if quando:
        notizie = [n for n in notizie if (n["report_date"] or "") <= quando]

    return ok({"symbol": simbolo.strip().upper(), "available": True, "as_of": quando,
               "notizie": notizie, "source": lettura.source})


@bp.get("/<simbolo>/segnali")
def segnali_fondamentali(simbolo: str):
    """I cinque segnali di rischio fondamentale, calcolati dai bilanci.

    Deterministici: nessun modello linguistico, nessuna opinione. Ogni segnale
    porta le misure su cui poggia, e la copertura dice quanti si sono potuti
    calcolare — tre spenti su cinque calcolabili non sono la stessa cosa di tre
    spenti su cinque quando gli altri due erano ignoti.

    Con `as_of` si ricostruiscono sui soli bilanci che a quella data erano gia'
    stati depositati, come i fondamentali.
    """
    quando, errore = _as_of(request.args.get("as_of"))
    if errore:
        return fail(errore)

    try:
        # Lo stesso taglio che usa la ricostruzione point-in-time, e la stessa
        # funzione: due tagli scritti due volte divergono, e il giorno che
        # divergono una delle due pagine mostra il futuro senza dirlo.
        calcolati = materiale.segnali_fondamentali(simbolo, None, quando)
    except materiale.AnalisiError as exc:
        return fail(str(exc), HTTP_NOT_FOUND)

    return ok({"symbol": simbolo.strip().upper(), **calcolati})


@bp.get("/<simbolo>/ricostruzione")
def ricostruzione_point_in_time(simbolo: str):
    """Cosa si poteva sapere a una data passata, e cosa e' successo dopo.

    Una lettura scritta oggi si potra' giudicare fra un anno; ricostruita a una
    data passata si giudica subito, perche' il dopo e' gia' successo.

    Nessun modello: misure deterministiche di allora e prezzi di poi. E i due
    tagli sono diversi — i prezzi sulla data, i bilanci sulla data di DEPOSITO.
    """
    quando, errore = _as_of(request.args.get("as_of"))
    if errore:
        return fail(errore)
    if quando is None:
        return fail("serve as_of: senza una data non c'e' niente da ricostruire")

    esito = ricostruzione.confronto(simbolo, quando)
    if not esito["available"]:
        return fail(esito["reason"], HTTP_NOT_FOUND)
    return ok(esito)


@bp.get("/<simbolo>/salute")
def salute_finanziaria(simbolo: str):
    """Figure di bilancio e rapporti di solidita'. **Nessun punteggio.**

    Nel vecchio sistema questa sezione produceva un Health Score 0-100 con
    etichetta: era un secondo verdetto sulla stessa azienda, parallelo a quello
    della qualita' fondamentale e non riconciliato con esso. Qui ci sono i dati;
    il giudizio lo da' l'analisi fondamentale, ed e' uno solo.

    Con `as_of` si ricostruisce sui soli bilanci che a quella data erano gia'
    stati depositati, come i segnali.
    """
    quando, errore = _as_of(request.args.get("as_of"))
    if errore:
        return fail(errore)

    lettura = defeatbeta.statements(simbolo)
    if not lettura.available:
        return fail(lettura.reason, HTTP_NOT_FOUND)

    mappa_depositi = depositi.mappa(simbolo)
    tutti = prospetti.periodi(lettura.frame)
    visibili = _periodi_visibili(mappa_depositi, tutti, quando, trimestrale=True)
    tabelle = {
        nome: prospetti.tabella(lettura.frame, nome, prospetti.TRIMESTRALE, visibili)
        for nome in prospetti.PROSPETTI
    }

    return ok({
        "symbol": simbolo.strip().upper(), "as_of": quando,
        **salute.quadro(tabelle),
        "base_del_taglio": publication_dates.truncation_basis(
            mappa_depositi, visibili if visibili is not None else tutti, True
        ) if quando else None,
        "source": lettura.source,
    })


@bp.get("/<simbolo>/simulatore")
def simulatore_psicologico(simbolo: str):
    """Cosa si sarebbe vissuto comprando questo titolo un certo giorno.

    Non e' un backtest di strategia: non c'e' nessuna strategia. C'e' una
    posizione sola, e la domanda non e' «quanto avrei guadagnato» ma «cosa avrei
    passato» — quanto e' sceso nel mezzo, quanto tempo e' stato in perdita.

    Parametri: `da` (giorno d'acquisto), `capitale`, e `base` — «giorno» per la
    variazione giorno su giorno, «periodo» per quella dal giorno d'acquisto.
    """
    quando, errore = _as_of(request.args.get("da"))
    if errore:
        return fail(errore.replace("as_of", "da"))

    capitale, errore = _capitale(request.args.get("capitale"))
    if errore:
        return fail(errore)

    base = request.args.get("base", BASE_GIORNO)
    if base not in (BASE_GIORNO, BASE_PERIODO):
        return fail(f"base sconosciuta: {base!r}. Ci sono: {BASE_GIORNO}, {BASE_PERIODO}")

    lettura = defeatbeta.prices(simbolo)
    if not lettura.available:
        return fail(lettura.reason, HTTP_NOT_FOUND)

    tutte = simulatore.variazioni(_barre(lettura.frame))
    dentro = [s for s in tutte if quando is None or s["data"] >= quando]
    if not dentro:
        return fail(f"nessuna seduta dal {quando}: il primo prezzo che Defeatbeta "
                    f"ha per {simbolo.strip().upper()} e' del "
                    f"{tutte[0]['data'] if tutte else '?'}", HTTP_NOT_FOUND)

    mostrate = simulatore.dal_punto(dentro) if base == BASE_PERIODO else dentro

    return ok({
        "symbol": simbolo.strip().upper(), "da": quando, "base": base,
        "capitale": capitale,
        "griglia": simulatore.griglia(mostrate),
        "esperienza": simulatore.esperienza(dentro, capitale),
        "prima_seduta_disponibile": tutte[0]["data"] if tutte else None,
        "source": lettura.source,
    })


@bp.get("/<simbolo>/filing-da-salvare")
def filing_da_salvare(simbolo: str):
    """Quali documenti SEC servono all'analisi qualitativa, e dove metterli.

    Defeatbeta ha l'indice dei depositi ma non il loro testo, e il testo e' la
    fonte primaria della qualitativa. Qui si dice quali servono, con che nome
    salvarli e in quale cartella: il riconoscimento avviene sul numero di
    protocollo, quindi un nome diverso va bene purche' quel numero ci sia.
    """
    try:
        return ok(filing_locali.stato(simbolo))
    except filing_locali.FilingError as exc:
        return fail(str(exc))


# --- le metriche gia' calcolate --------------------------------------------

# Quali metriche hanno una gemella di settore, per mostrarle accanto. E' il
# confronto che il vecchio tradash non sapeva fare: il suo registro dei peer
# copriva 7 ticker su 18.
GEMELLE_DI_SETTORE = {
    "roe": "industry_roe",
    "roa": "industry_roa",
    "roic": "industry_roic",
    "ttm_pe": "industry_ttm_pe",
    "quarterly_gross_margin": "industry_quarterly_gross_margin",
    "quarterly_net_margin": "industry_quarterly_net_margin",
}

# Quante righe di una serie si mandano al frontend: le piu' recenti bastano.
RIGHE_METRICA = 24


@bp.get("/<simbolo>/metriche")
def catalogo_metriche(simbolo: str):
    """Quali metriche si possono chiedere per questo titolo, e quali costano.

    Nessuna viene calcolata qui: aprire la pagina non deve far partire trenta
    query (regola 2). Si chiedono una alla volta, quando servono.
    """
    return ok({
        "symbol": simbolo.strip().upper(),
        "metriche": [
            {"nome": nome, "descrizione": descrizione,
             "lenta": nome in defeatbeta.METRICHE_LENTE,
             "gemella_di_settore": GEMELLE_DI_SETTORE.get(nome)}
            for nome, descrizione in sorted(defeatbeta.METRICHE.items())
            if not nome.startswith("industry_")
        ],
    })


def _serie(simbolo: str, nome: str) -> dict:
    """Una metrica come serie di righe pronte da mostrare."""
    lettura = defeatbeta.metrica(simbolo, nome)
    if not lettura.available:
        return {"available": False, "reason": lettura.reason, "action": lettura.action,
                "righe": []}

    frame = lettura.frame.tail(RIGHE_METRICA)
    return {
        "available": True, "source": lettura.source,
        "colonne": [c for c in frame.columns if c != "symbol"],
        "righe": [
            {c: python_puro(riga[c]) for c in frame.columns if c != "symbol"}
            for _, riga in frame.iterrows()
        ],
    }


@bp.get("/<simbolo>/metriche/<nome>")
def metrica(simbolo: str, nome: str):
    """Una metrica, con accanto quella dell'industria quando esiste.

    La serie arriva con le sue date: chi vuole ricostruire a una data passata
    taglia lei, come per i bilanci.
    """
    if nome not in defeatbeta.METRICHE:
        return fail(f"metrica sconosciuta: {nome!r}")

    try:
        risposta = {"symbol": simbolo.strip().upper(), "nome": nome,
                    "descrizione": defeatbeta.METRICHE[nome],
                    "titolo": _serie(simbolo, nome)}
        gemella = GEMELLE_DI_SETTORE.get(nome)
        if gemella and request.args.get("con_settore", "1") == "1":
            risposta["settore"] = {"nome": gemella, **_serie(simbolo, gemella)}
        return ok(risposta)
    except defeatbeta.DefeatbetaUnavailable as exc:
        return fail(str(exc))
