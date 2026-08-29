"""
test_blocco2.py — la verifica del Blocco 2: l'universo si deriva, si vede, si ferma.
# feat: se questi test non passano, non si va al Blocco 3.

Il PIANO chiede una derivazione da `stock_profile`, senza JSON statici. Qui si
verifica quello e le tre cose che lo circondano: che il lavoro sia fermabile
davvero (non "in teoria"), che i titoli con caselle vuote entrino lo stesso
invece di sparire, e che l'universo mai costruito lo dica.

Il finto sta sotto cio' che si misura: si sostituisce la derivazione — cioe' la
query su DuckDB — e restano vere la scrittura in transazione, il registro dei
lavori, la freschezza, i filtri e le route.
"""
import threading

import pandas as pd
import pytest

import config
from core import freshness, registry
from core.db import db_read
from core.schema import GLOBAL_SCOPE
from data import defeatbeta, universe

# Un universo finto piccolo, ma con dentro i casi scomodi: una societa' non
# americana quotata negli USA, e un titolo a cui manca meta' dei dati.
UNIVERSO_FINTO = [
    {"symbol": "AAPL", "sector": "Technology", "industry": "Consumer Electronics",
     "company_country": "United States", "employees": 150000, "last_close": 319.7,
     "last_close_date": "2026-08-28", "avg_volume_30d": 48259040.0,
     "market_cap": 4.67e12},
    {"symbol": "BABA", "sector": "Consumer Cyclical", "industry": "Internet Retail",
     "company_country": "China", "employees": 132165, "last_close": 118.9,
     "last_close_date": "2026-08-28", "avg_volume_30d": 11934780.0,
     "market_cap": 2.85e11},
    {"symbol": "ZOMB", "sector": None, "industry": None, "company_country": None,
     "employees": None, "last_close": None, "last_close_date": None,
     "avg_volume_30d": None, "shares_outstanding": None, "market_cap": None},
]

TIMEOUT_S = 5.0


def _lettura_finta(records=None) -> defeatbeta.Lettura:
    """Un risultato di derivazione, nella forma che ritorna il punto unico."""
    frame = pd.DataFrame(records if records is not None else UNIVERSO_FINTO)
    return defeatbeta.Lettura(
        frame=frame, scope=GLOBAL_SCOPE, category=defeatbeta.CATEGORY_UNIVERSE,
        source="cache", available=not frame.empty,
        reason=f"{len(frame)} righe finte",
    )


@pytest.fixture
def derivazione_finta(monkeypatch):
    """Sostituisce la sola query, lasciando vero tutto il resto della catena."""
    chiamate = {"quante": 0}

    def _universo_finto(run_id=None):
        chiamate["quante"] += 1
        return _lettura_finta()

    monkeypatch.setattr(defeatbeta, "universe", _universo_finto)
    return chiamate


def _titoli_in_tabella() -> list[dict]:
    with db_read() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM universe ORDER BY symbol")]


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
    esito = universe.build()

    assert esito["costruito"] is True
    assert esito["titoli"] == len(UNIVERSO_FINTO)
    assert [t["symbol"] for t in _titoli_in_tabella()] == ["AAPL", "BABA", "ZOMB"]
    assert freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_UNIVERSE) is not None

    lavoro = _lavoro(esito["run_id"])
    assert lavoro["status"] == registry.STATUS_DONE
    assert lavoro["done"] == universe.PASSI_COSTRUZIONE


def test_una_seconda_costruzione_non_rifa_il_lavoro_e_dice_perche(derivazione_finta):
    """Il gate di freschezza si interroga PRIMA di andare in rete, non dopo."""
    universe.build()
    esito = universe.build()

    assert esito["costruito"] is False
    assert "fresco" in esito["motivo"]
    assert derivazione_finta["quante"] == 1, "la derivazione non doveva ripartire"
    assert "saltato" in _lavoro(esito["run_id"])["detail"], (
        "anche un lavoro saltato deve restare in cronologia col suo motivo"
    )


