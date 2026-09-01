"""
test_blocco7.py — as_of: cosa si sapeva allora, e su cosa poggia il taglio.
# feat: se questi test non passano, non si va al Blocco 8.

Il look-ahead che questo blocco chiude non produce nessun errore. Un trimestre
chiuso il 30 giugno viene depositato ad agosto: chi tronca sulla fine del
periodo, ricostruendo un'analisi al 15 luglio, vede un bilancio che allora non
esisteva. Sono quaranta giorni di futuro nella finestra in cui il prezzo si
muove di piu', e il risultato non e' un'eccezione — e' un backtest bravissimo.

Per questo i test qui sotto non guardano solo il risultato: guardano se il
risultato sa dire su cosa poggia.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

import config
from data import defeatbeta, depositi, materiale
from data import ricostruzione as ricostruzione_dati
from domain import prospetti, publication_dates, ricostruzione, voci

# Una mappa di depositi come la costruisce `data/depositi.py`: fine periodo →
# (data di deposito, fonte).
REALE = publication_dates.SOURCE_FILING_INDEX
DEPOSITI = {
    "2024-03-31": ("2024-05-02", REALE),
    "2024-06-30": ("2024-08-01", REALE),
}


# --- quando un periodo e' diventato pubblico -------------------------------

def test_una_data_di_deposito_reale_vince_sulla_stima():
    quando, fonte = publication_dates.publication_date(DEPOSITI, "2024-06-30")

    assert quando == "2024-08-01"
    assert fonte == REALE


def test_senza_deposito_si_stima_TARDI():
    """Prudente qui significa tardi: meglio non vedere un dato che c'era, che
    vederne uno che non c'era."""
    quando, fonte = publication_dates.publication_date({}, "2024-09-30", is_quarterly=True)

    assert fonte == publication_dates.SOURCE_ESTIMATED
    assert quando == "2024-11-14", (
        f"{config.AS_OF_RITARDO_TRIMESTRALE_GIORNI} giorni dopo la fine del trimestre"
    )


def test_un_annuale_si_stima_ancora_piu_tardi():
    trimestre, _ = publication_dates.publication_date({}, "2024-12-31", is_quarterly=True)
    annuale, _ = publication_dates.publication_date({}, "2024-12-31", is_quarterly=False)

    assert annuale > trimestre


def test_le_due_fonti_non_si_allineano_al_giorno():
    """Un trimestre "chiuso il 28 giugno" nei bilanci puo' essere il 30 giugno
    nell'indice dei depositi. Senza tolleranza si ricadrebbe sulla stima pur
    avendo il dato vero."""
    quando, fonte = publication_dates.publication_date(DEPOSITI, "2024-06-28")

    assert fonte == REALE
    assert quando == "2024-08-01"


def test_un_periodo_e_pubblico_solo_dopo_il_deposito():
    """Il cuore del blocco: la fine del trimestre non e' la data in cui si sa."""
    assert publication_dates.was_public(DEPOSITI, "2024-06-30", "2024-08-02") is True
    assert publication_dates.was_public(DEPOSITI, "2024-06-30", "2024-07-15") is False, (
        "il 15 luglio quel bilancio non esisteva ancora"
    )


# --- e su cosa poggia il taglio --------------------------------------------

def test_la_base_del_taglio_distingue_i_fatti_dalle_stime():
    tutte_reali = publication_dates.truncation_basis(DEPOSITI, list(DEPOSITI))
    assert tutte_reali["source"] == REALE
    assert tutte_reali["estimated_periods"] == 0

    meta = publication_dates.truncation_basis(DEPOSITI, [*DEPOSITI, "2023-01-31"])
    assert meta["source"] == publication_dates.SOURCE_MIXED
    assert meta["real_periods"] == 2 and meta["estimated_periods"] == 1

    nessuna = publication_dates.truncation_basis({}, ["2024-06-30"])
    assert nessuna["source"] == publication_dates.SOURCE_ESTIMATED


def test_senza_periodi_la_base_non_e_affidabile_ma_non_pervenuta():
    """`None` non e' "va tutto bene": e' "non c'e' niente su cui pronunciarsi"."""
    vuota = publication_dates.truncation_basis(DEPOSITI, [])

    assert vuota["source"] is None
    assert vuota["periods"] == 0


# --- la mappa dei depositi, letta da Defeatbeta ----------------------------

