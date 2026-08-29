"""
test_blocco1.py — la verifica del Blocco 1, scritta accanto al codice che la deve passare.
# feat: se questi test non passano, non si va al Blocco 2.

La verifica dichiarata nel PIANO.md e' una frase sola: "leggere due volte lo
stesso dato produce due righe di log, la seconda con `from_cache=true`". Qui e'
spezzata nei suoi pezzi, e attorno le stanno le altre regole che il modulo deve
rispettare: un simbolo rotto non ferma il gruppo, l'assenza porta un motivo, e
la libreria non viene mai importata a livello di modulo.

Il finto sta SOTTO cio' che si misura: si sostituisce `_esegui`, cioe' il punto
in cui DuckDB parla con la rete, e tutto quello che sta sopra — registro,
provenienza, freschezza, forma del risultato — e' codice vero. Serve anche a
chiudere un buco misurato: la rete spenta a livello di socket non ferma DuckDB,
che apre le connessioni in C++.
"""
import ast
from pathlib import Path

import pandas as pd
import pytest

import config
from core import calls, freshness, registry
from core.db import db_read
from data import defeatbeta

# Un simbolo qualsiasi, purche' ben formato: nessun test qui esce davvero.
SIMBOLO = "AAPL"

# Quante richieste HTTP finge di aver fatto una lettura andata in rete.
RICHIESTE_DI_RETE = 3
NESSUNA_RICHIESTA = 0


def _righe_di_log() -> list[dict]:
    """Il registro delle chiamate, dalla piu' vecchia alla piu' recente."""
    with db_read() as conn:
        righe = conn.execute("SELECT * FROM calls ORDER BY id").fetchall()
    return [dict(r) for r in righe]


def _frame_finto(righe: int = 1) -> pd.DataFrame:
    """Un risultato di query plausibile, senza toccare nulla di esterno."""
    return pd.DataFrame({"symbol": [SIMBOLO] * righe, "valore": list(range(righe))})


@pytest.fixture
def rete_finta(monkeypatch):
    """Sostituisce i due punti che parlano col mondo, lasciando vero tutto il resto.

    Ritorna una funzione con cui il test decide, lettura per lettura, quante
    richieste HTTP sono state fatte e cosa e' tornato.
    """
    copione: dict = {"esiti": [], "sql_visti": [], "parametri_visti": []}

    def _prepara_finto(table, extra):
        return f"SELECT * FROM '<{table}>' WHERE symbol = ? {extra}".strip()

    def _esegui_finto(sql, parametri):
        copione["sql_visti"].append(sql)
        copione["parametri_visti"].append(parametri)
        if not copione["esiti"]:
            raise AssertionError("lettura non prevista dal test")
        frame, richieste = copione["esiti"].pop(0)
        if isinstance(frame, Exception):
            raise frame
        return frame, richieste

    monkeypatch.setattr(defeatbeta, "_prepara", _prepara_finto)
    monkeypatch.setattr(defeatbeta, "_esegui", _esegui_finto)
    return copione


# --- la verifica del PIANO -------------------------------------------------

def test_due_letture_dello_stesso_dato_producono_due_righe_la_seconda_da_cache(rete_finta):
    """La frase del PIANO, verificata: due righe, la seconda con provenienza cache."""
    rete_finta["esiti"] = [
        (_frame_finto(), RICHIESTE_DI_RETE),   # la prima volta i byte non c'erano
        (_frame_finto(), NESSUNA_RICHIESTA),   # la seconda erano gia' su disco
    ]

    prima = defeatbeta.profile(SIMBOLO)
    seconda = defeatbeta.profile(SIMBOLO)

    righe = _righe_di_log()
    assert len(righe) == 2, (
        "ogni lettura deve lasciare la sua riga, anche quella servita dalla cache"
    )
    assert righe[0]["source"] == calls.SOURCE_NETWORK
    assert righe[1]["source"] == calls.SOURCE_CACHE
    assert prima.source == calls.SOURCE_NETWORK
    assert seconda.source == calls.SOURCE_CACHE
    assert righe[0]["provider"] == defeatbeta.PROVIDER_NAME
    assert righe[0]["endpoint"] == defeatbeta.TABLE_PROFILE
    assert righe[0]["scope"] == SIMBOLO