def test_force_ricostruisce_comunque(derivazione_finta):
    """L'utente puo' sempre scavalcare il gate, ma deve dirlo."""
    universe.build()
    esito = universe.build(force=True)

    assert esito["costruito"] is True
    assert derivazione_finta["quante"] == 2


# --- fermabile davvero ------------------------------------------------------

def test_la_costruzione_si_ferma_a_meta_e_resta_stopped(monkeypatch):
    """Lo Stop arriva fino al motore: registro -> sentinella -> interruzione.

    Il finto sostituisce l'interruzione di DuckDB, non la sentinella: cosi' il
    filo che si verifica e' quello vero, dal pulsante alla query.
    """
    partita = threading.Event()
    interruzione_chiesta = threading.Event()

    def _interrompi() -> bool:
        interruzione_chiesta.set()
        return True

    def _universo_lento(run_id=None):
        partita.set()
        assert interruzione_chiesta.wait(TIMEOUT_S), "la sentinella non ha chiesto lo stop"
        raise defeatbeta.DefeatbetaUnavailable("query interrotta")

    monkeypatch.setattr(defeatbeta, "interrupt", _interrompi)
    monkeypatch.setattr(defeatbeta, "universe", _universo_lento)

    run_id = universe.build_in_background()
    assert partita.wait(TIMEOUT_S), "la derivazione non e' mai partita"

    consegnato, motivo = registry.request_stop(run_id)
    assert consegnato is True and motivo is None

    assert _attendi_fine(run_id)["status"] == registry.STATUS_STOPPED
    assert _titoli_in_tabella() == [], "un lavoro fermato non deve lasciare mezzo universo"
    assert freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_UNIVERSE) is None


def test_un_guasto_del_provider_non_si_traveste_da_stop(monkeypatch):
    """Se nessuno ha premuto Stop, un errore resta un errore: il lavoro fallisce."""
    def _universo_rotto(run_id=None):
        raise defeatbeta.DefeatbetaUnavailable("il provider non risponde")

    monkeypatch.setattr(defeatbeta, "universe", _universo_rotto)

    with pytest.raises(defeatbeta.DefeatbetaUnavailable):
        universe.build()

    with db_read() as conn:
        lavoro = dict(conn.execute("SELECT * FROM jobs ORDER BY started_at DESC").fetchone())
    assert lavoro["status"] == registry.STATUS_FAILED


# --- le caselle vuote si dichiarano, non si nascondono ----------------------

def test_i_titoli_incompleti_entrano_lo_stesso(derivazione_finta):
    """Tenere solo le righe complete farebbe sparire in silenzio 2.636 titoli."""
    universe.build()

    zombie = next(t for t in _titoli_in_tabella() if t["symbol"] == "ZOMB")
    assert zombie["sector"] is None
    assert zombie["market_cap"] is None


def test_il_paese_non_restringe_l_universo(derivazione_finta):
    """`country` e' il paese della SOCIETA', non della borsa.

    Filtrare su 'United States' butterebbe via BABA e SHOP, che sono quotate
    negli USA: il perimetro americano ce l'ha gia' il dataset.
    """
    universe.build()
    assert "BABA" in [t["symbol"] for t in _titoli_in_tabella()]


