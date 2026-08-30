"""
test_blocco8.py — i cinque segnali di rischio fondamentale.
# feat: la meta' deterministica del Blocco 8, quella che si puo' verificare qui.

Due principi che questi test difendono, e che vengono dal vecchio tradash:

1. **La qualita' dell'azienda e la qualita' dei dati sono cose diverse.**
   `ignoto` dice che il dato manca, non che l'azienda e' peggiore. Un'interfaccia
   che li confonde fa leggere una copertura mancante come un via libera.
2. **Un segnale porta sempre le sue misure.** Un verdetto senza i numeri
   costringe a fidarsi, ed e' invendibile alla domanda "in base a cosa?".
"""
import pandas as pd
import pytest

import config
from core import llm
from core.db import db_read
from data import analisi, defeatbeta
from domain import segnali

TRIMESTRI = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
             "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]


def _prospetto(**voci) -> dict:
    """Un prospetto nella forma che produce `domain/prospetti.py`."""
    return {"voci": {nome: dict(zip(TRIMESTRI, valori, strict=False))
                     for nome, valori in voci.items()},
            "periodi": list(reversed(TRIMESTRI))}


# --- F1: margini ------------------------------------------------------------

def test_f1_si_accende_quando_il_margine_scende_davvero():
    conto = _prospetto(
        total_revenue=[100] * 8,
        gross_profit=[40, 40, 40, 40, 36, 36, 36, 36],      # 40% -> 36%
    )
    esito = segnali.f1_margini(conto)

    assert esito["stato"] == segnali.ACCESO
    assert esito["misure"]["calo_pp"] == 4.0
    assert "40.0%" in esito["perche"] and "36.0%" in esito["perche"]


def test_f1_usa_la_mediana_perche_un_trimestre_eccezionale_non_e_una_tendenza():
    """Con la media, una svalutazione una tantum farebbe suonare il segnale."""
    conto = _prospetto(
        total_revenue=[100] * 8,
        gross_profit=[40, 40, 40, 40, 40, 40, 40, 5],       # un solo trimestre disastroso
    )
    esito = segnali.f1_margini(conto)

    assert esito["stato"] == segnali.SPENTO, "la mediana non si lascia spostare"


def test_f1_senza_abbastanza_trimestri_e_ignoto_non_spento():
    conto = _prospetto(total_revenue=[100, 100], gross_profit=[40, 40])
    esito = segnali.f1_margini(conto)

    assert esito["stato"] == segnali.IGNOTO
    assert str(config.F1_TRIMESTRI_MINIMI) in esito["perche"]


# --- F2: crescita -----------------------------------------------------------

def test_f2_confronta_con_lo_stesso_trimestre_dell_anno_prima():
    """Un business stagionale confrontato col trimestre precedente sembra
    sempre in crisi d'inverno e in boom d'estate."""
    conto = _prospetto(total_revenue=[100, 200, 100, 200, 110, 220, 110, 220])
    esito = segnali.f2_crescita(conto)

    assert esito["stato"] == segnali.SPENTO
    assert esito["misure"]["crescita_annua"] == 0.1


def test_f2_si_accende_dopo_due_trimestri_di_calo():
    conto = _prospetto(total_revenue=[100, 100, 100, 100, 110, 110, 90, 85])
    esito = segnali.f2_crescita(conto)

    assert esito["stato"] == segnali.ACCESO
    assert esito["misure"]["trimestri_in_calo"] == 2


def test_f2_vede_la_decelerazione_anche_senza_calo():
    conto = _prospetto(total_revenue=[100, 100, 100, 100, 200, 200, 200, 110])
    esito = segnali.f2_crescita(conto)

    assert esito["stato"] == segnali.ACCESO
    assert esito["misure"]["decelerazione"] > config.F2_DECELERAZIONE_ACCESA


# --- F3: leva ---------------------------------------------------------------

def test_f3_si_accende_sopra_il_multiplo():
    conto = _prospetto(ebitda=[25] * 8)                    # 100 TTM
    patrimoniale = _prospetto(net_debt=[400] * 8)
    esito = segnali.f3_leva(conto, patrimoniale)

    assert esito["stato"] == segnali.ACCESO
    assert esito["misure"]["debito_netto_su_ebitda"] == 4.0


def test_f3_con_ebitda_negativo_lo_dichiara_invece_di_inventare_un_multiplo():
    """Un multiplo su un EBITDA negativo e' un numero senza senso che pero'
    si stampa benissimo."""
    conto = _prospetto(ebitda=[-10] * 8)
    patrimoniale = _prospetto(net_debt=[400] * 8)
    esito = segnali.f3_leva(conto, patrimoniale)

    assert esito["stato"] == segnali.IGNOTO
    assert "F4" in esito["perche"], "il rischio si sposta sulla liquidita', e va detto dove"


