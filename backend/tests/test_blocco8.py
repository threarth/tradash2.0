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
import numpy as np
import pandas as pd
import pytest

import config
from core import llm
from core.db import db_read
from data import analisi, defeatbeta, filing_locali
from domain import pannello, segnali, spinoff, trascrizione

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
    with pytest.raises(analisi.AnalisiError, match="quattro fasi"):
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


# --- i filing che scarichi tu ----------------------------------------------

INDICE_FILING = pd.DataFrame([
    {"form_type": "10-Q", "report_date": "2026-07-26", "filing_date": "2026-08-26",
     "accession_number": "0001045810-26-000075",
     "filing_url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075"},
    {"form_type": "10-K", "report_date": "2026-01-25", "filing_date": "2026-02-25",
     "accession_number": "0001045810-26-000021",
     "filing_url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021"},
    {"form_type": "8-K", "report_date": "2026-03-01", "filing_date": "2026-03-02",
     "accession_number": "0001045810-26-000030", "filing_url": "https://x.example"},
])


@pytest.fixture
def indice_finto(monkeypatch):
    monkeypatch.setattr(defeatbeta, "sec_filings", lambda s, run_id=None: defeatbeta.Lettura(
        frame=INDICE_FILING, scope=s, category="sec_filings", source="cache",
        available=True, reason="finto"))


def test_chiede_solo_i_documenti_periodici(indice_finto):
    """Un 8-K non chiude nessun periodo e non serve alla qualitativa."""
    voci = filing_locali.richiesti("NVDA")

    assert [v["form_type"] for v in voci] == ["10-Q", "10-K"]
    assert all(v["accession_number"] for v in voci)


def test_il_nome_proposto_porta_il_protocollo(indice_finto):
    """Il resto del nome e' per gli occhi; il protocollo e' la chiave."""
    voce = filing_locali.richiesti("NVDA")[0]

    assert voce["nome_atteso"] == "NVDA_10-Q_2026-07-26_0001045810-26-000075.html"
    assert voce["accession_number"] in voce["nome_atteso"]


def test_riconosce_il_file_anche_con_un_nome_diverso(indice_finto, tmp_path, monkeypatch):
    """Se hai salvato con un nome tuo ma il protocollo c'e', il documento e' quello:
    non c'e' motivo di non riconoscerlo."""
    monkeypatch.setattr(config, "FILING_DIR", tmp_path)
    cartella = tmp_path / "NVDA"
    cartella.mkdir()
    (cartella / "nvidia scaricato ieri 000104581026000075.html").write_text(
        "<html><body>Item 1A. Risk Factors</body></html>", encoding="utf-8")

    stato = filing_locali.stato("NVDA")

    trovato = next(d for d in stato["documenti"] if d["form_type"] == "10-Q")
    assert trovato["presente"] is True
    assert stato["pronti"] == 1 and stato["richiesti"] == 2
    assert stato["completo"] is False
    assert "mancano 1" in stato["reason"]


def test_estrae_il_testo_senza_fogli_di_stile_ne_script(indice_finto, tmp_path, monkeypatch):
    """Finirebbero nel prompt come migliaia di token che non dicono niente."""
    monkeypatch.setattr(config, "FILING_DIR", tmp_path)
    cartella = tmp_path / "NVDA"
    cartella.mkdir()
    (cartella / "NVDA_10-K_2026-01-25_0001045810-26-000021.html").write_text(
        "<html><head><style>body{color:red}</style>"
        "<script>var x = 1;</script></head>"
        "<body><h1>ANNUAL REPORT</h1><p>Our business   depends on few customers.</p>"
        "</body></html>", encoding="utf-8")

    testo, errore = filing_locali.testo("NVDA", "0001045810-26-000021")

    assert errore is None
    assert "ANNUAL REPORT" in testo
    assert "color:red" not in testo and "var x" not in testo
    assert "business depends" in testo, "gli spazi ripetuti si stringono: ognuno e' un token"