def test_la_provenienza_e_il_numero_di_richieste_http_non_una_stima(rete_finta):
    """Zero richieste significa cache anche se la query e' stata lenta.

    E' la differenza fra misurare e dedurre: il vecchio sistema aveva un log
    che mostrava solo la rete, e "arrivato dalla rete" o "era in cache" non si
    poteva distinguere.
    """
    rete_finta["esiti"] = [(_frame_finto(), NESSUNA_RICHIESTA)]
    lettura = defeatbeta.prices(SIMBOLO)
    assert lettura.source == calls.SOURCE_CACHE

    rete_finta["esiti"] = [(_frame_finto(), 1)]
    assert defeatbeta.prices(SIMBOLO).source == calls.SOURCE_NETWORK


def test_la_freschezza_si_marca_solo_quando_si_esce_davvero_in_rete(rete_finta):
    """La data di freschezza e' quando il dato e' stato PRESO, non riletto."""
    assert freshness.age_seconds(SIMBOLO, "price") is None

    rete_finta["esiti"] = [(_frame_finto(), NESSUNA_RICHIESTA)]
    defeatbeta.prices(SIMBOLO)
    assert freshness.age_seconds(SIMBOLO, "price") is None, (
        "una lettura servita dalla cache non ha preso niente di nuovo"
    )

    rete_finta["esiti"] = [(_frame_finto(), RICHIESTE_DI_RETE)]
    defeatbeta.prices(SIMBOLO)
    assert freshness.age_seconds(SIMBOLO, "price") is not None


# --- regola 4: un simbolo rotto si isola, non frena il gruppo ---------------

def test_un_simbolo_assente_non_solleva_e_dichiara_il_motivo(rete_finta):
    """Zero righe non e' un guasto del provider: e' un titolo che non c'e'."""
    rete_finta["esiti"] = [(pd.DataFrame(), RICHIESTE_DI_RETE)]

    lettura = defeatbeta.profile("ZZQQ")

    assert lettura.available is False
    assert "ZZQQ" in lettura.reason
    assert lettura.action == defeatbeta.ACTION_SIMBOLO_ASSENTE
    assert len(_righe_di_log()) == 1, "anche una lettura a vuoto e' una lettura"


def test_il_provider_rotto_solleva_e_lascia_la_riga_di_errore(rete_finta):
    """Un guasto del provider e' l'altra meta' della regola 4: il giro si ferma."""
    rete_finta["esiti"] = [(OSError("connessione rifiutata"), 0)]

    with pytest.raises(defeatbeta.DefeatbetaUnavailable):
        defeatbeta.profile(SIMBOLO)

    righe = _righe_di_log()
    assert len(righe) == 1
    assert righe[0]["status"] == calls.STATUS_ERROR
    assert "DefeatbetaUnavailable" in righe[0]["error_msg"]


def test_un_simbolo_malformato_non_arriva_mai_alla_query(rete_finta):
    """Cio' che non ha la forma di un ticker si ferma prima del motore."""
    rete_finta["esiti"] = []   # se qualcosa provasse a leggere, il finto solleva

    lettura = defeatbeta.profile("robaccia'; DROP TABLE calls; --")

    assert lettura.available is False
    assert lettura.action == defeatbeta.ACTION_SIMBOLO_MALFORMATO
    assert rete_finta["sql_visti"] == []


# --- la forma della query --------------------------------------------------

def test_il_simbolo_viaggia_come_parametro_non_dentro_la_query(rete_finta):
    """Regola 12: mai concatenare. Il simbolo sta nei parametri, non nel testo."""
    rete_finta["esiti"] = [(_frame_finto(), NESSUNA_RICHIESTA)]

    defeatbeta.profile("aapl")

    sql = rete_finta["sql_visti"][0]
    assert "?" in sql and SIMBOLO not in sql
    assert rete_finta["parametri_visti"][0] == [SIMBOLO], "e il simbolo arriva normalizzato"


def test_il_tetto_delle_notizie_e_obbligatorio_e_controllato(rete_finta):
    """La tabella delle news pesa 1,1 GB: una lettura senza tetto non si fa."""
    rete_finta["esiti"] = [(_frame_finto(), NESSUNA_RICHIESTA)]
    defeatbeta.news(SIMBOLO, limit=10)
    assert rete_finta["parametri_visti"][0] == [SIMBOLO, 10]

    with pytest.raises(ValueError):
        defeatbeta.news(SIMBOLO, limit=config.DEFEATBETA_NEWS_LIMIT_MAX + 1)
    with pytest.raises(ValueError):
        defeatbeta.news(SIMBOLO, limit=0)


# --- nessun lettore sfugge al registro -------------------------------------

