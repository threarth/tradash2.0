"""
test_blocco9.py — lo scanner: fermabile, e capace di dire perche'.
# feat: l'ultimo blocco che non dipende dalle analisi.

Il vecchio tradash aveva scanner che nessuno vedeva partire e che non si
potevano fermare, e che rispondevano con un elenco di titoli senza dire in base
a cosa. Qui la scansione e' un lavoro del registro, e ogni titolo trovato porta
la ragione per cui e' stato trovato.
"""
import json
import threading
import time
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

import config
from core import registry
from core.db import db_read, db_session
from data import defeatbeta, forward, scanner, verdetto
from domain import dcf, drawdown, rischio, scansione, simulatore

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
    proseguire = threading.Event()

    def _lente(simbolo, run_id=None):
        # Il primo simbolo dice di essere partito e poi ASPETTA: senza questo il
        # giro poteva finire prima che lo stop arrivasse, e il test falliva una
        # volta ogni cinque circa. Una pausa fissa e' una scommessa sul carico
        # della macchina; questa e' una sincronizzazione.
        partita.set()
        assert proseguire.wait(TIMEOUT_S), "lo stop non e' mai stato chiesto"
        return defeatbeta.Lettura(frame=_prezzi([100, 120, 84, 96]), scope=simbolo,
                                  category="price", source="cache", available=True,
                                  reason="finto")

    monkeypatch.setattr(defeatbeta, "prices", _lente)

    run_id = scanner.avvia({"drawdown_minimo": 0.1}, {})
    assert partita.wait(TIMEOUT_S), "la scansione non e' partita"
    registry.request_stop(run_id)
    proseguire.set()

    scadenza = time.monotonic() + TIMEOUT_S
    riga = None
    while time.monotonic() < scadenza:
        with db_read() as conn:
            riga = conn.execute("SELECT * FROM jobs WHERE run_id = ?", (run_id,)).fetchone()
        if riga["ended_at"]:
            break
        threading.Event().wait(0.02)

    assert riga is not None and riga["ended_at"], "il lavoro non si e' chiuso in tempo"

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


# --- il DCF, e quanto dipende da cio' che si assume -------------------------
#
# Le cifre qui sotto sono quelle vere di NVDA al 28/08/2026, prese dal DCF di
# Defeatbeta. Servono a una cosa sola: verificare che il nostro conto e quello
# della libreria diano lo STESSO numero. La griglia di sensibilita' e la
# crescita implicita le calcoliamo noi, e valgono solo se la formula e' la sua.

NVDA_INGRESSI = {
    "base_fcf": 119076000000.0,
    "crescita_vicina": 0.2,
    "crescita_terminale": 0.035493374717919295,
    "sconto": 0.2402416970804019,
    "cassa": 80572000000.0,
    "debito": 12348000000.0,
    "azioni": 24147000000.0,
}

NVDA_PREZZO_EQUO_LIBRERIA = 52.58542482851448
NVDA_VALORE_IMPRESA_LIBRERIA = 1201556253334.1392
NVDA_PREZZO_DI_MERCATO = 217.55


def test_il_nostro_dcf_da_lo_stesso_numero_della_libreria():
    """Se divergesse, la griglia descriverebbe un prezzo diverso da quello mostrato."""
    calcolo = dcf.prezzo_equo(NVDA_INGRESSI)

    assert calcolo["prezzo_equo"] == pytest.approx(NVDA_PREZZO_EQUO_LIBRERIA, abs=1e-6)
    assert calcolo["valore_impresa"] == pytest.approx(NVDA_VALORE_IMPRESA_LIBRERIA, rel=1e-12)


def test_gli_anni_dal_sesto_scendono_per_gradi_uguali():
    """Non e' una scelta nostra: e' l'interpolazione lineare della libreria."""
    proiettati = dcf.flussi(100.0, 0.20, 0.00)

    crescite = [proiettati[i] / proiettati[i - 1] - 1 for i in range(1, len(proiettati))]
    assert crescite[:4] == pytest.approx([0.20] * 4)
    assert crescite[4:] == pytest.approx([0.16, 0.12, 0.08, 0.04, 0.00], abs=1e-9)


