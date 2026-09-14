"""
test_blocco2.py — la verifica del Blocco 2: l'universo si deriva, si vede, si ferma.
# feat: se questi test non passano, non si va al Blocco 3.
# feat (14/09/2026): l'universo e' due meta' con due freschezze, e si verifica
#   che restino separate.

Il PIANO chiede una derivazione da `stock_profile`, senza JSON statici. Qui si
verifica quello e le cose che lo circondano: che il lavoro sia fermabile davvero
(non "in teoria"), che i titoli con caselle vuote entrino lo stesso invece di
sparire, che l'universo mai costruito lo dica, e che rinfrescare l'anagrafica
non porti via i prezzi.

Il finto sta sotto cio' che si misura: si sostituiscono le due derivazioni —
cioe' le query su DuckDB — e restano vere la scrittura in transazione, il
registro dei lavori, la freschezza, la vista, i filtri e le route.
"""
import sqlite3
import threading
from datetime import date, timedelta

import pandas as pd
import pytest

import config
from core import freshness, registry
from core.db import db_read
from core.schema import GLOBAL_SCOPE
from data import defeatbeta, fondamentali, scanner, universe
from domain import scansione

# Un universo finto piccolo, ma con dentro i casi scomodi: una societa' non
# americana quotata negli USA, e un titolo a cui manca meta' dei dati.
# L'ultima chiusura dei titoli finti si conta da OGGI, non da una data scritta.
#
# Prima era «2026-08-28», e il test e' passato finche' quella data e' rimasta
# entro i sette giorni oltre i quali un prezzo si considera vecchio. Al primo
# giorno buono ha cominciato a fallire da solo, dicendo che tre titoli su tre
# avevano il prezzo vecchio: e non era cambiato il codice, era passato il tempo.
# Un test che dipende dal calendario non misura cio' che dice di misurare.
IERI = (date.today() - timedelta(days=1)).isoformat()

# Le azioni in circolazione sono scelte perche' il prodotto col prezzo dia le
# capitalizzazioni vere: AAPL 4,67e12 e BABA 2,85e11. Adesso che `market_cap`
# e' calcolato dalla vista e non piu' conservato, scriverlo a mano nel finto
# non misurerebbe piu' niente — lo calcola SQLite, e va calcolato sui fattori.
ANAGRAFICA_FINTA = [
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology",
     "industry": "Consumer Electronics", "company_country": "United States",
     "employees": 150000, "shares_outstanding": 1.4607e10},
    {"symbol": "BABA", "name": "Alibaba Group Holding Limited",
     "sector": "Consumer Cyclical", "industry": "Internet Retail",
     "company_country": "China", "employees": 132165,
     "shares_outstanding": 2.397e9},
    {"symbol": "ZOMB", "name": None, "sector": None, "industry": None,
     "company_country": None, "employees": None, "shares_outstanding": None},
]

# I prezzi ne contengono uno in piu': FANT non ha anagrafica. Non e' un caso
# inventato — alla ricostruzione del 14/09/2026 i prezzi coprivano 12.289
# simboli e l'anagrafica 11.351, sovrapposti su 11.283: 1.006 quotazioni sono
# state scartate proprio cosi'.
MERCATO_FINTO = [
    {"symbol": "AAPL", "last_close": 319.7, "last_close_date": IERI,
     "avg_volume_30d": 48259040.0},
    {"symbol": "BABA", "last_close": 118.9, "last_close_date": IERI,
     "avg_volume_30d": 11934780.0},
    {"symbol": "FANT", "last_close": 7.5, "last_close_date": IERI,
     "avg_volume_30d": 1000.0},
]

TIMEOUT_S = 5.0


def _lettura_finta(records, categoria) -> defeatbeta.Lettura:
    """Un risultato di derivazione, nella forma che ritorna il punto unico."""
    frame = pd.DataFrame(records)
    return defeatbeta.Lettura(
        frame=frame, scope=GLOBAL_SCOPE, category=categoria,
        source="cache", available=not frame.empty,
        reason=f"{len(frame)} righe finte",
    )