def test_un_documento_che_manca_dice_dove_metterlo(indice_finto, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FILING_DIR", tmp_path)

    testo, errore = filing_locali.testo("NVDA", "0001045810-26-000021")

    assert testo is None
    assert str(tmp_path / "NVDA") in errore


def test_lo_stato_dice_cosa_fare_quando_manca_qualcosa(indice_finto, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FILING_DIR", tmp_path)

    stato = filing_locali.stato("NVDA")

    assert stato["completo"] is False
    assert stato["pronti"] == 0
    assert "salva" in stato["action"]
    assert stato["cartella"].endswith("NVDA")


def test_senza_depositi_nell_indice_lo_dice(monkeypatch):
    monkeypatch.setattr(defeatbeta, "sec_filings", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame(), scope=s, category="sec_filings", source="cache",
        available=False, reason="nessun deposito"))

    stato = filing_locali.stato("XYZ")

    assert stato["documenti"] == []
    assert "nessun documento periodico" in stato["reason"]


# --- la soglia della diluizione dipende dall'azienda -----------------------

def test_chi_produce_cassa_non_ha_tolleranza():
    """Un'azienda che genera free cash flow si finanzia da sola: emettere azioni
    e' una scelta, non un fabbisogno."""
    conto = _prospetto(total_revenue=[100] * 8)
    cassa = _prospetto(free_cash_flow=[20] * 8)

    tolleranza, evidenza = segnali.tolleranza_diluizione(conto, cassa)

    assert tolleranza == "bassa"
    assert evidenza["brucia_cassa"] is False
    assert "scelta" in evidenza["regola"]


def test_chi_brucia_cassa_per_crescere_forte_ha_la_tolleranza_piu_alta():
    conto = _prospetto(total_revenue=[100, 100, 100, 100, 200, 200, 200, 200])
    cassa = _prospetto(free_cash_flow=[-30] * 8)

    tolleranza, evidenza = segnali.tolleranza_diluizione(conto, cassa)

    assert tolleranza == "alta"
    assert evidenza["crescita_ricavi"] == 1.0


def test_chi_brucia_cassa_senza_crescere_no():
    """Non sta finanziando espansione: sta finanziando le perdite."""
    conto = _prospetto(total_revenue=[100] * 8)
    cassa = _prospetto(free_cash_flow=[-30] * 8)

    tolleranza, _ = segnali.tolleranza_diluizione(conto, cassa)

    assert tolleranza == "bassa"


def test_la_precedenza_e_cassa_prima_della_fase():
    """Il difetto pagato dal vecchio sistema su MU: senza questa precedenza,
    "crescita forte piu' intensita' di capitale" davano a un'azienda
    cash-generative tre gradini di tolleranza in piu' del dovuto."""
    in_crescita_e_intensiva = _prospetto(
        total_revenue=[100, 100, 100, 100, 200, 200, 200, 200])
    produce_cassa = _prospetto(free_cash_flow=[50] * 8, capital_expenditure=[-40] * 8)

    tolleranza, _ = segnali.tolleranza_diluizione(in_crescita_e_intensiva, produce_cassa)

    assert tolleranza == "bassa", "cresce forte ed e' intensiva, ma non ne ha bisogno"


def test_la_stessa_diluizione_si_giudica_in_modo_diverso():
    """Il dato e' lo stesso, il giudizio no: e' il senso di avere quattro soglie."""
    azioni = {"diluted_average_shares": [100, 100, 100, 100, 106, 106, 106, 106]}

    chi_cresce = _prospetto(total_revenue=[100, 100, 100, 100, 200, 200, 200, 200], **azioni)
    chi_produce = _prospetto(total_revenue=[100] * 8, **azioni)

    acceso = segnali.f5_diluizione(chi_cresce, _prospetto(free_cash_flow=[-30] * 8))
    spento = segnali.f5_diluizione(chi_produce, _prospetto(free_cash_flow=[20] * 8))

    assert acceso["misure"]["crescita_azioni_annua"] == spento["misure"]["crescita_azioni_annua"]
    assert acceso["stato"] == segnali.SPENTO, "il 6% e' fisiologico per chi cresce forte"
    assert spento["stato"] == segnali.ACCESO, "il 6% non lo e' per chi produce cassa"


def test_il_segnale_dice_quale_soglia_ha_usato_e_perche():
    conto = _prospetto(total_revenue=[100] * 8,
                       diluted_average_shares=[100] * 4 + [110] * 4)
    esito = segnali.f5_diluizione(conto, _prospetto(free_cash_flow=[20] * 8))

    assert esito["misure"]["tolleranza"] == "bassa"
    assert "soglia" in esito["perche"]
    assert esito["misure"]["soglia_accesa"] == config.F5_SOGLIE["bassa"]["acceso"]


# --- le metriche della libreria, lette dal registro ------------------------

def test_l_elenco_delle_metriche_e_chiuso():
    """Il nome finisce in un `getattr`: chiuso, non e' una porta."""
    with pytest.raises(ValueError, match="non prevista"):
        defeatbeta.metrica("NVDA", "__class__")

    assert "roe" in defeatbeta.METRICHE
    assert all(not n.startswith("_") for n in defeatbeta.METRICHE)


def test_una_metrica_passa_dal_registro_come_ogni_lettura(monkeypatch):
    """La differenza fra usare i metodi della libreria e scrivere il calcolo a
    mano non deve essere che gli uni si vedono nel log e gli altri no."""
    frame = pd.DataFrame({"symbol": ["X"] * 3, "report_date": ["2025-12-31"] * 3,
                          "roe": [0.1, 0.2, 0.3]})
    monkeypatch.setattr(defeatbeta, "_esegui_metodo", lambda s, n: (frame, 2))

    lettura = defeatbeta.metrica("X", "roe")

    assert lettura.available is True
    assert lettura.source == "network", "due richieste HTTP: e' rete"
    with db_read() as conn:
        righe = [dict(r) for r in conn.execute("SELECT * FROM calls")]
    assert righe[0]["endpoint"] == "metrica:roe"
    assert righe[0]["scope"] == "X"


def test_una_metrica_servita_dalla_cache_lo_dice(monkeypatch):
    frame = pd.DataFrame({"symbol": ["X"], "roe": [0.1]})
    monkeypatch.setattr(defeatbeta, "_esegui_metodo", lambda s, n: (frame, 0))

    assert defeatbeta.metrica("X", "roe").source == "cache"


def test_un_simbolo_malformato_non_arriva_alla_libreria(monkeypatch):
    """La libreria interpola il ticker nel testo SQL: la porta si chiude prima."""
    def _mai(simbolo, nome):
        raise AssertionError("non doveva arrivare qui")

    monkeypatch.setattr(defeatbeta, "_esegui_metodo", _mai)

    lettura = defeatbeta.metrica("robaccia'; DROP TABLE calls; --", "roe")

    assert lettura.available is False
    assert lettura.action == defeatbeta.ACTION_SIMBOLO_MALFORMATO


def test_il_catalogo_dice_quali_costano_e_quali_hanno_il_settore(client):
    d = client.get("/api/titolo/NVDA/metriche").get_json()["data"]
    per_nome = {m["nome"]: m for m in d["metriche"]}

    assert "industry_roe" not in per_nome, "le gemelle non si scelgono, si accompagnano"
    assert per_nome["roe"]["gemella_di_settore"] == "industry_roe"
    assert per_nome["wacc"]["lenta"] is True
    assert all(m["descrizione"] for m in d["metriche"])


def test_una_metrica_inventata_viene_rifiutata_dalla_route(client):
    risposta = client.get("/api/titolo/NVDA/metriche/oroscopo")

    assert risposta.status_code == 400
    assert "sconosciuta" in risposta.get_json()["error"]


# --- il pannello: le serie ridotte a cio' che si legge ---------------------

def test_una_serie_diventa_tre_numeri():
    """`ttm_pe` ha 6.875 righe: mandarle intere costerebbe ~200.000 token per un
    numero che si guarda alla fine."""
    righe = [{"report_date": f"2025-0{i+1}-01", "roe": 0.10 + i * 0.01} for i in range(8)]

    compressa = pannello.comprimi(righe, ["report_date", "roe"])

    assert compressa["adesso"] == 0.17
    assert compressa["un_anno_fa"] == 0.13, "quattro punti indietro su serie trimestrale"
    assert compressa["movimento"] == "in aumento"
    assert compressa["punti"] == 8


def test_il_valore_che_conta_e_l_ultima_colonna_numerica():
    """Le tabelle della libreria portano i valori intermedi accanto al risultato:
    `roe` ha utile, patrimonio e ROE, in quest'ordine."""
    righe = [{"report_date": "2025-01-01", "net_income": 100.0,
              "avg_equity": 1000.0, "roe": 0.1}]

    compressa = pannello.comprimi(righe, ["report_date", "net_income", "avg_equity", "roe"])

    assert compressa["misura"] == "roe"
    assert compressa["adesso"] == 0.1


def test_una_serie_giornaliera_guarda_indietro_di_un_anno_di_borsa():
    righe = [{"report_date": f"g{i}", "pe": 20.0 + i * 0.01} for i in range(300)]

    compressa = pannello.comprimi(righe, ["report_date", "pe"])

    assert compressa["punti"] == 300
    assert compressa["un_anno_fa"] == round(20.0 + (300 - 1 - 252) * 0.01, 4)


def test_una_serie_vuota_non_vale_zero():
    assert pannello.comprimi([], ["roe"]) is None
    assert pannello.comprimi([{"report_date": "2025-01-01"}], ["report_date"]) is None


def test_senza_un_anno_di_storia_il_movimento_non_si_pronuncia():
    righe = [{"d": "1", "roe": 0.1}, {"d": "2", "roe": 0.2}]

    compressa = pannello.comprimi(righe, ["d", "roe"])

    assert compressa["un_anno_fa"] is None
    assert compressa["movimento"] == "non confrontabile"


def test_il_confronto_col_settore_dice_di_quanto_ci_si_discosta():
    """"Questo numero e' alto?" non ha senso da solo: e' la domanda che il vecchio
    sistema non sapeva rispondere per undici ticker su diciotto."""
    titolo = {"adesso": 0.33, "misura": "roe"}
    settore = {"adesso": 0.60, "misura": "industry_roe"}

    confrontato = pannello.confronta(titolo, settore)

    assert confrontato["settore"] == 0.60
    assert confrontato["scarto_dal_settore"] == -0.45
    assert confrontato["sopra_il_settore"] is False


def test_senza_settore_il_confronto_lascia_il_titolo_com_e():
    titolo = {"adesso": 0.33, "misura": "roe"}

    assert pannello.confronta(titolo, None) == titolo
    assert pannello.confronta(None, {"adesso": 0.6}) is None


# --- l'analisi fondamentale -------------------------------------------------

def test_la_fondamentale_e_pronta_e_dice_su_cosa_poggia():
    metodi = {m["metodo"]: m for m in analisi.elenco()}

    assert metodi["fondamentale"]["pronta"] is True
    assert "settore" in metodi["fondamentale"]["fonte"]


def test_una_metrica_che_manca_non_ferma_il_pannello(monkeypatch):
    """Le altre otto continuano a dire quello che sanno."""
    def _a_meta(simbolo, nome, run_id=None):
        if nome == "roe":
            raise defeatbeta.DefeatbetaUnavailable("questa no")
        return defeatbeta.Lettura(
            frame=pd.DataFrame({"symbol": ["X"], "report_date": ["2026-01-01"], "v": [1.0]}),
            scope="X", category="metriche", source="cache", available=True, reason="finto")

    monkeypatch.setattr(defeatbeta, "metrica", _a_meta)

    misure, mancanti = analisi._pannello("X", None)

    assert "roe" in mancanti
    assert "roic" in misure


def test_senza_nemmeno_una_metrica_la_fondamentale_si_ferma(monkeypatch):
    """Una lettura fondamentale senza numeri non e' povera: e' inventata."""
    monkeypatch.setattr(analisi, "_segnali_fondamentali", lambda s, r: {"segnali": {}})
    monkeypatch.setattr(defeatbeta, "metrica", lambda s, n, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame(), scope=s, category="metriche", source="cache",
        available=False, reason="niente"))

    with pytest.raises(analisi.AnalisiError, match="si ferma"):
        analisi._fondamentale("X", None)