def test_uno_sconto_che_non_supera_la_crescita_terminale_non_da_un_valore():
    """La formula di Gordon li' divide per zero o per un negativo: il risultato
    non sarebbe un valore alto, sarebbe un valore senza senso."""
    assert dcf.valore_terminale(100.0, 0.05, 0.05) is None
    assert dcf.prezzo_equo({**NVDA_INGRESSI, "sconto": 0.02}) is None


def test_lo_scostamento_si_misura_sul_prezzo_di_mercato():
    """La libreria divide per il prezzo equo, e il suo -3,14 su NVDA si legge
    come «sopravvalutata del 314%», che non e' quello che dice."""
    scarto = dcf.scostamento(NVDA_PREZZO_EQUO_LIBRERIA, NVDA_PREZZO_DI_MERCATO)

    assert scarto == pytest.approx(-0.7583, abs=1e-4)
    assert dcf.scostamento(50.0, 0) is None


def test_la_crescita_implicita_dice_cosa_dovrebbe_fare_l_azienda():
    """La domanda utile non e' «quanto e' caro» ma «cosa deve succedere»."""
    implicita = dcf.crescita_implicita(NVDA_INGRESSI, NVDA_PREZZO_DI_MERCATO)

    assert implicita == pytest.approx(0.5555, abs=1e-3)
    verifica = dcf.prezzo_equo({**NVDA_INGRESSI, "crescita_vicina": implicita})
    assert verifica["prezzo_equo"] >= NVDA_PREZZO_DI_MERCATO


def test_se_nemmeno_la_crescita_massima_basta_lo_dice():
    """Un None qui e' una risposta: il prezzo non si spiega con la sola crescita."""
    caro = dcf.crescita_implicita(NVDA_INGRESSI, prezzo_di_mercato=100_000.0)

    assert caro is None


def test_la_griglia_mostra_che_il_numero_e_un_opinione():
    """Cinque punti di crescita in piu' spostano il prezzo equo di decine di punti."""
    griglia = dcf.sensibilita(NVDA_INGRESSI, (0.10, 0.20), (0.20, 0.25))

    assert len(griglia) == 4
    prezzi = {(v["crescita_vicina"], v["sconto"]): v["prezzo_equo"] for v in griglia}
    assert prezzi[(0.2, 0.2)] > prezzi[(0.1, 0.2)], "piu' crescita, piu' valore"
    assert prezzi[(0.2, 0.25)] < prezzi[(0.2, 0.2)], "piu' sconto, meno valore"


def test_il_forward_si_ferma_se_il_dcf_non_c_e(monkeypatch):
    monkeypatch.setattr(defeatbeta, "dcf", lambda s, run_id=None: defeatbeta.Dato(
        dato=None, scope=s, category="dcf", source="cache", available=False,
        reason="bilanci insufficienti"))

    with pytest.raises(forward.AnalisiError, match="bilanci insufficienti"):
        forward.misure("XYZ", None)


def test_un_dcf_a_pezzi_non_diventa_un_prezzo_a_pezzi(monkeypatch):
    """Meglio nessun prezzo equo che uno calcolato sugli ingressi che c'erano."""
    monkeypatch.setattr(defeatbeta, "dcf", lambda s, run_id=None: defeatbeta.Dato(
        dato={"dcf_template": {"base_fcf": 1.0, "growth_rate_1_5y": 0.1},
              "dcf_value": {}},
        scope=s, category="dcf", source="cache", available=True, reason="finto"))

    with pytest.raises(forward.AnalisiError, match="incompleto"):
        forward.misure("XYZ", None)