@pytest.fixture
def derivazione_finta(monkeypatch):
    """Sostituisce le due query, lasciando vero tutto il resto della catena."""
    chiamate = {"anagrafica": 0, "mercato": 0}

    def _anagrafica(run_id=None):
        chiamate["anagrafica"] += 1
        return _lettura_finta(ANAGRAFICA_FINTA, defeatbeta.CATEGORY_ANAGRAFICA)

    def _mercato(run_id=None):
        chiamate["mercato"] += 1
        return _lettura_finta(MERCATO_FINTO, defeatbeta.CATEGORY_MERCATO)

    monkeypatch.setattr(defeatbeta, "anagrafica_universo", _anagrafica)
    monkeypatch.setattr(defeatbeta, "mercato_universo", _mercato)
    return chiamate


def _costruisci_tutto() -> None:
    """Le due meta', nell'ordine obbligato: il mercato ha bisogno dell'anagrafica."""
    universe.build_anagrafica()
    universe.build_mercato()


def _titoli_in_tabella() -> list[dict]:
    """Cosa mostra la VISTA, che e' cio' che il resto del sistema legge."""
    with db_read() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM universe ORDER BY symbol")]


def _prezzi_in_tabella() -> list[dict]:
    with db_read() as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM universe_mercato ORDER BY symbol")]


def _lavoro(run_id: str) -> dict:
    with db_read() as conn:
        return dict(conn.execute("SELECT * FROM jobs WHERE run_id = ?", (run_id,)).fetchone())


def _attendi_fine(run_id: str) -> dict:
    """Aspetta che un lavoro avviato in un thread sia davvero finito.

    Non e' pignoleria: un test che finisce lasciando vivo il suo thread lo
    consegna al test successivo, dove il monkeypatch non c'e' piu' e la
    derivazione FINTA torna a essere quella vera. E' successo — la rete spenta
    l'ha fermata, ma il lavoro non sorvegliato e' proprio cio' che qui non deve
    esistere.
    """
    scadenza = threading.Event()
    while not scadenza.wait(0.02):
        lavoro = _lavoro(run_id)
        if lavoro["ended_at"] is not None:
            return lavoro
    raise AssertionError(f"il lavoro {run_id} non e' mai finito")


# --- la derivazione ---------------------------------------------------------

def test_la_costruzione_deriva_scrive_e_marca_la_freschezza(derivazione_finta):
    """Il cuore del blocco: niente JSON statici, la lista viene dalla derivazione."""
    esito = universe.build_anagrafica()

    assert esito["costruito"] is True
    assert esito["titoli"] == len(ANAGRAFICA_FINTA)
    assert [t["symbol"] for t in _titoli_in_tabella()] == ["AAPL", "BABA", "ZOMB"]
    assert freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_ANAGRAFICA) is not None

    lavoro = _lavoro(esito["run_id"])
    assert lavoro["status"] == registry.STATUS_DONE
    assert lavoro["done"] == universe.PASSI_COSTRUZIONE


def test_una_seconda_costruzione_non_rifa_il_lavoro_e_dice_perche(derivazione_finta):
    """Il gate di freschezza si interroga PRIMA di andare in rete, non dopo."""
    universe.build_anagrafica()
    esito = universe.build_anagrafica()

    assert esito["costruito"] is False
    assert "fresco" in esito["motivo"]
    assert derivazione_finta["anagrafica"] == 1, "la derivazione non doveva ripartire"
    assert "saltato" in _lavoro(esito["run_id"])["detail"], (
        "anche un lavoro saltato deve restare in cronologia col suo motivo"
    )


def test_force_ricostruisce_comunque(derivazione_finta):
    """L'utente puo' sempre scavalcare il gate, ma deve dirlo."""
    universe.build_anagrafica()
    esito = universe.build_anagrafica(force=True)

    assert esito["costruito"] is True
    assert derivazione_finta["anagrafica"] == 2


# --- le due meta' sono davvero due ------------------------------------------

def test_il_mercato_senza_anagrafica_si_rifiuta_dicendo_perche(derivazione_finta):
    """Regola 5: non zero righe in silenzio, ma un motivo e un'azione.

    I prezzi si tengono solo dei titoli che hanno un'anagrafica. Senza, il
    lavoro non saprebbe di chi tenerli e scriverebbe una tabella vuota che
    sembra un guasto dei dati.
    """
    esito = universe.build_mercato()

    assert esito["costruito"] is False
    assert esito["motivo"] == universe.MOTIVO_SENZA_ANAGRAFICA
    assert esito["action"] == universe.ACTION_UNIVERSO_VUOTO
    assert derivazione_finta["mercato"] == 0, "non doveva nemmeno leggere"
    assert _prezzi_in_tabella() == []