# --- le trascrizioni: due meta' che si leggono in modo diverso -------------

def _paragrafi(voci) -> list[dict]:
    return [{"paragraph_number": i + 1, "speaker": chi, "content": testo}
            for i, (chi, testo) in enumerate(voci)]


CALL = _paragrafi([
    ("Operator", "Welcome to the call. After the speakers' remarks, there will be a "
                 "question-and-answer session."),
    ("Colette Kress", "Revenue was 46 billion, up 56%."),
    ("Colette Kress", "For next quarter we expect 54 billion."),
    ("Operator", "In order to ask a question, press star then one."),
    ("Operator", "Your first question comes from the line of Joseph Moore."),
    ("Joseph Moore", "What gives you confidence in the guide?"),
    ("Jensen Huang", "AI has become useful."),
    ("Jensen Huang", "Customers can mix and match."),
    ("Operator", "Your next question comes from the line of C.J. Muse."),
    ("C.J. Muse", "And on margins?"),
    ("Colette Kress", "We expect them to hold."),
])


def test_il_saluto_iniziale_non_e_l_inizio_delle_domande():
    """Misurato su NVDA: l'operatore dice gia' nel saluto "there will be a
    question-and-answer session", e un marcatore ingenuo aggancia il paragrafo 1
    lasciando la parte preparata vuota."""
    struttura = trascrizione.struttura(CALL)

    assert len(struttura["preparata"]) == 2, "i due interventi del CFO"
    assert struttura["management"] == ["Colette Kress"]
    assert "46 billion" in struttura["preparata"][0]["testo"]


