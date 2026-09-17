"""
test_blocco6.py — il grafico e il guscio della scheda titolo.
# feat: se questi test non passano, non si va al Blocco 7.

Il pezzo copiato dal vecchio tradash e' il motore a nodi, che li' funzionava:
qui si verifica che continui a funzionare e che le due trappole trovate
portandolo non tornino — il ciclo nell'albero dei source, e gli indicatori
calcolati sul solo intervallo mostrato.
"""
import json
import math
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


# --- il grafico a una data passata ------------------------------------------
#
# Il difetto che questi test impediscono e' sottile e invisibile a occhio: una
# media a 50 sedute calcolata su tutta la storia e poi TAGLIATA alla data
# passata ha gia' visto il mese dopo. Il grafico sembrerebbe identico, e i
# numeri sarebbero quelli di un veggente.

def _barre_finte(giorni: int, dal: date) -> list[dict]:
    """Le stesse barre che vede l'API, per poter rifare il calcolo qui."""
    return [{"timestamp": (dal + timedelta(days=i)).isoformat(),
             "open": 100.0, "high": 100.0, "low": 100.0,
             "close": 100.0 + i, "volume": 1e6}
            for i in range(giorni)]


def _prezzi_finti(monkeypatch, giorni: int, dal: date) -> None:
    """Sostituisce la lettura dei prezzi con una serie che sale di 1 al giorno."""
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({
            "report_date": [(dal + timedelta(days=i)).isoformat() for i in range(giorni)],
            "open": [100.0] * giorni, "high": [100.0] * giorni, "low": [100.0] * giorni,
            "close": [100.0 + i for i in range(giorni)], "volume": [1e6] * giorni,
        }),
        scope=s, category="price", source="cache", available=True, reason="finto"))


def test_col_grafico_a_una_data_passata_le_barre_si_fermano_li(client, monkeypatch):
    """Il taglio e' rigido: solo le sedute con data minore o uguale."""
    _prezzi_finti(monkeypatch, 400, date(2024, 1, 1))
    quando = "2024-06-30"

    corpo = client.get(f"/api/titolo/X/prezzi?intervallo=tutto&as_of={quando}").get_json()
    assert corpo["success"], corpo["error"]
    d = corpo["data"]

    assert d["as_of"] == quando
    assert d["ultima_seduta"] <= quando
    assert all(b["timestamp"] <= quando for b in d["barre"])


def test_le_serie_mostrate_sono_quelle_della_storia_troncata(client, monkeypatch):
    """L'invariante che conta: quello che vedi e' calcolato su cio' che c'era.

    Si verifica **contro il motore stesso** e non con una formula chiusa: la
    serie predefinita e' una EMA, e una formula sbagliata farebbe fallire il
    test per il motivo sbagliato.
    """
    giorni, dal = 400, date(2024, 1, 1)
    _prezzi_finti(monkeypatch, giorni, dal)
    quando = "2024-06-30"

    corpo = client.get(f"/api/titolo/X/prezzi?intervallo=tutto&as_of={quando}").get_json()
    assert corpo["success"], corpo["error"]
    dall_api = corpo["data"]["serie"]

    troncate = [b for b in _barre_finte(giorni, dal) if b["timestamp"] <= quando]
    attese = indicators.compute(troncate, indicators.DEFAULT_CONFIG)

    for nome, punti in attese.items():
        if not punti:
            continue
        assert dall_api[nome][-1]["v"] == pytest.approx(punti[-1]["v"]), nome