def test_il_forward_non_propaga_il_consiglio_della_libreria(monkeypatch):
    """La libreria scrive «Buy» o «Sell» in un campo. Accanto a un'analisi
    sembrerebbe la sua conclusione."""
    monkeypatch.setattr(defeatbeta, "dcf", lambda s, run_id=None: defeatbeta.Dato(
        dato={"dcf_template": {"base_fcf": NVDA_INGRESSI["base_fcf"],
                               "growth_rate_1_5y": 0.2,
                               "growth_rate_terminal": NVDA_INGRESSI["crescita_terminale"],
                               "discount_rate": NVDA_INGRESSI["sconto"]},
              "dcf_value": {"cash": NVDA_INGRESSI["cassa"],
                            "total_debt": NVDA_INGRESSI["debito"],
                            "shares_outstanding": NVDA_INGRESSI["azioni"],
                            "fair_price": NVDA_PREZZO_EQUO_LIBRERIA,
                            "current_price": NVDA_PREZZO_DI_MERCATO,
                            "recommendation": "Sell"}},
        scope=s, category="dcf", source="cache", available=True, reason="finto"))

    misurato = forward.misure("NVDA", None)

    assert "Sell" not in json.dumps(misurato)
    assert misurato["controllo_sulla_libreria"]["concorde"] is True
    assert misurato["prezzo_equo"] == pytest.approx(52.59, abs=0.01)


def test_se_la_formula_della_libreria_cambia_il_referto_lo_dice(monkeypatch):
    """Il giorno che divergono, pubblicare la griglia accanto al loro numero
    sarebbe pubblicare una griglia che non lo descrive."""
    monkeypatch.setattr(defeatbeta, "dcf", lambda s, run_id=None: defeatbeta.Dato(
        dato={"dcf_template": {"base_fcf": NVDA_INGRESSI["base_fcf"],
                               "growth_rate_1_5y": 0.2,
                               "growth_rate_terminal": NVDA_INGRESSI["crescita_terminale"],
                               "discount_rate": NVDA_INGRESSI["sconto"]},
              "dcf_value": {"cash": NVDA_INGRESSI["cassa"],
                            "total_debt": NVDA_INGRESSI["debito"],
                            "shares_outstanding": NVDA_INGRESSI["azioni"],
                            "fair_price": 999.0, "current_price": NVDA_PREZZO_DI_MERCATO}},
        scope=s, category="dcf", source="cache", available=True, reason="finto"))

    controllo = forward.misure("NVDA", None)["controllo_sulla_libreria"]

    assert controllo["concorde"] is False
    assert "la formula e' cambiata" in controllo["nota"]


# --- il verdetto: le contraddizioni, non un punteggio ----------------------

def _referto(metodo: str, giorni_fa: int, contenuto: dict) -> dict:
    quando = datetime.now(UTC) - timedelta(days=giorni_fa)
    return {"metodo": metodo, "creato_il": quando.isoformat(timespec="seconds"),
            "contenuto": contenuto}


METODI_FINTI = {
    "tecnica": {"nome": "Lettura tecnica"},
    "fondamentale": {"nome": "Qualita' fondamentale"},
    "verdetto": {"nome": "Verdetto finale"},
}


def test_il_verdetto_prende_solo_l_ultimo_referto_di_ogni_metodo():
    """Due letture tecniche della stessa settimana raddoppiano il contesto e
    non aggiungono niente."""
    tutti = [_referto("tecnica", 1, {"lettura": "la piu' recente"}),
             _referto("tecnica", 9, {"lettura": "la vecchia"}),
             _referto("fondamentale", 2, {"lettura": "margini in calo"})]

    scelti, mancanti = verdetto.referti_da_sintetizzare(tutti, METODI_FINTI)

    assert len(scelti) == 2
    tecnica = next(r for r in scelti if r["metodo"] == "tecnica")
    assert tecnica["contenuto"]["lettura"] == "la piu' recente"
    assert mancanti == []


