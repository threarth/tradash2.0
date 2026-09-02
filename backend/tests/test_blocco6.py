"""
test_blocco6.py — il grafico e il guscio della scheda titolo.
# feat: se questi test non passano, non si va al Blocco 7.

Il pezzo copiato dal vecchio tradash e' il motore a nodi, che li' funzionava:
qui si verifica che continui a funzionare e che le due trappole trovate
portandolo non tornino — il ciclo nell'albero dei source, e gli indicatori
calcolati sul solo intervallo mostrato.
"""
import json
from datetime import date, timedelta

import pandas as pd
import pytest

import config
from api import titolo
from core import tipi
from core.tipi import python_puro
from data import defeatbeta, grafici
from domain import indicators

# Una serie di barre lunga abbastanza da far esistere una media a 200 giorni.
SEDUTE = 400


def _barre(quante: int = SEDUTE) -> list[dict]:
    """Barre finte ma plausibili: date crescenti, prezzo che sale, volume costante.

    Le date devono crescere davvero: un primo tentativo le faceva ripetere ogni
    28 righe, e il taglio dell'intervallo finiva all'inizio della serie invece
    che alla fine — che e' esattamente cio' che succederebbe con dati veri
    disordinati.
    """
    inizio = date(2024, 1, 1)
    return [
        {"timestamp": (inizio + timedelta(days=i)).isoformat(), "open": 100 + i * 0.1,
         "high": 101 + i * 0.1, "low": 99 + i * 0.1, "close": 100 + i * 0.1,
         "volume": 1_000_000 + i}
        for i in range(quante)
    ]


# --- il motore a nodi -------------------------------------------------------

def test_la_configurazione_predefinita_produce_le_sue_serie():
    serie = indicators.compute(_barre(), indicators.DEFAULT_CONFIG)

    assert sorted(serie) == ["ema50", "sma200", "vol_main"]
    assert len(serie["ema50"]) == SEDUTE


def test_un_nodo_produce_anche_le_serie_secondarie():
    """MACD non e' una linea sola: senza segnale e istogramma non si legge."""
    serie = indicators.compute(_barre(), {"nodes": [
        {"id": "macd1", "kind": "macd", "source": "price", "enabled": True, "params": {}}
    ]})

    assert sorted(serie) == ["macd1", "macd1:hist", "macd1:signal"]


def test_un_ciclo_nei_source_viene_rifiutato():
    """Un nodo figlio di se stesso girerebbe a vuoto invece di dirlo."""
    with pytest.raises(indicators.IndicatorConfigError, match="ciclo"):
        indicators.compute(_barre(), {"nodes": [
            {"id": "a", "kind": "ema", "source": "b", "enabled": True, "params": {}},
            {"id": "b", "kind": "ema", "source": "a", "enabled": True, "params": {}},
        ]})


def test_una_media_puo_stare_sopra_un_altro_indicatore():
    """E' il senso del modello a nodi: la media del volume, non solo del prezzo."""
    serie = indicators.compute(_barre(), {"nodes": [
        {"id": "vol_main", "kind": "volume", "source": "volume", "enabled": True, "params": {}},
        {"id": "vol_ma", "kind": "sma", "source": "vol_main", "enabled": True,
         "params": {"period": 20}},
    ]})

    assert "vol_ma" in serie
    assert serie["vol_ma"][-1]["v"] is not None


def test_validare_non_richiede_le_barre():
    """Serve a chi SALVA una configurazione: `compute` su zero barre non direbbe niente."""
    assert indicators.compute([], {"nodes": [{"id": "a", "kind": "ema", "source": "a",
                                              "enabled": True, "params": {}}]} ) == {}

    with pytest.raises(indicators.IndicatorConfigError):
        indicators.valida({"nodes": [{"id": "a", "kind": "ema", "source": "a",
                                      "enabled": True, "params": {}}]})


# --- la trappola dell'intervallo -------------------------------------------

