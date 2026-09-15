"""
test_allarmi.py — il sistema DICE cosa e' vecchio, e non fa niente.
# feat: la verifica della scelta dichiarata dall'utente il 15/09/2026.

Niente scheduler, niente ricostruzioni automatiche. Se l'anagrafica ha
quattordici giorni si vede una pastiglia, e a premere il pulsante sei tu.

Il test che conta di piu' e' quello che verifica il NON fare: chiedere lo stato
della freschezza non deve produrre nemmeno una riga nel registro delle chiamate,
perche' se ne producesse una vorrebbe dire che e' andato a prendere qualcosa.
"""
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import config
from core import freshness
from core.db import db_read, db_session
from core.schema import GLOBAL_SCOPE
from data import allarmi, defeatbeta, preset


def _invecchia(categoria: str, giorni: float) -> None:
    """Scrive nella freschezza un istante di N giorni fa, per farla scadere."""
    quando = datetime.now(UTC) - timedelta(days=giorni)
    with db_session() as conn:
        conn.execute(
            "INSERT INTO freshness (scope, category, fetched_at) VALUES (?, ?, ?) "
            "ON CONFLICT (scope, category) DO UPDATE SET fetched_at = excluded.fetched_at",
            (GLOBAL_SCOPE, categoria, quando.isoformat(timespec="seconds")),
        )


# Un mercato finto minimo: due titoli investibili su quattordici mesi. Serve
# solo perche' `rigioca_tutti()` abbia qualcosa su cui girare — i verdetti che
# ne escono sono privi di significato, e non e' quello che questi test misurano.
AZIONI = 20_000_000
VOLUME = 50_000


def _storico_finto() -> None:
    mesi = [f"2025-{m:02d}" for m in range(1, 13)] + ["2026-01", "2026-02"]
    righe = []
    for simbolo, partenza in (("ALFA", 100.0), ("BETA", 50.0)):
        for indice, mese in enumerate(mesi):
            righe.append((simbolo, mese, partenza + indice, VOLUME, AZIONI))
    with db_session() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO universe_prezzi_mensili "
            "(symbol, mese, chiusura, volume_medio, azioni, built_at) "
            "VALUES (?, ?, ?, ?, ?, '2026-09-15')", righe)


def _quante_chiamate() -> int:
    with db_read() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM calls").fetchone()["n"]


# --- il non fare -----------------------------------------------------------

def test_chiedere_cosa_e_vecchio_non_fa_partire_niente():
    """E' il cuore della scelta: l'allarme guarda, non agisce.

    Se questa chiamata producesse una riga nel registro vorrebbe dire che e'
    andata a prendere qualcosa — e da li' a ricostruire da soli il passo e'
    corto. Nel vecchio tradash una scheda del browser dimenticata ha rilanciato
    cinquecento download al riavvio del backend.
    """
    prima = _quante_chiamate()

    allarmi.stato()

    assert _quante_chiamate() == prima, (
        "l'allarme ha registrato una chiamata: sta facendo qualcosa invece di dirlo"
    )


def test_niente_scheduler_nel_codice_di_produzione():
    """La regola scritta, verificata sui sorgenti invece che sulla parola.

    Un thread periodico o un timer aggiunto fra sei mesi fa fallire questo test
    finche' qualcuno non lo dichiara a voce.
    """
    radice = Path(config.BASE_DIR)
    vietati = re.compile(r"\b(APScheduler|crontab|schedule\.every|threading\.Timer)\b")
    colpevoli = []
    for cartella in ("api", "core", "data", "domain"):
        for file in (radice / cartella).rglob("*.py"):
            if vietati.search(file.read_text(encoding="utf-8")):
                colpevoli.append(file.name)

    assert not colpevoli, f"qualcosa gira da solo: {colpevoli}"


# --- l'allarme dice motivo e azione ----------------------------------------

def test_una_categoria_scaduta_compare_col_motivo_e_con_cosa_fare():
    """Regola 5: mai un booleano nudo. «vecchio: True» non dice a nessuno che fare."""
    _invecchia(defeatbeta.CATEGORY_ANAGRAFICA, giorni=20)

    stato = allarmi.stato()
    riga = next(r for r in stato["vecchi"]
                if r["categoria"] == defeatbeta.CATEGORY_ANAGRAFICA)

    assert riga["vecchio"] is True
    assert riga["eta_giorni"] >= 19
    assert riga["limite_giorni"] == 14, "il limite dichiarato e' quello scelto"
    assert riga["reason"], "senza motivo e' un allarme che non si puo' valutare"
    assert "Universo" in riga["azione"], "l'azione e' il nome del pulsante"


def test_una_categoria_fresca_non_suona():
    """Un allarme che suona sempre e' un allarme che si impara a ignorare."""
    freshness.mark_fetched_global(defeatbeta.CATEGORY_ANAGRAFICA)

    riga = next(r for r in allarmi.stato()["tutti"]
                if r["categoria"] == defeatbeta.CATEGORY_ANAGRAFICA)

    assert riga["vecchio"] is False
    assert riga["eta_giorni"] < 1


def test_il_conteggio_e_quello_che_la_pastiglia_mostra():
    """Zero e' un'informazione anche lui: vuol dire che non c'e' niente da fare."""
    for categoria, _, _ in allarmi.SORVEGLIATI:
        freshness.mark_fetched_global(categoria)
    _storico_finto()
    preset.rigioca_tutti()

    assert allarmi.stato()["quanti"] == 0

    _invecchia(defeatbeta.CATEGORY_MERCATO, giorni=3)
    _invecchia(defeatbeta.CATEGORY_FONDAMENTALI, giorni=3)

    assert allarmi.stato()["quanti"] == 2