def test_a_dire_chi_e_l_analista_e_l_operatore():
    """Prima lo deducevo da chi aveva parlato nella parte preparata, e su NVDA
    il CEO risultava analista ventotto volte: in quella call aveva parlato solo
    rispondendo."""
    struttura = trascrizione.struttura(CALL)

    assert [s["analista"] for s in struttura["scambi"]] == ["Joseph Moore", "C.J. Muse"]
    assert [r["chi"] for r in struttura["scambi"][0]["risposte"]] == \
        ["Jensen Huang", "Jensen Huang"]


def test_una_call_senza_domande_lo_dice():
    solo_preparata = _paragrafi([("Operator", "Welcome."), ("CFO", "I numeri sono questi.")])

    struttura = trascrizione.struttura(solo_preparata)

    assert struttura["ha_domande"] is False
    assert struttura["scambi"] == []
    assert len(struttura["preparata"]) == 1


def test_i_paragrafi_arrivano_come_array_numpy():
    """`paragrafi or []` non si puo' scrivere: su un array numpy il valore di
    verita' e' ambiguo e solleva invece di decidere."""
    struttura = trascrizione.struttura(np.array(CALL, dtype=object))

    assert len(struttura["scambi"]) == 2
    assert trascrizione.struttura(None)["caratteri"] == 0