def test_gli_indicatori_vedono_il_passato_che_non_si_mostra():
    """Il difetto trovato dal vivo: a un mese di grafico, l'EMA50 era calcolata
    su ventidue sedute e chiamata "media a 50 giorni".

    Le medie mobili hanno bisogno del passato che sta fuori dall'inquadratura:
    si calcola su tutto e si taglia dopo.
    """
    tutte = _barre()
    serie = indicators.compute(tutte, indicators.DEFAULT_CONFIG)

    visibili, tagliate = titolo._taglia(tutte, serie, tutte[-22]["timestamp"])

    assert len(tagliate["sma200"]) == len(visibili)
    assert all(p["v"] is not None for p in tagliate["sma200"]), (
        "una media a 200 giorni sulle ultime 22 sedute non esisterebbe: "
        "questi valori ci sono solo perche' il calcolo ha visto tutta la storia"
    )


def test_barre_e_serie_restano_allineate():
    """Tagliarle con due criteri diversi le sfaserebbe di un giorno in silenzio."""
    tutte = _barre()
    serie = indicators.compute(tutte, indicators.DEFAULT_CONFIG)

    visibili, tagliate = titolo._taglia(tutte, serie, tutte[100]["timestamp"])

    assert visibili[0]["timestamp"] == tutte[100]["timestamp"]
    for chiave, punti in tagliate.items():
        assert len(punti) == len(visibili), f"{chiave} non e' allineata alle barre"


# --- le impostazioni per titolo --------------------------------------------

def test_le_impostazioni_sono_per_titolo_con_una_predefinita():
    assert grafici.configurazione("AAPL") == indicators.DEFAULT_CONFIG

    mia = {"nodes": [{"id": "rsi14", "kind": "rsi", "source": "price",
                      "enabled": True, "params": {"period": 14}}]}
    grafici.imposta("AAPL", mia)

    assert grafici.configurazione("AAPL") == mia
    assert grafici.configurazione("MSFT") == indicators.DEFAULT_CONFIG, "non e' di tutti"

    assert grafici.dimentica("AAPL") is True
    assert grafici.configurazione("AAPL") == indicators.DEFAULT_CONFIG


def test_una_configurazione_rotta_non_entra_nel_file():
    """Salvata, romperebbe il grafico a ogni apertura invece che una volta sola."""
    with pytest.raises(grafici.GraficiError, match="non valida"):
        grafici.imposta("AAPL", {"nodes": [{"id": "a", "kind": "inventato",
                                            "source": "price", "enabled": True, "params": {}}]})

    assert not config.GRAFICI_PATH.exists() or grafici.configurazione("AAPL") == \
        indicators.DEFAULT_CONFIG


# --- le route ---------------------------------------------------------------

def test_la_scheda_dichiara_le_sezioni_che_non_ci_sono_ancora(client, monkeypatch):
    """Una sezione futura non sparisce: dice quale blocco la portera'."""
    monkeypatch.setattr(defeatbeta, "profile", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame([{"sector": "Technology", "industry": "Semiconductors",
                             "country": "United States", "long_business_summary": "fa chip",
                             "full_time_employees": 30000, "web_site": "https://x.example",
                             "city": "Santa Clara"}]),
        scope="NVDA", category="profile", source="cache", available=True, reason="1 riga",
    ))

    risposta = client.get("/api/titolo/NVDA").get_json()["data"]

    assert risposta["profilo"]["sector"] == "Technology"
    assert risposta["profilo"]["full_time_employees"] == 30000
    # L'elenco adesso e' vuoto: le sezioni che aspettavano sono arrivate. La
    # regola pero' vale per la prossima, e questo test la difende.
    for nome, sezione in risposta["sezioni_future"].items():
        assert sezione["available"] is False, nome
        assert sezione["reason"] and sezione["action"], (
            f"{nome} dichiara di mancare ma non dice perche' ne' cosa aspettare")
        assert "blocco" in sezione["action"]