def test_un_referto_vecchio_arriva_al_modello_marcato_vecchio():
    """Una sintesi che mette insieme tre mesi fa e stamattina e' coerente e sbagliata."""
    tutti = [_referto("tecnica", 90, {"lettura": "forza"}),
             _referto("fondamentale", 1, {"lettura": "debolezza"})]

    scelti, _ = verdetto.referti_da_sintetizzare(tutti, METODI_FINTI)

    vecchi = {r["metodo"]: r["vecchio"] for r in scelti}
    assert vecchi["tecnica"] is True
    assert vecchi["fondamentale"] is False
    assert next(r for r in scelti if r["metodo"] == "tecnica")["eta_in_giorni"] == 90


def test_il_verdetto_dice_quali_metodi_non_hanno_referti():
    """Un verdetto che tace su cio' che non ha letto si legge come completo."""
    _, mancanti = verdetto.referti_da_sintetizzare(
        [_referto("tecnica", 1, {"lettura": "x"})], METODI_FINTI)

    assert any("Qualita' fondamentale" in m for m in mancanti)
    assert not any("Verdetto" in m for m in mancanti), "non manca a se stesso"


def test_con_un_solo_referto_il_verdetto_si_ferma():
    """Con uno solo la sintesi sarebbe una parafrasi."""
    lavoro = type("L", (), {"run_id": None})()

    with pytest.raises(verdetto.AnalisiError, match="almeno 2 referti"):
        verdetto.esegui("NVDA", lavoro,
                        [_referto("tecnica", 1, {"lettura": "x"})], METODI_FINTI)


def test_i_dati_grezzi_dei_referti_non_finiscono_nel_verdetto():
    """Griglie, metriche e citazioni riempirebbero il contesto di numeri che il
    verdetto non deve ricalcolare."""
    tutti = [_referto("forward", 1, {"lettura": "caro", "dcf": {"sensibilita": [1] * 100}}),
             _referto("fondamentale", 1, {"lettura": "solida",
                                          "metriche": {"roe": {"adesso": 0.3}}})]

    scelti, _ = verdetto.referti_da_sintetizzare(tutti, METODI_FINTI)

    testo = json.dumps(scelti)
    assert "sensibilita" not in testo and "roe" not in testo
    assert "caro" in testo and "solida" in testo


def test_un_testo_lunghissimo_di_un_referto_viene_tagliato(monkeypatch):
    monkeypatch.setattr(config, "VERDETTO_TESTO_CARATTERI", 50)
    tutti = [_referto("tecnica", 1, {"lettura": "parola " * 200}),
             _referto("fondamentale", 1, {"lettura": "corta"})]

    scelti, _ = verdetto.referti_da_sintetizzare(tutti, METODI_FINTI)

    lungo = next(r for r in scelti if r["metodo"] == "tecnica")["contenuto"]["lettura"]
    assert lungo.endswith("[…]") and len(lungo) < 100


# --- il simulatore psicologico ---------------------------------------------
#
# La domanda a cui risponde non e' «quanto avrei guadagnato» ma «cosa avrei
# passato»: sono due domande diverse, e la seconda si dimentica sempre.

def _salita(prezzi: list[float], da: str = "2026-01-01") -> list[dict]:
    """Barre giornaliere consecutive con le chiusure date."""
    inizio = date.fromisoformat(da)
    return [{"timestamp": (inizio + timedelta(days=i)).isoformat(), "close": p}
            for i, p in enumerate(prezzi)]


def test_la_prima_seduta_non_ha_una_variazione_pari_a_zero():
    """Zero vorrebbe dire «non si e' mossa», e non e' quello che sappiamo."""
    sedute = simulatore.variazioni(_salita([100, 110]))

    assert sedute[0]["variazione"] is None
    assert sedute[1]["variazione"] == pytest.approx(0.1)


def test_ogni_seduta_porta_il_suo_giorno_della_settimana():
    """Il 5 e' lunedi' a marzo e giovedi' ad aprile: senza, si legge la griglia
    credendo che le righe siano settimane."""
    sedute = simulatore.variazioni(_salita([100, 101, 102], da="2026-03-05"))

    assert [s["giorno_settimana"] for s in sedute] == ["G", "V", "S"]