def test_ricostruire_l_anagrafica_non_porta_via_i_prezzi(derivazione_finta):
    """Il difetto che questo test esiste per impedire.

    `universe_mercato.symbol` punta all'anagrafica con ON DELETE CASCADE: se la
    ricostruzione dell'anagrafica fosse un DELETE seguito da un INSERT, ogni due
    settimane i prezzi sparirebbero tutti fino al giorno dopo. Si aggiorna chi
    c'e' invece di svuotare.
    """
    _costruisci_tutto()
    prezzi_prima = _prezzi_in_tabella()
    assert prezzi_prima, "servono dei prezzi da poter perdere"

    universe.build_anagrafica(force=True)

    assert _prezzi_in_tabella() == prezzi_prima


def test_un_titolo_sparito_dal_dataset_esce_e_si_porta_via_il_prezzo(derivazione_finta,
                                                                    monkeypatch):
    """Chi non e' piu' nel dataset non resta in tabella per inerzia.

    E il suo prezzo se ne va con lui: un prezzo senza anagrafica e' proprio la
    riga cieca che non si vuole conservare.
    """
    _costruisci_tutto()
    assert "BABA" in [t["symbol"] for t in _titoli_in_tabella()]

    sopravvissuti = [r for r in ANAGRAFICA_FINTA if r["symbol"] != "BABA"]
    monkeypatch.setattr(
        defeatbeta, "anagrafica_universo",
        lambda run_id=None: _lettura_finta(sopravvissuti, defeatbeta.CATEGORY_ANAGRAFICA),
    )
    esito = universe.build_anagrafica(force=True)

    assert esito["spariti"] == 1
    assert "BABA" not in [t["symbol"] for t in _titoli_in_tabella()]
    assert "BABA" not in [p["symbol"] for p in _prezzi_in_tabella()]


def test_i_titoli_senza_anagrafica_non_entrano_nei_prezzi(derivazione_finta):
    """I 1.006 simboli quotati di cui Defeatbeta non pubblica il profilo.

    Hanno un prezzo e nessun'altra cosa: conservarlo vorrebbe dire una riga che
    nessuna pagina mostrera' mai, perche' ogni lettura parte dall'anagrafica.
    """
    _costruisci_tutto()
    esito = universe.build_mercato(force=True)

    assert esito["senza_anagrafica"] == 1
    assert "FANT" not in [p["symbol"] for p in _prezzi_in_tabella()]
    assert "FANT" not in [t["symbol"] for t in _titoli_in_tabella()]


def test_le_due_freschezze_sono_indipendenti(derivazione_finta):
    """Regola 3: il guard sta sull'eta' del dato che mostri, per CATEGORIA.

    Prima erano una sola: `sector` e `last_close` ricevevano lo stesso verdetto
    pur invecchiando a velocita' diverse di tre ordini di grandezza.
    """
    universe.build_anagrafica()

    assert freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_ANAGRAFICA) is not None
    assert freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_MERCATO) is None

    stato = universe.stato()
    assert stato["anagrafica"]["da_ricostruire"] is False
    assert stato["mercato"]["da_ricostruire"] is True
    assert "mai preso" in stato["mercato"]["reason"]


def test_i_due_ttl_sono_diversi_e_dichiarati():
    """Due settimane contro un giorno: e' la scelta che rende la separazione utile."""
    assert config.FRESHNESS_TTL_S["universe_anagrafica"] == 14 * config.SECONDS_PER_DAY
    assert config.FRESHNESS_TTL_S["universe_mercato"] == 1 * config.SECONDS_PER_DAY


def test_market_cap_e_calcolato_non_conservato(derivazione_finta, monkeypatch):
    """Il prodotto di due numeri di epoche diverse non deve poter esistere.

    Prima `market_cap` si scriveva al momento della costruzione. Da quando le
    due meta' si rinfrescano a ritmi diversi, conservarlo vorrebbe dire tenere
    un prezzo di stanotte moltiplicato per delle azioni di due settimane fa,
    senza che nessuno lo dica. Qui si cambiano le azioni e basta: la
    capitalizzazione deve seguirle senza toccare i prezzi.
    """
    _costruisci_tutto()
    prima = next(t for t in _titoli_in_tabella() if t["symbol"] == "AAPL")["market_cap"]

    raddoppiate = [{**r, "shares_outstanding": (r["shares_outstanding"] or 0) * 2}
                   for r in ANAGRAFICA_FINTA]
    monkeypatch.setattr(
        defeatbeta, "anagrafica_universo",
        lambda run_id=None: _lettura_finta(raddoppiate, defeatbeta.CATEGORY_ANAGRAFICA),
    )
    universe.build_anagrafica(force=True)

    dopo = next(t for t in _titoli_in_tabella() if t["symbol"] == "AAPL")["market_cap"]
    assert dopo == pytest.approx(prima * 2)
    assert derivazione_finta["mercato"] == 1, "i prezzi non dovevano essere riletti"