def test_un_intervallo_inventato_elenca_quelli_veri(client):
    risposta = client.get("/api/titolo/NVDA/prezzi?intervallo=sempre")

    assert risposta.status_code == 400
    assert "1M" in risposta.get_json()["error"]


# --- i quattro modi in cui i dati dicono «non c'e'» -------------------------

def test_i_due_assenti_di_pandas_diventano_none():
    """Trovati dal vivo leggendo i dirigenti di NVDA, dove eta' e compenso
    mancano per sette righe su dieci.

    `pandas.NA` non e' un float, non ha `.item()` ne' `.isoformat()`: passava
    indenne fino a `json.dumps`, che si e' fermato — dopo che due fasi
    dell'analisi qualitativa erano gia' state pagate.
    """
    assert python_puro(pd.NA) is None
    assert python_puro(pd.NaT) is None
    assert json.dumps({"eta": python_puro(pd.NA)}) == '{"eta": null}'


def test_una_data_mancante_non_diventa_la_stringa_NaT():
    """Il difetto peggiore dei due, perche' non si fermava: `NaT.isoformat()`
    restituisce "NaT", e quel testo finiva dentro un referto dove nessuno
    l'avrebbe riconosciuto per un dato mancante."""
    assert pd.NaT.isoformat() == "NaT", "e' proprio quello che fa pandas"
    assert python_puro(pd.NaT) is None, "e proprio per questo si controlla prima"


def test_i_quattro_assenti_si_riconoscono_tutti():
    for valore in (None, float("nan"), pd.NA, pd.NaT):
        assert tipi.manca(valore) is True, valore
    for valore in (0, 0.0, "", "x", False):
        assert tipi.manca(valore) is False, valore


# --- le variazioni per periodo, in cima alla scheda ------------------------

def test_le_variazioni_arrivano_per_ogni_intervallo(client, monkeypatch):
    """Costano zero — i prezzi si leggono gia' tutti — e servono a rispondere a
    «e sul trimestre?» senza ricaricare la pagina."""
    giorni = 400
    inizio = date.today() - timedelta(days=giorni - 1)
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({
            "report_date": [(inizio + timedelta(days=i)).isoformat() for i in range(giorni)],
            "open": [100.0] * giorni, "high": [100.0] * giorni,
            "low": [100.0] * giorni, "close": [100.0 + i for i in range(giorni)],
            "volume": [1e6] * giorni,
        }),
        scope=s, category="price", source="cache", available=True, reason="finto"))

    d = client.get("/api/titolo/X/prezzi?intervallo=1A").get_json()["data"]

    assert d["ultimo_prezzo"] == 100.0 + giorni - 1
    assert set(d["variazioni"]) == set(config.INTERVALLI_GRAFICO)
    for nome, v in d["variazioni"].items():
        assert "da" in v and "sedute" in v, nome


def test_un_intervallo_piu_lungo_della_storia_non_vale_zero(client, monkeypatch):
    """Un titolo quotato da otto mesi non ha fatto lo 0% in cinque anni."""
    giorni = 60
    # La storia deve arrivare fino a OGGI: con dati vecchi di un mese anche la
    # finestra a un mese sarebbe vuota, ed e' un caso diverso da quello provato.
    inizio = date.today() - timedelta(days=giorni - 1)
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({
            "report_date": [(inizio + timedelta(days=i)).isoformat() for i in range(giorni)],
            "open": [10.0] * giorni, "high": [10.0] * giorni, "low": [10.0] * giorni,
            "close": [10.0 + i for i in range(giorni)], "volume": [1e6] * giorni,
        }),
        scope=s, category="price", source="cache", available=True, reason="finto"))

    d = client.get("/api/titolo/X/prezzi").get_json()["data"]

    assert d["variazioni"]["5A"]["variazione"] is None
    assert "non copre" in d["variazioni"]["5A"]["reason"]
    assert d["variazioni"]["1M"]["variazione"] is not None, "il mese invece c'e'"