def test_la_griglia_mette_i_mesi_in_colonna_e_i_giorni_in_riga():
    prezzi = _salita([100 + i for i in range(70)], da="2026-01-30")
    griglia = simulatore.griglia(simulatore.variazioni(prezzi))

    assert [m["chiave"] for m in griglia["mesi"]] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert griglia["giorni"] == list(range(1, 32))
    assert griglia["celle"]["2026-02"][14]["data"] == "2026-02-14"
    # Febbraio 2026 ha 28 giorni: la casella 30 non esiste, e non e' uno zero.
    assert 30 not in griglia["celle"]["2026-02"]
    assert griglia["mesi"][1]["giorni_del_mese"] == 28


def test_dal_punto_misura_dalla_partenza_e_non_dal_giorno_prima():
    """Giorno su giorno e' quello che si sente; dal punto e' quello che si ricorda."""
    sedute = simulatore.variazioni(_salita([100, 110, 121]))

    dal_via = simulatore.dal_punto(sedute)

    assert [s["variazione"] for s in dal_via] == pytest.approx([0.0, 0.1, 0.21])


def test_le_sedute_prima_del_riferimento_restano_ma_senza_variazione():
    """Toglierle nasconderebbe che il periodo scelto comincia piu' tardi."""
    sedute = simulatore.variazioni(_salita([100, 110, 121]))

    dal_via = simulatore.dal_punto(sedute, riferimento="2026-01-02")

    assert dal_via[0]["variazione"] is None
    assert dal_via[1]["variazione"] == pytest.approx(0.0)
    assert dal_via[2]["variazione"] == pytest.approx(0.1)


def test_il_peggio_attraversato_non_e_la_perdita_finale():
    """E' la discesa dal massimo raggiunto FINO AD ALLORA: il numero che si
    guardava mentre stava succedendo, non quello del consuntivo."""
    # Sale a 200, crolla a 100, risale a 210: finisce in guadagno, ma nel mezzo
    # ha dimezzato.
    sedute = simulatore.variazioni(_salita([100] * 5 + [200] * 5 + [100] * 5 + [210] * 5))

    e = simulatore.esperienza(sedute, 10_000)

    assert e["rendimento"] == pytest.approx(1.1), "finisce a +110%"
    assert e["discesa_peggiore"] == pytest.approx(-0.5), "ma ha attraversato un -50%"


def test_il_tempo_in_perdita_e_una_misura_a_se():
    """Nessun rendimento annuo racconta quanti giorni si e' stati sotto."""
    sedute = simulatore.variazioni(_salita([100] + [80] * 10 + [130] * 9))

    e = simulatore.esperienza(sedute, 10_000)

    assert e["giorni_sotto_il_prezzo_pagato"] == 10
    assert e["quota_del_tempo_in_perdita"] == pytest.approx(0.5)
    assert e["rendimento"] == pytest.approx(0.3), "e intanto il consuntivo e' +30%"


def test_con_pochissime_sedute_non_c_e_niente_da_rivivere():
    e = simulatore.esperienza(simulatore.variazioni(_salita([100, 101, 102])), 10_000)

    assert e["available"] is False
    assert "20 sedute" in e["reason"] and e["action"]


def test_la_rotta_del_simulatore_rifiuta_un_capitale_impossibile(client):
    for valore in ("0", "-100", "molti"):
        risposta = client.get(f"/api/titolo/NVDA/simulatore?capitale={valore}")
        assert risposta.status_code == 400, valore
        assert "capitale" in risposta.get_json()["error"]


def test_la_rotta_del_simulatore_rifiuta_una_base_inventata(client):
    risposta = client.get("/api/titolo/NVDA/simulatore?base=lunare")

    assert risposta.status_code == 400
    assert "giorno" in risposta.get_json()["error"]