# --- fermabile davvero ------------------------------------------------------

def test_la_costruzione_si_ferma_a_meta_e_resta_stopped(monkeypatch, derivazione_finta):
    """Lo Stop arriva fino al motore: registro -> sentinella -> interruzione.

    Il finto sostituisce l'interruzione di DuckDB, non la sentinella: cosi' il
    filo che si verifica e' quello vero, dal pulsante alla query. Si prova sul
    mercato perche' e' la meta' lunga, quella che si ha davvero bisogno di
    fermare.
    """
    universe.build_anagrafica()
    partita = threading.Event()
    interruzione_chiesta = threading.Event()

    def _interrompi() -> bool:
        interruzione_chiesta.set()
        return True

    def _mercato_lento(run_id=None):
        partita.set()
        assert interruzione_chiesta.wait(TIMEOUT_S), "la sentinella non ha chiesto lo stop"
        raise defeatbeta.DefeatbetaUnavailable("query interrotta")

    monkeypatch.setattr(defeatbeta, "interrupt", _interrompi)
    monkeypatch.setattr(defeatbeta, "mercato_universo", _mercato_lento)

    run_id = universe.build_in_background("mercato")
    assert partita.wait(TIMEOUT_S), "la derivazione non e' mai partita"

    consegnato, motivo = registry.request_stop(run_id)
    assert consegnato is True and motivo is None

    assert _attendi_fine(run_id)["status"] == registry.STATUS_STOPPED
    assert _prezzi_in_tabella() == [], "un lavoro fermato non deve lasciare mezzi prezzi"
    assert freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_MERCATO) is None


def test_un_guasto_del_provider_non_si_traveste_da_stop(monkeypatch):
    """Se nessuno ha premuto Stop, un errore resta un errore: il lavoro fallisce."""
    def _anagrafica_rotta(run_id=None):
        raise defeatbeta.DefeatbetaUnavailable("il provider non risponde")

    monkeypatch.setattr(defeatbeta, "anagrafica_universo", _anagrafica_rotta)

    with pytest.raises(defeatbeta.DefeatbetaUnavailable):
        universe.build_anagrafica()

    with db_read() as conn:
        lavoro = dict(conn.execute("SELECT * FROM jobs ORDER BY started_at DESC").fetchone())
    assert lavoro["status"] == registry.STATUS_FAILED


# --- le caselle vuote si dichiarano, non si nascondono ----------------------

def test_i_titoli_incompleti_entrano_lo_stesso(derivazione_finta):
    """Tenere solo le righe complete farebbe sparire in silenzio 2.636 titoli."""
    _costruisci_tutto()

    zombie = next(t for t in _titoli_in_tabella() if t["symbol"] == "ZOMB")
    assert zombie["sector"] is None
    assert zombie["market_cap"] is None
    assert zombie["last_close"] is None, "senza prezzo resta visibile, non sparisce"


def test_il_paese_non_restringe_l_universo(derivazione_finta):
    """`country` e' il paese della SOCIETA', non della borsa.

    Filtrare su 'United States' butterebbe via BABA e SHOP, che sono quotate
    negli USA: il perimetro americano ce l'ha gia' il dataset.
    """
    _costruisci_tutto()
    assert "BABA" in [t["symbol"] for t in _titoli_in_tabella()]


def test_le_stringhe_vuote_sono_dati_assenti_non_dati_presenti(monkeypatch):
    """Il difetto era nostro, e faceva dichiarare una copertura migliore del vero.

    Nel profilo di Defeatbeta il settore manca 635 volte come NULL e **886 volte
    come stringa vuota**. Contando solo i NULL, la copertura risultava il doppio
    di quella reale: un buco silenzioso prodotto proprio dal codice che doveva
    dichiarare i buchi.
    """
    vuoti = [{"symbol": "VUOT", "name": None, "sector": "   ", "industry": "",
              "company_country": "", "employees": None, "shares_outstanding": None}]
    monkeypatch.setattr(
        defeatbeta, "anagrafica_universo",
        lambda run_id=None: _lettura_finta(vuoti, defeatbeta.CATEGORY_ANAGRAFICA),
    )

    universe.build_anagrafica()

    riga = _titoli_in_tabella()[0]
    assert riga["sector"] is None and riga["industry"] is None
    assert riga["company_country"] is None
    assert universe.stato()["copertura"]["sector"]["mancanti"] == 1