def test_le_stringhe_vuote_sono_dati_assenti_non_dati_presenti(monkeypatch):
    """Il difetto era nostro, e faceva dichiarare una copertura migliore del vero.

    Nel profilo di Defeatbeta il settore manca 635 volte come NULL e **886 volte
    come stringa vuota**. Contando solo i NULL, la copertura risultava il doppio
    di quella reale: un buco silenzioso prodotto proprio dal codice che doveva
    dichiarare i buchi.
    """
    vuoti = [{"symbol": "VUOT", "sector": "   ", "industry": "",
              "company_country": "", "employees": None, "last_close": 1.0,
              "last_close_date": "2026-08-28", "avg_volume_30d": 10.0,
              "shares_outstanding": None, "market_cap": None}]
    monkeypatch.setattr(defeatbeta, "universe", lambda run_id=None: _lettura_finta(vuoti))

    universe.build()

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
    universe.build()
    capitalizzazione = universe.stato()["capitalizzazione"]

    assert capitalizzazione["non_derivabile"] == 1
    assert capitalizzazione["perche_mancano_le_azioni"] == 1
    assert capitalizzazione["perche_manca_il_prezzo"] == 1


def test_lo_stato_dichiara_la_copertura(derivazione_finta):
    """Regola 5: i buchi si contano e si mostrano, non si scoprono per caso."""
    universe.build()
    stato = universe.stato()

    assert stato["available"] is True
    assert stato["titoli"] == 3
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
    universe.build()

    assert [t["symbol"] for t in universe.rows(sector="Technology")] == ["AAPL"]
    assert [t["symbol"] for t in universe.rows(min_market_cap=1e12)] == ["AAPL"]
    assert [t["symbol"] for t in universe.rows(search="ba")] == ["BABA"]
    assert len(universe.rows(limit=1)) == 1

    with pytest.raises(ValueError):
        universe.rows(limit=config.UNIVERSE_PAGE_LIMIT_MAX + 1)


def test_i_titoli_senza_capitalizzazione_finiscono_in_fondo_non_in_cima(derivazione_finta):
    """Ordinare per capitalizzazione con dei NULL in mezzo li mette primi, se non si dice nulla."""
    universe.build()
    assert [t["symbol"] for t in universe.rows()] == ["AAPL", "BABA", "ZOMB"]


def test_la_scrittura_e_una_transazione_sola(derivazione_finta, monkeypatch):
    """Se la scrittura fallisce a meta', l'universo di prima resta intero."""
    universe.build()
    prima = _titoli_in_tabella()

    def _riga_rotta(record):
        raise RuntimeError("conversione fallita a meta'")

    monkeypatch.setattr(universe, "_riga", _riga_rotta)
    with pytest.raises(RuntimeError):
        universe.build(force=True)

    assert _titoli_in_tabella() == prima, "un universo dimezzato sembrerebbe completo"


# --- le route ---------------------------------------------------------------

def test_le_route_dell_universo(client, derivazione_finta):
    """Elenco, stato e avvio: la costruzione non parte mai aprendo una pagina."""
    vuoto = client.get("/api/universe").get_json()
    assert vuoto["success"] is True
    assert vuoto["data"]["available"] is False
    assert vuoto["data"]["action"] == universe.ACTION_UNIVERSO_VUOTO

    universe.build()

    elenco = client.get("/api/universe?sector=Technology").get_json()
    assert [t["symbol"] for t in elenco["data"]["titoli"]] == ["AAPL"]
    assert elenco["data"]["totale"] == 3

    stato = client.get("/api/universe/stato").get_json()
    assert stato["data"]["titoli"] == 3

    avvio = client.post("/api/universe/build?force=1").get_json()
    assert avvio["success"] is True
    assert avvio["data"]["stop"].endswith(avvio["data"]["run_id"])

    # Si aspetta la fine prima di uscire: il thread non deve sopravvivere al test.
    assert _attendi_fine(avvio["data"]["run_id"])["status"] == registry.STATUS_DONE
    assert derivazione_finta["quante"] == 2, "ha ricostruito col finto, non col vero"


def test_un_limite_sbagliato_non_diventa_un_errore_del_server(client):
    """L'utente riceve il motivo, non uno stack trace (regola 16)."""
    risposta = client.get("/api/universe?limit=moltissimi")
    assert risposta.status_code == 400
    assert risposta.get_json()["error"].startswith("limit non e' un numero")