def test_un_ingresso_mancante_del_dcf_non_diventa_zero(monkeypatch):
    """Prima cassa e debito ripiegavano su 0,0: un debito assente sarebbe stato
    letto come «azienda senza debiti», e il prezzo equo ne sarebbe uscito piu'
    alto senza che niente lo segnalasse. Su F il debito vale 163 miliardi."""
    completo = {"dcf_template": {"base_fcf": 100.0, "growth_rate_1_5y": 0.1,
                                 "growth_rate_terminal": 0.03, "discount_rate": 0.1},
                "dcf_value": {"cash": 10.0, "total_debt": 5.0,
                              "shares_outstanding": 100.0, "current_price": 1.0}}

    for assente, nome_atteso in (("cash", "cassa"), ("total_debt", "debito totale"),
                                 ("shares_outstanding", "azioni in circolazione")):
        rotto = {**completo, "dcf_value": {k: v for k, v in completo["dcf_value"].items()
                                           if k != assente}}
        monkeypatch.setattr(defeatbeta, "dcf", lambda s, run_id=None, d=rotto: defeatbeta.Dato(
            dato=d, scope=s, category="dcf", source="cache", available=True, reason="finto"))

        with pytest.raises(forward.AnalisiError, match=nome_atteso):
            forward.misure("X", None)


# --- il punteggio di rischio -----------------------------------------------

def _segnali_finti(**stati) -> dict:
    return {"segnali": {n: {"stato": s, "perche": f"{n} e' {s}"} for n, s in stati.items()}}


def test_il_rischio_prende_il_peggiore_e_non_la_media():
    """E' la scelta che lo tiene diverso dai punteggi che questo progetto ha
    gia' tolto due volte: un rischio alto non si annulla con quattro bassi."""
    componenti = [
        rischio.da_segnali(_segnali_finti(F1="spento", F2="spento")),
        rischio.da_discesa({"profondita_massima": -0.05, "giorni_sotto_il_massimo": 3}),
        rischio.da_coda(0.85),
        rischio.da_crescita(0.10, 0.30),
    ]

    esito = rischio.punteggio(componenti)

    assert esito["banda"] == rischio.ALTO
    assert esito["deciso_da"] == "Valore oltre l'orizzonte"
    assert "85%" in esito["perche"], "dice il numero che l'ha deciso"


def test_cio_che_non_si_sa_non_abbassa_il_rischio_ma_la_confidenza():
    """Confonderli e' il modo classico per far sembrare sicuro un titolo di cui
    non sappiamo niente."""
    componenti = [
        rischio.da_segnali(_segnali_finti(F1="acceso")),
        rischio.da_discesa(None),
        rischio.da_coda(None),
        rischio.da_crescita(None, None),
    ]

    esito = rischio.punteggio(componenti)

    assert esito["banda"] == rischio.ALTO, "l'unico calcolabile decide"
    assert esito["confidenza"] == "bassa"
    assert esito["calcolati"] == 1 and esito["su"] == 4


def test_ogni_componente_porta_il_numero_che_lo_ha_deciso():
    """Non c'e' un peso da indovinare: c'e' una soglia scritta e il valore
    misurato accanto."""
    voce = rischio.da_coda(0.83)

    assert voce["banda"] == rischio.ALTO
    assert voce["misura"] == 0.83
    assert "83%" in voce["perche"]


def test_la_crescita_richiesta_si_misura_contro_quella_storica():
    """Non e' «cresce poco» o «cresce tanto»: e' se il prezzo pretende una
    crescita che questa azienda non ha mai avuto."""
    poco = rischio.da_crescita(0.10, 0.40)     # ne chiede un quarto: basso
    tanto = rischio.da_crescita(0.60, 0.20)    # ne chiede il triplo: alto

    assert poco["banda"] == rischio.BASSO
    assert tanto["banda"] == rischio.ALTO


def test_senza_nessun_componente_il_rischio_non_diventa_basso():
    """«Non lo so» e «non c'e' rischio» sono letture opposte."""
    esito = rischio.punteggio([rischio.da_coda(None), rischio.da_crescita(None, None)])

    assert esito["banda"] == rischio.IGNOTO
    assert esito["deciso_da"] is None