def test_una_capitalizzazione_che_manca_e_non_derivabile_non_assente(derivazione_finta):
    """Dire 'manca al 23,4%' fa sembrare un guasto cio' che per un ETF e' normale.

    `market_cap` e' prezzo per azioni in circolazione: senza uno dei due fattori
    il prodotto non esiste. Su Defeatbeta 2.394 simboli su 11.256 non hanno
    proprio il dato delle azioni.
    """
    _costruisci_tutto()
    capitalizzazione = universe.stato()["capitalizzazione"]

    assert capitalizzazione["non_derivabile"] == 1
    assert capitalizzazione["perche_mancano_le_azioni"] == 1
    assert capitalizzazione["perche_manca_il_prezzo"] == 1


def test_lo_stato_dichiara_la_copertura(derivazione_finta):
    """Regola 5: i buchi si contano e si mostrano, non si scoprono per caso."""
    _costruisci_tutto()
    stato = universe.stato()

    assert stato["available"] is True
    assert stato["titoli"] == 3
    assert stato["titoli_con_prezzo"] == 2, "FANT non ha anagrafica e non si conta"
    assert stato["copertura"]["sector"]["mancanti"] == 1
    assert stato["copertura"]["market_cap"]["mancanti"] == 1
    assert stato["prezzo_vecchio"]["titoli"] == 1, "ZOMB non ha prezzo: va contato"


def test_un_universo_mai_costruito_dice_perche_e_cosa_fare():
    """Non una lista vuota: un `available` a falso, con motivo e azione."""
    stato = universe.stato()

    assert stato["available"] is False
    assert stato["titoli"] == 0
    assert stato["action"] == universe.ACTION_UNIVERSO_VUOTO


# --- filtri e lettura -------------------------------------------------------

def test_i_filtri_sono_parametrizzati_e_il_limite_e_controllato(derivazione_finta):
    """Regola 12: i valori dei filtri non entrano mai nel testo della query."""
    _costruisci_tutto()

    assert [t["symbol"] for t in universe.rows(sector="Technology")] == ["AAPL"]
    assert [t["symbol"] for t in universe.rows(min_market_cap=1e12)] == ["AAPL"]
    assert [t["symbol"] for t in universe.rows(search="ba")] == ["BABA"]
    assert len(universe.rows(limit=1)) == 1

    with pytest.raises(ValueError):
        universe.rows(limit=config.UNIVERSE_PAGE_LIMIT_MAX + 1)


def test_la_ricerca_trova_per_simbolo_e_per_nome(derivazione_finta):
    """Chi cerca "alibaba" non sta cercando un ticker, e chi cerca "BABA" non sta
    scrivendo un nome.

    Il vecchio tradash dava il nome per irrecuperabile da Defeatbeta, avendo
    guardato solo `stock_profile`: sta invece nel calendario degli utili e
    nell'indice dei depositi, e i due insieme coprono il 91,4% dell'universo.
    """
    _costruisci_tutto()

    assert [t["symbol"] for t in universe.rows(search="BAB")] == ["BABA"]
    assert [t["symbol"] for t in universe.rows(search="alibaba")] == ["BABA"], \
        "il nome si cerca ovunque dentro, e senza badare alle maiuscole"
    assert [t["symbol"] for t in universe.rows(search="Apple")] == ["AAPL"]
    assert universe.rows(search="inesistente") == []


def test_un_titolo_senza_nome_resta_cercabile_per_simbolo(derivazione_finta):
    """Il 8,6% dell'universo non ha un nome da nessuna delle due fonti."""
    _costruisci_tutto()

    assert [t["symbol"] for t in universe.rows(search="ZOMB")] == ["ZOMB"]
    assert next(t for t in universe.rows() if t["symbol"] == "ZOMB")["name"] is None