def test_f3_guarda_anche_la_copertura_degli_interessi():
    conto = _prospetto(ebitda=[25] * 8, interest_expense=[10] * 8)   # copertura 2.5
    patrimoniale = _prospetto(net_debt=[50] * 8)                     # multiplo basso
    esito = segnali.f3_leva(conto, patrimoniale)

    assert esito["stato"] == segnali.ACCESO
    assert esito["misure"]["copertura_interessi"] == 2.5


# --- F4: liquidita' ---------------------------------------------------------

def test_f4_conta_i_trimestri_di_autonomia_solo_se_brucia_cassa():
    cassa = _prospetto(free_cash_flow=[-50] * 8)
    patrimoniale = _prospetto(cash_and_cash_equivalents=[100] * 8)

    assert segnali.autonomia_trimestri(cassa, patrimoniale) == 2.0
    assert segnali.f4_liquidita(cassa, patrimoniale)["stato"] == segnali.ACCESO


def test_f4_chi_non_brucia_cassa_non_ha_un_autonomia_da_contare():
    cassa = _prospetto(free_cash_flow=[50] * 8)
    patrimoniale = _prospetto(cash_and_cash_equivalents=[100] * 8)

    assert segnali.autonomia_trimestri(cassa, patrimoniale) is None
    assert segnali.f4_liquidita(cassa, patrimoniale)["stato"] == segnali.SPENTO


# --- F5: diluizione ---------------------------------------------------------

def test_f5_confronta_a_un_anno_di_distanza():
    """Un riacquisto concentrato in un trimestre farebbe sembrare la diluizione
    negativa proprio mentre l'anno la vede crescere."""
    conto = _prospetto(diluted_average_shares=[100, 100, 100, 100, 120, 120, 120, 118])
    esito = segnali.f5_diluizione(conto)

    assert esito["stato"] == segnali.ACCESO
    assert esito["misure"]["crescita_azioni_annua"] == 0.18


def test_f5_riconosce_i_riacquisti():
    conto = _prospetto(diluted_average_shares=[100] * 4 + [95] * 4)
    esito = segnali.f5_diluizione(conto)

    assert esito["stato"] == segnali.SPENTO
    assert "riacquisti" in esito["perche"]


# --- tutti insieme ----------------------------------------------------------

def test_la_copertura_e_una_misura_a_parte():
    """Tre spenti su cinque calcolabili non sono la stessa cosa di tre spenti
    su cinque quando gli altri due erano ignoti."""
    esito = segnali.tutti({
        "income_statement": _prospetto(total_revenue=[100] * 8, gross_profit=[40] * 8,
                                       diluted_average_shares=[100] * 8),
        "balance_sheet": {}, "cash_flow": {},
    })

    assert esito["copertura"]["calcolati"] == 3
    assert sorted(esito["copertura"]["ignoti"]) == ["F3", "F4"]
    assert esito["accesi"] == []


def test_ogni_segnale_porta_il_suo_nome_e_le_sue_misure():
    esito = segnali.tutti({
        "income_statement": _prospetto(total_revenue=[100] * 8, gross_profit=[40] * 8),
        "balance_sheet": {}, "cash_flow": {},
    })

    for chiave, segnale in esito["segnali"].items():
        assert segnale["nome"] == segnali.NOMI[chiave]
        assert segnale["perche"], f"{chiave} non dice perche'"


# --- la route ---------------------------------------------------------------

def test_i_segnali_si_possono_ricostruire_a_una_data(client):
    """Con `as_of` guardano solo i bilanci gia' depositati allora, e lo dicono."""
    risposta = client.get("/api/titolo/NVDA/segnali?as_of=domani")

    assert risposta.status_code == 400
    assert "YYYY-MM-DD" in risposta.get_json()["error"]


# --- le analisi: il registro, il costo, il referto --------------------------

class _Uso:
    def __init__(self, entrata, uscita):
        self.input_tokens = entrata
        self.output_tokens = uscita


class _Blocco:
    def __init__(self, testo):
        self.type = "text"
        self.text = testo


class _Risposta:
    def __init__(self, testo, entrata=1000, uscita=500, stop="end_turn"):
        self.content = [_Blocco(testo)]
        self.usage = _Uso(entrata, uscita)
        self.stop_reason = stop


class _ClienteFinto:
    """Un client che risponde senza uscire. Il finto sta SOTTO cio' che si misura:
    costo, registrazione, lettura del JSON e salvataggio sono codice vero."""

    def __init__(self, risposta):
        self._risposta = risposta
        self.chiamate = []
        self.messages = self

    def create(self, **argomenti):
        self.chiamate.append(argomenti)
        if isinstance(self._risposta, Exception):
            raise self._risposta
        return self._risposta


def _finto(monkeypatch, risposta):
    cliente = _ClienteFinto(risposta)
    monkeypatch.setattr(llm, "_client", lambda: cliente)
    return cliente