def test_le_troncature_si_contano_e_si_dichiarano(monkeypatch):
    """Un testo troncato mostrato senza dirlo si legge come se quella fosse
    tutta la risposta."""
    monkeypatch.setattr(config, "TRASCRIZIONE_RISPOSTA_CARATTERI", 20)

    leggibile = analisi._call_leggibile(trascrizione.struttura(CALL), con_risposte=True)

    assert leggibile["testi_troncati"] > 0
    assert leggibile["scambi"][0]["domanda"].endswith("[…]")


def test_l_earnings_si_ferma_se_non_ci_sono_trascrizioni(monkeypatch):
    monkeypatch.setattr(defeatbeta, "transcripts", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame(), scope=s, category="transcripts", source="cache",
        available=False, reason="nessuna call"))

    with pytest.raises(analisi.AnalisiError, match=r"6\.495 simboli"):
        analisi._earnings("X", None)


def test_l_earnings_legge_due_call_per_vedere_cosa_e_cambiato(monkeypatch):
    """Le preoccupazioni degli analisti si spostano, e vederle spostarsi dice
    piu' di una fotografia sola."""
    frame = pd.DataFrame([
        {"fiscal_year": 2027, "fiscal_quarter": 2, "report_date": "2026-08-26",
         "transcripts": CALL},
        {"fiscal_year": 2027, "fiscal_quarter": 1, "report_date": "2026-05-26",
         "transcripts": CALL},
    ])
    monkeypatch.setattr(defeatbeta, "transcripts", lambda s, run_id=None: defeatbeta.Lettura(
        frame=frame, scope=s, category="transcripts", source="cache",
        available=True, reason="finto"))
    monkeypatch.setattr(defeatbeta, "profile", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame(), scope=s, category="profile", source="cache",
        available=False, reason="niente"))
    _finto(monkeypatch, _Risposta('{"lettura": "va bene", "confidenza": "media"}'))

    esito = analisi._earnings("X", None)

    assert esito["contenuto"]["call"] == "2027 Q2"
    assert esito["contenuto"]["call_precedente"] == "2027 Q1"


# --- il rilevatore di spin-off ---------------------------------------------

def _notizia(titolo: str, quando: str = "2026-08-01", corpo=None) -> dict:
    return {"title": titolo, "report_date": quando, "publisher": "Tale dei Tali",
            "link": "https://x.example", "news": corpo}