def test_i_titoli_senza_capitalizzazione_finiscono_in_fondo_non_in_cima(derivazione_finta):
    """Ordinare per capitalizzazione con dei NULL in mezzo li mette primi, se non si dice nulla."""
    _costruisci_tutto()
    assert [t["symbol"] for t in universe.rows()] == ["AAPL", "BABA", "ZOMB"]


def test_la_scrittura_dei_prezzi_e_una_transazione_sola(derivazione_finta, monkeypatch):
    """Se la scrittura fallisce a meta', i prezzi di prima restano interi.

    Il guasto si mette DENTRO la transazione, non prima: un errore che capita
    mentre si preparano le righe non arriva mai al DELETE, e non proverebbe
    nulla sul rollback. Qui l'INSERT e' storto, quindi il DELETE e' gia' stato
    eseguito quando SQLite si lamenta.
    """
    _costruisci_tutto()
    prima = _prezzi_in_tabella()
    assert prima, "servono dei prezzi da poter perdere"

    vero = universe._insert

    def _insert_storto(tabella, colonne):
        if tabella == "universe_mercato":
            return "INSERT INTO universe_mercato (symbol) VALUES (?, ?, ?, ?, ?)"
        return vero(tabella, colonne)

    monkeypatch.setattr(universe, "_insert", _insert_storto)
    with pytest.raises(sqlite3.OperationalError):
        universe.build_mercato(force=True)

    assert _prezzi_in_tabella() == prima, "un listino dimezzato sembrerebbe completo"


# --- le route ---------------------------------------------------------------

def test_le_route_dell_universo(client, derivazione_finta):
    """Elenco, stato e avvio: la costruzione non parte mai aprendo una pagina."""
    vuoto = client.get("/api/universe").get_json()
    assert vuoto["success"] is True
    assert vuoto["data"]["available"] is False
    assert vuoto["data"]["action"] == universe.ACTION_UNIVERSO_VUOTO

    _costruisci_tutto()

    elenco = client.get("/api/universe?sector=Technology").get_json()
    assert [t["symbol"] for t in elenco["data"]["titoli"]] == ["AAPL"]
    assert elenco["data"]["totale"] == 3

    stato = client.get("/api/universe/stato").get_json()
    assert stato["data"]["titoli"] == 3
    assert stato["data"]["anagrafica"]["costruita_il"] is not None
    assert stato["data"]["mercato"]["titoli"] == 2


def test_le_due_route_di_costruzione_sono_due(client, derivazione_finta):
    """Un pulsante solo vorrebbe dire pagare sempre anche la meta' cara."""
    anagrafica = client.post("/api/universe/anagrafica?force=1").get_json()
    assert anagrafica["success"] is True
    assert anagrafica["data"]["meta"] == "anagrafica"
    assert anagrafica["data"]["stop"].endswith(anagrafica["data"]["run_id"])
    assert _attendi_fine(anagrafica["data"]["run_id"])["status"] == registry.STATUS_DONE

    mercato = client.post("/api/universe/mercato?force=1").get_json()
    assert mercato["data"]["meta"] == "mercato"
    assert _attendi_fine(mercato["data"]["run_id"])["status"] == registry.STATUS_DONE

    assert derivazione_finta == {"anagrafica": 1, "mercato": 1}, \
        "ha ricostruito col finto, non col vero"


def test_un_limite_sbagliato_non_diventa_un_errore_del_server(client):
    """L'utente riceve il motivo, non uno stack trace (regola 16)."""
    risposta = client.get("/api/universe?limit=moltissimi")
    assert risposta.status_code == 400
    assert risposta.get_json()["error"].startswith("limit non e' un numero")


# --- i fondamentali di tutto l'universo ------------------------------------
#
# Il buco che chiudono: l'universo sapeva solo com'e' andato il prezzo, quindi
# lo scanner poteva cercare solo per prezzo, e i segnali che guardano i bilanci
# erano calcolabili solo su una lista venuta da fuori.

FONDAMENTALI_FINTI = [
    # AAPL: due trimestri, il secondo migliore, con la data di deposito vera.
    {"symbol": "AAPL", "report_date": "2026-03-31", "voce": "total_revenue",
     "valore": 100.0, "filing_date": "2026-05-02"},
    {"symbol": "AAPL", "report_date": "2026-03-31", "voce": "gross_profit",
     "valore": 30.0, "filing_date": "2026-05-02"},
    {"symbol": "AAPL", "report_date": "2026-06-30", "voce": "total_revenue",
     "valore": 130.0, "filing_date": "2026-08-01"},
    {"symbol": "AAPL", "report_date": "2026-06-30", "voce": "gross_profit",
     "valore": 52.0, "filing_date": "2026-08-01"},
    # ZOMB: un trimestre solo, e senza data di deposito.
    {"symbol": "ZOMB", "report_date": "2026-06-30", "voce": "total_revenue",
     "valore": 10.0, "filing_date": None},
]