def test_vince_il_primo_deposito_non_la_rettifica(monkeypatch):
    """Una rettifica successiva non retrodata la notizia."""
    frame = pd.DataFrame([
        {"form_type": "10-Q", "report_date": "2024-06-30", "filing_date": "2024-11-20"},
        {"form_type": "10-Q", "report_date": "2024-06-30", "filing_date": "2024-08-01"},
        {"form_type": "8-K", "report_date": "2024-06-30", "filing_date": "2024-07-02"},
    ])
    monkeypatch.setattr(defeatbeta, "sec_filings", lambda s, run_id=None: defeatbeta.Lettura(
        frame=frame, scope="X", category="sec_filings", source="cache",
        available=True, reason="finto",
    ))

    mappa = depositi.mappa("X")

    assert mappa["2024-06-30"] == ("2024-08-01", REALE), "il primo 10-Q, non la rettifica"
    assert len(mappa) == 1, "l'8-K non chiude nessun trimestre e non entra"


def test_un_titolo_senza_depositi_non_e_un_errore(monkeypatch):
    monkeypatch.setattr(defeatbeta, "sec_filings", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame(), scope="X", category="sec_filings", source="cache",
        available=False, reason="nessun deposito", action="verifica il simbolo",
    ))

    assert depositi.mappa("X") == {}


# --- i prospetti ------------------------------------------------------------

def _bilanci() -> pd.DataFrame:
    righe = []
    for periodo in ("2024-03-31", "2024-06-30", "TTM"):
        for voce, valore in (("total_revenue", 100.0), ("net_income", 10.0)):
            righe.append({"report_date": periodo, "item_name": voce, "item_value": valore,
                          "finance_type": prospetti.CONTO_ECONOMICO,
                          "period_type": prospetti.TRIMESTRALE})
    return pd.DataFrame(righe)


def test_il_ttm_non_e_una_data_e_resta_fuori():
    """Un filtro sulle date lo tratterebbe come una stringa qualsiasi, finendo
    dove capita."""
    assert prospetti.periodi(_bilanci()) == ["2024-06-30", "2024-03-31"]

    tabella = prospetti.tabella(_bilanci(), prospetti.CONTO_ECONOMICO)
    assert prospetti.PERIODO_TTM not in tabella["periodi"]


def test_la_tabella_tiene_solo_i_periodi_ammessi():
    """E' il taglio temporale: chi lo passa ha gia' deciso cosa era pubblico."""
    tabella = prospetti.tabella(_bilanci(), prospetti.CONTO_ECONOMICO,
                                periodi_ammessi=["2024-03-31"])

    assert tabella["periodi"] == ["2024-03-31"]
    assert tabella["voci"]["total_revenue"] == {"2024-03-31": 100.0}


# --- le route ---------------------------------------------------------------

def test_una_data_scritta_male_non_diventa_nessun_taglio(client):
    """Senza taglio si vede il futuro: l'opposto di quello che chiedeva chi
    ha scritto quella data."""
    risposta = client.get("/api/titolo/NVDA/fondamentali?as_of=ieri")

    assert risposta.status_code == 400
    assert "YYYY-MM-DD" in risposta.get_json()["error"]


def test_una_periodicita_inventata_viene_rifiutata(client):
    risposta = client.get("/api/titolo/NVDA/fondamentali?periodicita=mensile")

    assert risposta.status_code == 400
    assert "periodicita" in risposta.get_json()["error"]


def test_i_fondamentali_dichiarano_sempre_la_base_del_taglio(client, monkeypatch):
    monkeypatch.setattr(defeatbeta, "statements", lambda s, run_id=None: defeatbeta.Lettura(
        frame=_bilanci(), scope="X", category="statements", source="cache",
        available=True, reason="finto",
    ))
    monkeypatch.setattr(depositi, "mappa", lambda s, run_id=None: DEPOSITI)

    d = client.get("/api/titolo/X/fondamentali").get_json()["data"]

    assert d["base_del_taglio"]["source"] == REALE
    assert d["periodi_totali"] == 2
    assert set(d["prospetti"]) == set(prospetti.PROSPETTI)


def test_ricostruire_a_una_data_riduce_i_periodi(client, monkeypatch):
    monkeypatch.setattr(defeatbeta, "statements", lambda s, run_id=None: defeatbeta.Lettura(
        frame=_bilanci(), scope="X", category="statements", source="cache",
        available=True, reason="finto",
    ))
    monkeypatch.setattr(depositi, "mappa", lambda s, run_id=None: DEPOSITI)

    d = client.get("/api/titolo/X/fondamentali?as_of=2024-07-15").get_json()["data"]

    assert d["periodi_visibili"] == 1, "il trimestre di giugno era depositato ad agosto"
    assert d["prospetti"][prospetti.CONTO_ECONOMICO]["periodi"] == ["2024-03-31"]