def test_la_nota_dice_che_non_parte_niente():
    """E' la domanda che chi vede una pastiglia si fa subito dopo."""
    nota = allarmi.stato()["nota"]

    assert "si ricostruisce da sola" in nota
    assert "tua" in nota


# --- i verdetti dei preset invecchiano, e lo dicono ------------------------

def test_senza_file_i_preset_dicono_che_non_sono_mai_stati_rigiocati():
    """Regola 5 di nuovo: un preset senza verdetto non e' un preset neutro."""
    config.PRESET_VERDETTI_PATH.unlink(missing_ok=True)

    stato = preset.con_verdetto()

    assert stato["da_rimisurare"] is True
    assert "mai stati rigiocati" in " ".join(stato["perche"])
    assert stato["azione"] == "python manage.py preset"
    assert all(p["verdetto"] is None for p in stato["preset"])


def test_i_verdetti_invecchiano_se_cambiano_le_soglie_del_paragone():
    """Il difetto che il file dei verdetti esiste per impedire.

    Prima i numeri stavano scritti a mano accanto ai criteri: cambiare una
    soglia li rendeva falsi senza che niente lo dicesse.
    """
    _storico_finto()
    preset.rigioca_tutti()
    assert preset.con_verdetto()["da_rimisurare"] is False

    documento = json.loads(config.PRESET_VERDETTI_PATH.read_text(encoding="utf-8"))
    documento["soglie"]["capitalizzazione_minima"] = 1
    config.PRESET_VERDETTI_PATH.write_text(json.dumps(documento), encoding="utf-8")

    stato = preset.con_verdetto()
    assert stato["da_rimisurare"] is True
    assert "soglia" in " ".join(stato["perche"])


def test_i_verdetti_invecchiano_se_arrivano_mesi_di_dati_nuovi():
    """L'altro modo di invecchiare, quello che non si vede: i dati vanno avanti."""
    _storico_finto()
    preset.rigioca_tutti()

    documento = json.loads(config.PRESET_VERDETTI_PATH.read_text(encoding="utf-8"))
    documento["finestra_dati"]["al"] = "2019-01"
    config.PRESET_VERDETTI_PATH.write_text(json.dumps(documento), encoding="utf-8")

    perche = " ".join(preset.con_verdetto()["perche"])
    assert "si fermano a 2019-01" in perche


def test_il_verdetto_e_calcolato_non_scritto_a_mano():
    """`forma` e `vince` si ricavano dai tre orizzonti: nessuna prosa da aggiornare."""
    _storico_finto()
    documento = preset.rigioca_tutti()

    for nome, verdetto in documento["verdetti"].items():
        assert set(verdetto["orizzonti"]) == {"3", "6", "12"}, nome
        assert verdetto["forma"] in (
            preset.VINCE_SEMPRE, preset.LENTO, preset.PERDE_SEMPRE,
            preset.MISTO, preset.NON_GIUDICABILE), nome
        assert verdetto["vince"] in (True, False, None), nome


# --- la rotta ---------------------------------------------------------------

def test_la_rotta_della_freschezza(client):
    """La pagina la chiede all'apertura: dev'essere economica e parlante."""
    _invecchia(defeatbeta.CATEGORY_MERCATO, giorni=5)

    dati = client.get("/api/ops/freschezza").get_json()["data"]

    assert dati["quanti"] >= 1
    vecchio = next(r for r in dati["vecchi"]
                   if r["categoria"] == defeatbeta.CATEGORY_MERCATO)
    assert vecchio["azione"] == "Universo → Prezzi"
    assert dati["nota"]


# --- quando la fonte cade -----------------------------------------------

def test_la_fonte_giu_diventa_un_motivo_non_un_500(client, monkeypatch):
    """Il difetto, trovato mentre Defeatbeta era davvero in avaria.

    `DefeatbetaUnavailable` risaliva fino a Flask, che rispondeva 500 con uno
    stack trace: ventiquattro rotte su ventisei di `api/titolo.py` non lo
    catturavano. Bastava un quarto d'ora di problemi della fonte perche' la
    scheda di un titolo mostrasse un errore illeggibile invece di dire cosa
    stava succedendo.
    """
    def _giu(*args, **kwargs):
        raise defeatbeta.DefeatbetaUnavailable(
            "HTTP Error: HTTP GET error on stock_profile.parquet (HTTP 404)")

    monkeypatch.setattr(defeatbeta, "profile", _giu)

    risposta = client.get("/api/titolo/NVDA")

    assert risposta.status_code == 503, "non e' un errore nostro: e' la fonte"
    errore = risposta.get_json()["error"]
    assert "Defeatbeta" in errore, "va detto CHI non risponde"
    assert "non e' un guasto di tradash" in errore.lower()
    assert "404" not in errore and "parquet" not in errore, (
        "il dettaglio tecnico resta nel log del server, non va all'utente"
    )


def test_col_provider_giu_quello_che_e_gia_locale_continua_a_funzionare(client, monkeypatch):
    """La distinzione che rende utile il messaggio: non e' tutto rotto.

    Universo, watchlist e scanner leggono da SQLite e non si accorgono di
    niente; solo cio' che ha bisogno della rete si ferma.
    """
    def _giu(*args, **kwargs):
        raise defeatbeta.DefeatbetaUnavailable("la fonte non risponde")

    for nome in ("profile", "prices", "sec_filings", "news"):
        monkeypatch.setattr(defeatbeta, nome, _giu)

    assert client.get("/api/universe/stato").status_code == 200
    assert client.get("/api/watchlist").status_code == 200
    assert client.get("/api/scanner/criteri").status_code == 200
    assert client.get("/api/ops/freschezza").status_code == 200