def test_il_costo_si_calcola_sui_prezzi_dichiarati():
    assert llm.costo("claude-opus-5", 1_000_000, 0) == 5.0
    assert llm.costo("claude-opus-5", 0, 1_000_000) == 25.0
    assert llm.costo("claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0


def test_un_modello_senza_listino_non_inventa_un_costo():
    """Un costo su prezzi che non abbiamo e' peggio di nessun costo: sembra un dato."""
    assert llm.costo("modello-mai-visto", 1_000_000, 1_000_000) == 0.0


def test_ogni_chiamata_lascia_due_righe_una_col_costo(monkeypatch):
    """Una in `calls` come tutte le altre chiamate, una in `llm_calls` col dettaglio."""
    _finto(monkeypatch, _Risposta("va bene"))

    esito = llm.chiedi(fase="prova", sistema="sei un test", messaggio="ciao", scope="AAPL")

    assert esito["costo_usd"] > 0
    with db_read() as conn:
        generiche = [dict(r) for r in conn.execute("SELECT * FROM calls")]
        dettagli = [dict(r) for r in conn.execute("SELECT * FROM llm_calls")]

    assert [r["provider"] for r in generiche] == ["anthropic"]
    assert generiche[0]["source"] == "network"
    assert dettagli[0]["fase"] == "prova"
    assert dettagli[0]["token_entrata"] == 1000
    assert dettagli[0]["costo_usd"] == esito["costo_usd"]


def test_una_chiamata_fallita_resta_nel_registro(monkeypatch):
    """Se sparisse, il conto di quanto si e' bruciato sarebbe sbagliato per difetto."""
    _finto(monkeypatch, RuntimeError("il modello non risponde"))

    with pytest.raises(llm.LlmNonDisponibile):
        llm.chiedi(fase="prova", sistema="s", messaggio="m")

    with db_read() as conn:
        dettagli = [dict(r) for r in conn.execute("SELECT * FROM llm_calls")]
    assert dettagli[0]["status"] == "error"


def test_il_modello_riceve_i_numeri_e_non_gli_strumenti_per_calcolarli(monkeypatch):
    """La regola ferrea del vecchio prompt — "non ricalcolare niente" — qui e'
    strutturale: senza strumenti da chiamare, non ha modo di inventare un numero."""
    cliente = _finto(monkeypatch, _Risposta('{"lettura": "sale", "confidenza": "alta"}'))
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({"close": [100 + i for i in range(300)],
                            "volume": [1e6] * 300,
                            "report_date": [f"2026-01-{i % 28 + 1:02d}" for i in range(300)]}),
        scope=s, category="price", source="cache", available=True, reason="finto"))
    monkeypatch.setattr(defeatbeta, "profile", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame(), scope=s, category="profile", source="cache",
        available=False, reason="niente profilo"))

    esito = analisi.esegui("tecnica", "aaa")

    assert esito["motivo"] == "completata"
    assert "tools" not in cliente.chiamate[0], "nessuno strumento da chiamare"
    assert esito["contenuto"]["misure"]["media_200"] is not None
    assert esito["contenuto"]["lettura"] == "sale"


def test_un_titolo_con_poca_storia_ferma_l_analisi_invece_di_degradarla(monkeypatch):
    """Un referto costruito su venti sedute costa quanto uno costruito su seimila
    e vale molto meno."""
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({"close": [100.0] * 10, "volume": [1e6] * 10,
                            "report_date": ["2026-01-01"] * 10}),
        scope=s, category="price", source="cache", available=True, reason="finto"))

    with pytest.raises(analisi.AnalisiError, match="si ferma invece di degradare"):
        analisi.esegui("tecnica", "AAA")


def test_i_metodi_non_ancora_costruiti_restano_in_elenco_e_dicono_cosa_manca():
    """Toglierli li farebbe sparire, e un'analisi che manca senza dirlo e'
    indistinguibile da un'analisi che non serve."""
    metodi = {m["metodo"]: m for m in analisi.elenco()}

    assert len(metodi) == 7
    for chiave, metodo in metodi.items():
        if not metodo["pronta"]:
            assert metodo["manca"], f"{chiave} non dice cosa gli manca"


def test_chiedere_un_metodo_non_pronto_dice_cosa_gli_manca():
    with pytest.raises(analisi.AnalisiError, match=r"sec\.gov"):
        analisi.esegui("qualitativa", "NVDA")

    with pytest.raises(analisi.AnalisiError, match="metodo sconosciuto"):
        analisi.esegui("oroscopo", "NVDA")


def test_un_rifiuto_del_modello_non_diventa_un_referto_vuoto(monkeypatch):
    _finto(monkeypatch, _Risposta("", stop="refusal"))
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({"close": [100 + i for i in range(300)],
                            "volume": [1e6] * 300,
                            "report_date": [f"2026-01-{i % 28 + 1:02d}" for i in range(300)]}),
        scope=s, category="price", source="cache", available=True, reason="finto"))
    monkeypatch.setattr(defeatbeta, "profile", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame(), scope=s, category="profile", source="cache",
        available=False, reason="niente"))

    with pytest.raises(analisi.AnalisiError, match="rifiutato"):
        analisi.esegui("tecnica", "AAA")