# --- la ricostruzione a una data passata ------------------------------------
#
# Il valore di questa pagina sta in una condizione sola: cio' che mostra come
# "quello che si sapeva" deve essere davvero quello che si sapeva. Bastano due
# sedute di troppo nel taglio perche' il confronto diventi la dimostrazione che
# il metodo funziona — e sarebbe una dimostrazione falsa.

def _serie(prima_data: str, quante: int, prezzo_iniziale: float = 100.0) -> list[dict]:
    """Sedute consecutive di calendario, una al giorno, in salita di un punto."""
    inizio = date.fromisoformat(prima_data)
    return [{"data": (inizio + timedelta(days=i)).isoformat(),
             "close": prezzo_iniziale + i, "volume": 1_000_000.0}
            for i in range(quante)]


def test_il_taglio_dei_prezzi_include_la_data_scelta_e_non_una_seduta_di_piu():
    barre = _serie("2026-01-01", 10)

    prima, dopo = ricostruzione.dividi(barre, "2026-01-05")

    assert [b["data"] for b in prima] == [f"2026-01-0{i}" for i in range(1, 6)]
    assert dopo[0]["data"] == "2026-01-06"
    assert len(prima) + len(dopo) == len(barre), "nessuna seduta si perde per strada"


def test_un_orizzonte_non_ancora_maturato_vale_none_e_non_zero():
    """«Non si sa ancora» e «non si e' mosso» sono letture opposte."""
    barre = _serie("2026-01-01", 40)
    prima, dopo = ricostruzione.dividi(barre, "2026-01-01")

    esito = ricostruzione.cosa_e_successo(prima[-1]["close"], dopo, "2026-01-01")

    assert esito["rendimenti"]["30g"] is not None
    assert esito["rendimenti"]["90g"] is None
    assert esito["rendimenti"]["365g"] is None


def test_una_seduta_troppo_lontana_non_risponde_alla_domanda_fatta():
    """Il prezzo di tre mesi dopo non e' il prezzo di un anno dopo."""
    barre = _serie("2026-01-01", 100)
    prima, dopo = ricostruzione.dividi(barre, "2026-01-01")

    esito = ricostruzione.cosa_e_successo(prima[-1]["close"], dopo, "2026-01-01")

    assert esito["rendimenti"]["90g"] is not None, "c'e' una seduta a 90 giorni"
    assert esito["rendimenti"]["180g"] is None, "la piu' vicina dista 8 giorni di troppo"


def test_gli_orizzonti_maturati_non_contraddicono_i_rendimenti():
    """Il difetto visto dal vivo su NVDA: l'ultimo prezzo distava 364 giorni, il
    rendimento a un anno veniva calcolato e l'orizzonte risultava non maturato.
    Due campi della stessa risposta che si contraddicono."""
    barre = _serie("2025-08-29", 365)
    prima, dopo = ricostruzione.dividi(barre, "2025-08-29")

    esito = ricostruzione.cosa_e_successo(prima[-1]["close"], dopo, "2025-08-29")
    maturati = ricostruzione.orizzonti_maturati("2025-08-29", barre[-1]["data"])

    assert "365g" in maturati
    for orizzonte in maturati:
        assert esito["rendimenti"][orizzonte] is not None, (
            f"{orizzonte} risulta maturato ma non ha un numero")


def test_senza_sedute_dopo_il_confronto_dice_che_non_e_ancora_possibile():
    """Una data di ieri non e' un errore: e' un confronto che deve aspettare."""
    esito = ricostruzione.cosa_e_successo(100.0, [], "2026-08-30")

    assert esito["rendimenti"] == {}
    assert "non e' ancora possibile" in esito["motivo"]


def test_la_discesa_massima_dopo_si_misura_sul_prezzo_di_allora():
    barre = [{"data": "2026-01-02", "close": 50.0, "volume": 1.0},
             {"data": "2026-01-03", "close": 130.0, "volume": 1.0}]

    esito = ricostruzione.cosa_e_successo(100.0, barre, "2026-01-01")

    assert esito["discesa_massima"] == pytest.approx(-0.5)
    assert esito["salita_massima"] == pytest.approx(0.3)
    assert esito["rendimento_a_oggi"] == pytest.approx(0.3), "l'ultima, non la migliore"


def test_con_pochi_prezzi_la_lettura_tecnica_di_allora_si_ferma():
    """Una lettura costruita su venti sedute vale meno di nessuna lettura."""
    poche = _serie("2026-01-01", 10)

    misurato = ricostruzione_dati._misure_di_allora(poche)

    assert misurato["available"] is False
    assert "60" in misurato["reason"]
    assert misurato["action"]