def test_tutti_gli_indicatori_guardano_solo_indietro():
    """La proprieta' su cui NON ci si appoggia, ma che e' bene sapere quando cade.

    Misurato il 17/09/2026 su tutti e dodici i kind: calcolare su tutta la
    storia e tagliare dopo, oppure troncare e poi calcolare, da' gli stessi
    identici valori. Sono tutti filtri causali.

    Per questo il grafico a una data passata mostra numeri giusti **comunque**,
    e per questo l'ordine del taglio in `api/titolo.py` non e' oggi un dettaglio
    di correttezza ma di costruzione.

    Il giorno in cui qualcuno aggiunge un indicatore che guarda l'intera serie —
    un percentile annuale, una normalizzazione sul massimo storico — questo test
    fallisce, ed e' il momento in cui quell'ordine diventa l'unica cosa che
    tiene onesto il point-in-time. Meglio scoprirlo qui che in pagina.
    """
    giorni, dal = 400, date(2024, 1, 1)
    quando = "2024-06-30"
    # Una serie NON lineare: su una lineare i numeri potrebbero coincidere per caso.
    barre = [{"timestamp": (dal + timedelta(days=i)).isoformat(),
              "open": 100 + math.sin(i / 7) * 10, "high": 105 + math.sin(i / 7) * 10,
              "low": 95 + math.sin(i / 7) * 10,
              "close": 100 + math.sin(i / 7) * 10 + i * 0.05,
              "volume": 1e6 + (i % 13) * 1e5}
             for i in range(giorni)]
    troncate = [b for b in barre if b["timestamp"] <= quando]

    nodi = []
    for kind in sorted(indicators.VALID_KINDS):
        for sorgente in ("price", "volume"):
            nodo = {"id": kind, "kind": kind, "source": sorgente, "enabled": True,
                    "params": {}, "style": {}}
            try:
                indicators.compute(barre[:60], {"nodes": [nodo]})
            except indicators.IndicatorConfigError:
                continue
            nodi.append(nodo)
            break

    assert len(nodi) == len(indicators.VALID_KINDS), "qualche kind non e' stato provato"

    intera = indicators.compute(barre, {"nodes": nodi})
    tronca = indicators.compute(troncate, {"nodes": nodi})

    non_causali = []
    for nome, punti in tronca.items():
        if not punti:
            continue
        ultimo = punti[-1]
        allo_stesso_istante = next((p["v"] for p in intera[nome] if p["t"] == ultimo["t"]), None)
        if allo_stesso_istante is None or abs(allo_stesso_istante - ultimo["v"]) > 1e-9:
            non_causali.append(nome)

    assert not non_causali, (
        f"questi indicatori cambiano se hanno visto il futuro: {non_causali}. "
        f"Da adesso il taglio prima del calcolo NON e' piu' una scelta di "
        f"costruzione: e' l'unica cosa che tiene onesto il grafico a una data "
        f"passata. Verificare che `api/titolo.py` lo faccia ancora."
    )


def test_la_finestra_dell_intervallo_segue_la_data_scelta(client, monkeypatch):
    """«Un anno» a una data passata e' l'anno PRIMA di quella data.

    Senza, chiedere un anno di grafico al 2024 darebbe una finestra che finisce
    nel 2026: vuota, e per un motivo che nessuno indovinerebbe guardandola.
    """
    _prezzi_finti(monkeypatch, 800, date(2023, 1, 1))
    quando = "2024-06-30"

    d = client.get(f"/api/titolo/X/prezzi?intervallo=1A&as_of={quando}").get_json()["data"]

    assert d["barre"], "la finestra non deve essere vuota"
    assert d["barre"][-1]["timestamp"] <= quando
    assert d["barre"][0]["timestamp"] >= "2023-06-30", "parte circa un anno prima"


def test_una_data_prima_della_prima_quotazione_lo_dice(client, monkeypatch):
    """Regola 5: non un grafico vuoto, un motivo."""
    _prezzi_finti(monkeypatch, 100, date(2024, 1, 1))

    risposta = client.get("/api/titolo/X/prezzi?as_of=2010-01-01")

    assert risposta.status_code == 404
    assert "prima quotazione" in risposta.get_json()["error"]


def test_senza_data_il_grafico_e_quello_di_oggi(client, monkeypatch):
    """Il campo si dichiara sempre, anche quando e' vuoto: un campo che compare
    solo a volte non si legge."""
    _prezzi_finti(monkeypatch, 100, date.today() - timedelta(days=99))

    d = client.get("/api/titolo/X/prezzi").get_json()["data"]

    assert "as_of" in d and d["as_of"] is None