def _scrivi_fondamentali(righe=None):
    """Riempie la tabella come farebbe la derivazione, senza toccare la rete."""

    frame = pd.DataFrame(righe if righe is not None else FONDAMENTALI_FINTI)
    return fondamentali._scrivi(frame)


def test_senza_derivazione_i_fondamentali_lo_dicono():
    """Regola 5: l'assenza si dichiara col motivo e con l'azione."""

    stato = fondamentali.stato()

    assert stato["available"] is False
    assert "mai stati derivati" in stato["reason"]
    assert "premi" in stato["action"]


def test_i_fondamentali_si_leggono_nella_forma_che_vuole_il_dominio():
    """La stessa forma che produce `prospetti.tabella()`: cosi' i segnali del
    rilevatore funzionano identici sul titolo letto uno a uno e su quello preso
    dalla tabella dell'universo."""
    _scrivi_fondamentali()

    voci = fondamentali.voci_di("aapl")

    assert voci["total_revenue"] == {"2026-03-31": 100.0, "2026-06-30": 130.0}
    assert voci["gross_profit"]["2026-06-30"] == 52.0
    assert fondamentali.voci_di("MAI-VISTO") == {}


def test_le_date_di_deposito_arrivano_solo_dove_ci_sono():
    """Dove mancano, chi calcola ricade sul ritardo prudente e lo dichiara: una
    data inventata sarebbe peggio di una mancante."""
    _scrivi_fondamentali()

    assert fondamentali.depositi_di("AAPL") == {
        "2026-03-31": ("2026-05-02", "filing_index"),
        "2026-06-30": ("2026-08-01", "filing_index"),
    }
    assert fondamentali.depositi_di("ZOMB") == {}


def test_lo_stato_dichiara_la_copertura_voce_per_voce():
    """Il margine lordo manca a migliaia di titoli — le banche non lo riportano
    — e un filtro sul margine li' sopra non torna vuoto: torna assente."""
    _scrivi_fondamentali()

    stato = fondamentali.stato()

    assert stato["available"] is True
    assert stato["titoli"] == 2
    assert stato["copertura"] == {"gross_profit": 1, "total_revenue": 2}
    assert stato["con_data_di_deposito"] == 4, "ZOMB non ha deposito"


def test_lo_scanner_puo_cercare_per_bilancio():
    """Il criterio nuovo: prima si poteva chiedere solo com'e' andato il prezzo."""
    _scrivi_fondamentali()

    misure = scanner._fondamentali("AAPL", None)

    assert misure["ricavi_qoq"] == pytest.approx(0.30)
    assert misure["margine_variazione"] == pytest.approx(0.10)
    assert misure["trimestri"] == 2


def test_un_criterio_di_bilancio_su_un_titolo_senza_bilanci_non_passa():
    """La stessa regola dei prezzi mancanti: un valore che manca non soddisfa
    nessuna soglia, e non e' un caso speciale."""
    _scrivi_fondamentali()

    misurato = scansione.misure([100.0] * 250, [1e6] * 250)
    misurato["fondamentali"] = scanner._fondamentali("ZOMB", None)

    soddisfa, _ = scansione.valuta(misurato, {"ricavi_qoq_minimo": 0.05})

    assert soddisfa is False, "un trimestre solo non fa un'accelerazione"


def test_il_taglio_a_una_data_passata_usa_le_date_di_deposito():
    """Il trimestre di giugno e' stato depositato il primo agosto: chi ricostruisce
    al 15 luglio non deve vederlo, o sono due settimane di futuro."""
    _scrivi_fondamentali()

    a_meta_luglio = scanner._fondamentali("AAPL", "2026-07-15")
    a_settembre = scanner._fondamentali("AAPL", "2026-09-15")

    assert a_meta_luglio["trimestri"] == 1, "a luglio era pubblico un trimestre solo"
    assert a_meta_luglio["ricavi_qoq"] is None
    assert a_settembre["trimestri"] == 2
    assert a_settembre["ricavi_qoq"] == pytest.approx(0.30)