def test_lo_stadio_si_deduce_dal_titolo_e_puo_non_dedursi():
    """"non determinabile" e' diverso da "annunciato": confonderli farebbe
    contare come annuncio un commento."""
    assert spinoff.stadio("IDT Delays net2phone Spin-Off Until Markets Improve") == "rinviato"
    assert spinoff.stadio("Comcast announces plans to spin off NBCUniversal") == "annunciato"
    assert spinoff.stadio("GE Vernova completes its spin-off") == "completato"
    assert spinoff.stadio("Corteva's Vylor Spin-Off Seen as Catalyst") == \
        spinoff.STADIO_IGNOTO


def test_il_completamento_vince_sull_annuncio():
    """Un articolo che racconta il completamento nomina spesso anche l'annuncio."""
    assert spinoff.stadio("Company completes the spin-off it announced last year") == \
        "completato"


def test_scarta_le_notizie_che_parlano_di_un_altra_societa():
    """Misurato: NVDA aveva dodici menzioni, e parlavano di Comcast e Honeywell —
    rassegne di mercato associate al simbolo ma su altre societa'."""
    righe = [
        _notizia("There Are Now 4 Honeywell Stocks After This Latest Spin-Off"),
        _notizia("Nvidia's chip unit spin-off is confirmed"),
    ]

    trovate = spinoff.menzioni_nelle_notizie(righe, "NVDA", "NVIDIA Corporation")

    assert [m["titolo"] for m in trovate] == ["Nvidia's chip unit spin-off is confirmed"]


def test_riconosce_la_societa_dal_simbolo_o_dal_nome():
    assert spinoff.riguarda_il_titolo("IDT Delays Spin-Off", "IDT", "IDT Corporation")
    assert spinoff.riguarda_il_titolo("Corteva's Vylor Spin-Off", "CTVA", "Corteva, Inc.")
    assert not spinoff.riguarda_il_titolo("Honeywell Spin-Off", "CTVA", "Corteva, Inc.")


def test_le_forme_giuridiche_non_contano_come_nome():
    """"Corporation" comparirebbe in mezzo mercato, e riconoscerebbe chiunque."""
    assert not spinoff.riguarda_il_titolo("Some Corporation Spin-Off", "AAA",
                                          "IDT Corporation")


def test_senza_nome_noto_non_si_filtra_ma_lo_si_dichiara():
    """L'8,6% dell'universo non ha un nome: un silenzio sarebbe peggio."""
    trovate = spinoff.menzioni_nelle_notizie([_notizia("Some Spin-Off news")], "", None)

    assert len(trovate) == 1
    assert trovate[0]["riguarda_il_titolo"] is None


def test_dalla_call_si_distingue_chi_parla():
    """Il management che lo annuncia e un analista che lo chiede non sono la
    stessa cosa: il primo e' una dichiarazione, il secondo una preoccupazione."""
    struttura = {
        "preparata": [{"chi": "CFO", "testo": "We plan a spin-off of our unit."}],
        "scambi": [{"analista": "Tizio", "domanda": "Any update on the spinoff?",
                    "risposte": [{"chi": "CEO", "testo": "It is on track."}]}],
    }

    menzioni = spinoff.menzioni_nella_call(struttura)

    assert [m["dove"] for m in menzioni] == ["parte preparata", "domanda di un analista"]
    assert menzioni[0]["chi"] == "CFO"


def test_senza_menzioni_non_si_chiede_niente_al_modello(monkeypatch):
    """Un modello a cui si chiede di analizzare il vuoto produce comunque una
    risposta, e quella risposta sembra un'analisi."""
    monkeypatch.setattr(analisi, "_menzioni_notizie", lambda s, r: [])
    monkeypatch.setattr(analisi, "_menzioni_call", lambda s, r: [])
    chiamato = {"si": False}
    monkeypatch.setattr(llm, "chiedi", lambda **k: chiamato.__setitem__("si", True))

    esito = analisi._spin_off("AAA", None)

    assert chiamato["si"] is False
    assert esito["costo_usd"] == 0.0
    assert esito["contenuto"]["c_e_uno_spinoff"] == "no"
    assert esito["contenuto"]["dati_mancanti"], "dice anche cosa NON puo' sapere"