def test_ogni_lettore_del_blocco_passa_dal_registro(rete_finta):
    """Sei lettori, sei righe di log, ognuna col nome della sua tabella."""
    lettori = [
        (defeatbeta.profile, defeatbeta.TABLE_PROFILE),
        (defeatbeta.prices, defeatbeta.TABLE_PRICES),
        (defeatbeta.statements, defeatbeta.TABLE_STATEMENT),
        (defeatbeta.earning_calendar, defeatbeta.TABLE_EARNING_CALENDAR),
        (defeatbeta.sec_filings, defeatbeta.TABLE_SEC_FILING),
        (defeatbeta.news, defeatbeta.TABLE_NEWS),
    ]
    rete_finta["esiti"] = [(_frame_finto(), NESSUNA_RICHIESTA)] * len(lettori)

    for lettore, _ in lettori:
        lettore(SIMBOLO)

    registrati = [r["endpoint"] for r in _righe_di_log()]
    assert registrati == [tabella for _, tabella in lettori]


def test_nessuna_riga_di_log_resta_senza_provenienza(rete_finta):
    """`undeclared` e' la spia di un percorso che non ha dichiarato da dove legge."""
    rete_finta["esiti"] = [(_frame_finto(), RICHIESTE_DI_RETE)]
    defeatbeta.statements(SIMBOLO)
    assert calls.summary().get(calls.SOURCE_UNDECLARED, 0) == 0


def test_una_lettura_si_puo_attribuire_al_lavoro_che_l_ha_chiesta(rete_finta):
    """Le chiamate di un batch devono ritrovarsi tutte sotto il suo run_id."""
    rete_finta["esiti"] = [(_frame_finto(), NESSUNA_RICHIESTA)]
    with registry.job("prova", "lettura dentro un lavoro") as lavoro:
        defeatbeta.profile(SIMBOLO, run_id=lavoro.run_id)
        atteso = lavoro.run_id

    assert [r["run_id"] for r in _righe_di_log()] == [atteso]


# --- le categorie di freschezza esistono davvero ---------------------------

def test_ogni_tabella_ha_una_categoria_con_un_ttl_dichiarato():
    """Una categoria non dichiarata prende il TTL cortissimo e nessuno se ne accorge."""
    for tabella, categoria in defeatbeta.CATEGORIA_PER_TABELLA.items():
        assert categoria in config.FRESHNESS_TTL_S, (
            f"la tabella {tabella} usa la categoria '{categoria}', che non ha un TTL in config"
        )


# --- la libreria non si importa a livello di modulo ------------------------

def test_la_libreria_non_e_importata_a_livello_di_modulo():
    """Il buco che questo test chiude: la rete spenta sui socket non ferma DuckDB.

    DuckDB apre le connessioni in C++, senza passare dal modulo `socket` di
    Python: la difesa del conftest non lo vede. Qui la difesa e' un'altra e si
    verifica sul sorgente — se `defeatbeta_api` non viene importato in cima al
    file, in una suite senza rete non c'e' proprio il motore che potrebbe uscire.
    E vale anche in uso reale: e' la regola 2, nessun lavoro all'avvio.
    """
    sorgente = Path(defeatbeta.__file__).read_text(encoding="utf-8")
    albero = ast.parse(sorgente)

    importati_in_cima = [
        nome.name
        for nodo in albero.body
        if isinstance(nodo, ast.Import | ast.ImportFrom)
        for nome in nodo.names
    ] + [
        nodo.module
        for nodo in albero.body
        if isinstance(nodo, ast.ImportFrom) and nodo.module
    ]

    assert not any("defeatbeta_api" in str(nome) for nome in importati_in_cima), (
        "importare defeatbeta_api in cima al file fa tre chiamate di rete "
        "all'avvio dell'applicazione"
    )


# --- la lettura vera, esclusa dai giri normali -----------------------------

@pytest.mark.network
def test_lettura_vera_da_defeatbeta():
    """La verifica dal vivo: per i dati veri il finto non basta.

    Gira solo con `pytest -m network`. Legge due volte il profilo di un titolo
    reale e controlla che la seconda sia servita dalla cache dei byte.
    """
    prima = defeatbeta.profile(SIMBOLO)
    assert prima.available is True, prima.reason
    assert prima.frame["sector"].iloc[0]

    seconda = defeatbeta.profile(SIMBOLO)
    assert seconda.available is True
    assert seconda.source == calls.SOURCE_CACHE, (
        "la seconda lettura dello stesso dato non deve uscire in rete"
    )

    profili = [r for r in _righe_di_log() if r["endpoint"] == defeatbeta.TABLE_PROFILE]
    provenienze = [r["source"] for r in profili]
    assert provenienze == [calls.SOURCE_NETWORK, calls.SOURCE_CACHE]
