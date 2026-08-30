"""
test_blocco9.py — lo scanner: fermabile, e capace di dire perche'.
# feat: l'ultimo blocco che non dipende dalle analisi.

Il vecchio tradash aveva scanner che nessuno vedeva partire e che non si
potevano fermare, e che rispondevano con un elenco di titoli senza dire in base
a cosa. Qui la scansione e' un lavoro del registro, e ogni titolo trovato porta
la ragione per cui e' stato trovato.
"""
import threading

import pandas as pd
import pytest

from core import registry
from core.db import db_read, db_session
from data import defeatbeta, scanner
from domain import drawdown, scansione

TIMEOUT_S = 5.0


def _prezzi(valori: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "report_date": [f"2026-01-{i % 28 + 1:02d}" for i in range(len(valori))],
        "close": valori, "volume": [1_000_000.0] * len(valori),
    })


# --- il drawdown, che nel vecchio sistema era un servizio -------------------

def test_un_titolo_ai_massimi_non_e_in_drawdown():
    profilo = drawdown.profilo([100, 105, 110, 115])

    assert profilo["profondita_attuale"] == 0.0
    assert profilo["e_un_drawdown"] is False
    assert profilo["giorni_sotto_il_massimo"] == 0


def test_profondita_durata_e_recupero_si_misurano_dai_prezzi():
    """La risposta a "basato su cosa?", che nel vecchio sistema non c'era."""
    profilo = drawdown.profilo([100, 120, 90, 96, 102])

    assert profilo["profondita_attuale"] == pytest.approx(-0.15)
    assert profilo["profondita_massima"] == pytest.approx(-0.25)
    assert profilo["giorni_sotto_il_massimo"] == 3
    assert profilo["recupero_dal_fondo"] == pytest.approx(0.4)
    assert profilo["e_un_drawdown"] is True


def test_senza_abbastanza_prezzi_il_drawdown_manca_e_non_vale_zero():
    """Sono due letture molto diverse, e confonderle riempie uno scanner di
    titoli che non c'entrano niente."""
    assert drawdown.profilo([]) is None
    assert drawdown.profilo([100]) is None


# --- i criteri --------------------------------------------------------------

def test_un_criterio_su_una_misura_che_manca_non_passa():
    misurato = scansione.misure([100, 101, 102])      # troppo corta per un anno

    assert misurato["variazione_1a"] is None
    soddisfa, _ = scansione.valuta(misurato, {"variazione_1a_minima": 0.1})
    assert soddisfa is False


def test_ogni_titolo_trovato_porta_il_perche():
    misurato = scansione.misure([100, 120, 84, 96])

    soddisfa, perche = scansione.valuta(misurato, {"drawdown_minimo": 0.15,
                                                   "recupero_minimo": 0.3})

    assert soddisfa is True
    assert len(perche) == 2
    assert "sceso almeno" in perche[0]


def test_i_criteri_si_sommano_e_bastano_a_escludere():
    misurato = scansione.misure([100, 120, 84, 96])

    assert scansione.valuta(misurato, {"drawdown_minimo": 0.5})[0] is False


# --- la scansione, come lavoro ---------------------------------------------

@pytest.fixture
def universo_finto():
    with db_session() as conn:
        conn.executemany(
            "INSERT INTO universe (symbol, sector, market_cap, avg_volume_30d, built_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [("AAA", "Technology", 3e11, 5e6, "2026-08-30T00:00:00+00:00"),
             ("BBB", "Technology", 2e11, 5e6, "2026-08-30T00:00:00+00:00"),
             ("CCC", "Energy", 1e11, 5e6, "2026-08-30T00:00:00+00:00")],
        )


def _prezzi_finti(monkeypatch, per_simbolo: dict):
    def _prices(simbolo, run_id=None):
        frame = per_simbolo.get(simbolo)
        if frame is None:
            return defeatbeta.Lettura(frame=pd.DataFrame(), scope=simbolo, category="price",
                                      source="cache", available=False, reason="nessun prezzo")
        return defeatbeta.Lettura(frame=frame, scope=simbolo, category="price",
                                  source="cache", available=True, reason="finto")
    monkeypatch.setattr(defeatbeta, "prices", _prices)


def test_la_scansione_trova_e_spiega(universo_finto, monkeypatch):
    _prezzi_finti(monkeypatch, {
        "AAA": _prezzi([100, 120, 84, 96]),      # -20% dal massimo, recuperato
        "BBB": _prezzi([100, 101, 102, 103]),    # ai massimi
    })

    esito = scanner._esegui({"drawdown_minimo": 0.1}, {})

    assert esito["completata"] is True
    assert [t["symbol"] for t in esito["trovati"]] == ["AAA"]
    assert esito["trovati"][0]["perche"]
    assert esito["senza_dati"] == ["CCC"], "un simbolo senza prezzi non ferma il giro"


def test_i_filtri_dell_universo_riducono_i_candidati(universo_finto, monkeypatch):
    _prezzi_finti(monkeypatch, {})

    esito = scanner._esegui({"drawdown_minimo": 0.1}, {"sector": "Energy"})

    assert esito["totale"] == 1
    assert esito["senza_dati"] == ["CCC"]


def test_la_scansione_si_ferma_e_conserva_quello_che_aveva_trovato(universo_finto, monkeypatch):
    """Fermata a meta' e' meno di quanto chiesto, non niente."""
    partita = threading.Event()

    def _lente(simbolo, run_id=None):
        partita.set()
        threading.Event().wait(0.15)
        return defeatbeta.Lettura(frame=_prezzi([100, 120, 84, 96]), scope=simbolo,
                                  category="price", source="cache", available=True,
                                  reason="finto")

    monkeypatch.setattr(defeatbeta, "prices", _lente)

    run_id = scanner.avvia({"drawdown_minimo": 0.1}, {})
    assert partita.wait(TIMEOUT_S)
    registry.request_stop(run_id)

    scadenza = threading.Event()
    while not scadenza.wait(0.05):
        with db_read() as conn:
            riga = conn.execute("SELECT * FROM jobs WHERE run_id = ?", (run_id,)).fetchone()
        if riga["ended_at"]:
            break

    assert riga["status"] == registry.STATUS_STOPPED
    assert scanner.esito(run_id)["completata"] is False


# --- le route ---------------------------------------------------------------

def test_una_scansione_senza_criteri_viene_rifiutata(client):
    risposta = client.post("/api/scanner", json={"criteri": {}})

    assert risposta.status_code == 400
    assert "universo intero" in risposta.get_json()["error"]


def test_un_criterio_inventato_viene_nominato(client):
    risposta = client.post("/api/scanner", json={"criteri": {"fortuna": 1}})

    assert risposta.status_code == 400
    assert "fortuna" in risposta.get_json()["error"]


def test_l_esito_di_una_scansione_sconosciuta_lo_dice(client):
    risposta = client.get("/api/scanner/inventato")

    assert risposta.status_code == 404
    assert "ops/active" in risposta.get_json()["error"]