def test_la_ricostruzione_taglia_i_bilanci_sulla_data_di_deposito(monkeypatch):
    """Il look-ahead classico: un trimestre chiuso il 31 gennaio non era pubblico
    il 1 febbraio. Tagliarlo sulla fine del periodo mostrerebbe il futuro."""
    visto = {}

    def _finti(simbolo, run_id, quando=None):
        visto["quando"] = quando
        return {"segnali": {}, "as_of": quando, "periodi_visibili": 17,
                "periodi_totali": 20, "base_del_taglio": {"source": "filing_index"}}

    monkeypatch.setattr(materiale, "segnali_fondamentali", _finti)
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({"report_date": [b["data"] for b in _serie("2026-01-01", 90)],
                            "close": [b["close"] for b in _serie("2026-01-01", 90)],
                            "volume": [1e6] * 90}),
        scope=s, category="price", source="cache", available=True, reason="finto"))

    esito = ricostruzione_dati.confronto("NVDA", "2026-02-15")

    assert visto["quando"] == "2026-02-15", "la data arriva fino al taglio dei bilanci"
    assert esito["allora"]["fondamentale"]["periodi_visibili"] == 17
    assert esito["allora"]["fondamentale"]["base_del_taglio"]["source"] == "filing_index"


def test_la_rotta_della_ricostruzione_pretende_una_data(client):
    """Senza data non c'e' niente da ricostruire, e "nessun taglio" vorrebbe
    dire mostrare tutto il futuro."""
    risposta = client.get("/api/titolo/NVDA/ricostruzione")

    assert risposta.status_code == 400
    assert "as_of" in risposta.get_json()["error"]


def test_anche_la_ricostruzione_rifiuta_una_data_scritta_male(client):
    risposta = client.get("/api/titolo/NVDA/ricostruzione?as_of=ieri")

    assert risposta.status_code == 400
    assert "YYYY-MM-DD" in risposta.get_json()["error"]


def test_una_data_prima_del_primo_prezzo_dice_da_quando_c_e_storia(client, monkeypatch):
    barre = _serie("2026-01-01", 90)
    monkeypatch.setattr(defeatbeta, "prices", lambda s, run_id=None: defeatbeta.Lettura(
        frame=pd.DataFrame({"report_date": [b["data"] for b in barre],
                            "close": [b["close"] for b in barre],
                            "volume": [1e6] * len(barre)}),
        scope=s, category="price", source="cache", available=True, reason="finto"))

    risposta = client.get("/api/titolo/NVDA/ricostruzione?as_of=2020-01-01")

    assert risposta.status_code == 404
    assert "2026-01-01" in risposta.get_json()["error"]


# --- i nomi delle voci in italiano -----------------------------------------

def test_ogni_voce_dei_prospetti_di_nvda_ha_un_nome_italiano():
    """Il dizionario copre cio' che si vede davvero. Una voce non tradotta non
    e' un guasto — torna col suo nome — ma se ne mancassero molte la tabella
    resterebbe in inglese meta' e meta', che e' peggio di tutta in inglese."""
    prese = set(voci.VOCI)

    assert len(prese) > 150, "il dizionario deve coprire i tre prospetti"
    for atteso in ("net_income", "ebit", "ebitda", "free_cash_flow",
                   "stockholders_equity", "total_debt", "operating_income"):
        assert atteso in prese, atteso


def test_una_voce_sconosciuta_torna_col_suo_nome_e_non_sparisce():
    """Un dizionario incompleto non deve peggiorare niente: senza traduzione si
    vede quello che si vedeva prima."""
    assert voci.etichetta("voce_mai_vista") == "voce mai vista"
    assert voci.spiegazione("voce_mai_vista") is None


def test_il_nome_originale_resta_accanto_a_quello_italiano(client, monkeypatch):
    """Chi confronta col bilancio depositato deve ritrovare la stessa parola."""
    monkeypatch.setattr(defeatbeta, "statements", lambda s, run_id=None: defeatbeta.Lettura(
        frame=_bilanci(), scope="X", category="statements", source="cache",
        available=True, reason="finto",
    ))
    monkeypatch.setattr(depositi, "mappa", lambda s, run_id=None: DEPOSITI)

    risposta = client.get("/api/titolo/X/fondamentali").get_json()["data"]

    voci_viste = risposta["prospetti"]["income_statement"]["voci"]
    assert voci_viste, "il finto deve avere almeno una voce di conto economico"
    for nome in voci_viste:
        assert nome in risposta["nomi"], f"{nome} non ha un'etichetta"
    # Il nome originale resta la CHIAVE: e' con quello che si cerca e si confronta.
    assert set(risposta["nomi"]) >= set(voci_viste)
