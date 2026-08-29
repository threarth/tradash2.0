"""
test_blocco0.py — la verifica del Blocco 0, scritta prima del codice che la deve passare.
# feat: se questi test non passano, non si va al Blocco 1.

La verifica dichiarata nel PIANO.md e' una sola frase: "un lavoro finto parte,
si vede in elenco, si ferma con Stop, e il log mostra ogni chiamata con la
provenienza valorizzata". Qui e' spezzata nei suoi pezzi verificabili.
"""
import threading
import time

import pytest

from core import calls, registry, freshness

# Un lavoro finto abbastanza lungo da poter essere fermato a meta'.
PASSI_LAVORO_FINTO = 50
PAUSA_PER_PASSO_S = 0.02
TIMEOUT_ATTESA_S = 5.0


def _attendi(condizione, timeout: float = TIMEOUT_ATTESA_S) -> bool:
    """Aspetta che una condizione diventi vera, senza dormire a caso."""
    scadenza = time.monotonic() + timeout
    while time.monotonic() < scadenza:
        if condizione():
            return True
        time.sleep(PAUSA_PER_PASSO_S / 2)
    return False


def _lavoro_finto(passi: int, visto: dict) -> None:
    """Lavoro di prova: avanza a passi, controllando a ogni giro se deve fermarsi."""
    with registry.job("prova", "lavoro finto", total=passi) as lavoro:
        visto["run_id"] = lavoro.run_id
        for indice in range(passi):
            time.sleep(PAUSA_PER_PASSO_S)
            lavoro.advance(detail=f"passo {indice}")
        visto["completato"] = True


# --- 1. il lavoro si vede e si ferma ---------------------------------------

def test_il_lavoro_compare_in_elenco_e_si_ferma():
    """Un lavoro in corso e' visibile, riceve lo Stop e si ferma prima della fine."""
    visto: dict = {}
    thread = threading.Thread(target=_lavoro_finto, args=(PASSI_LAVORO_FINTO, visto))
    thread.start()

    assert _attendi(lambda: bool(registry.active())), "il lavoro non e' mai comparso in elenco"
    attivi = registry.active()
    assert len(attivi) == 1
    assert attivi[0]["kind"] == "prova"

    consegnato, motivo = registry.request_stop(attivi[0]["run_id"])
    assert consegnato is True and motivo is None

    thread.join(timeout=TIMEOUT_ATTESA_S)
    assert not thread.is_alive(), "il lavoro non si e' fermato"
    assert visto.get("completato") is not True, "il lavoro e' arrivato in fondo nonostante lo Stop"
    assert registry.active() == [], "il lavoro fermato risulta ancora attivo"


def test_lo_stop_su_un_lavoro_inesistente_spiega_perche():
    """Un fallimento porta sempre il motivo, mai un None silenzioso."""
    consegnato, motivo = registry.request_stop("run_id_che_non_esiste")
    assert consegnato is False
    assert "nessun lavoro attivo" in motivo


def test_il_lavoro_fermato_resta_nella_storia_con_il_suo_esito():
    """Chi si ferma lascia traccia: la cronologia dice `stopped`, non sparisce."""
    visto: dict = {}
    thread = threading.Thread(target=_lavoro_finto, args=(PASSI_LAVORO_FINTO, visto))
    thread.start()
    assert _attendi(lambda: bool(registry.active()))
    registry.request_stop(registry.active()[0]["run_id"])
    thread.join(timeout=TIMEOUT_ATTESA_S)

    from core.db import db_read
    with db_read() as conn:
        riga = conn.execute("SELECT * FROM jobs WHERE run_id = ?", (visto["run_id"],)).fetchone()

    assert riga["status"] == registry.STATUS_STOPPED
    assert riga["ended_at"] is not None
    assert 0 < riga["done"] < PASSI_LAVORO_FINTO


# --- 2. ogni chiamata e' loggata, con la provenienza ------------------------

def test_una_chiamata_di_rete_lascia_una_riga_con_provenienza_rete():
    """Il caso base: dato preso dalla rete, riga con `source = network`."""
    with calls.track("defeatbeta", "stock_prices", symbol="AAPL") as chiamata:
        chiamata.from_network()

    righe = calls.recent(limit=10)
    assert len(righe) == 1
    assert righe[0]["source"] == calls.SOURCE_NETWORK
    assert righe[0]["provider"] == "defeatbeta"
    assert righe[0]["symbol"] == "AAPL"
    assert righe[0]["status"] == calls.STATUS_OK


def test_la_stessa_lettura_due_volte_distingue_rete_da_cache():
    """La domanda per cui il log esiste: e' arrivato dalla rete o era in cache?"""
    with calls.track("defeatbeta", "stock_prices", symbol="MU") as prima:
        prima.from_network()
    with calls.track("defeatbeta", "stock_prices", symbol="MU") as seconda:
        seconda.from_cache()

    conteggi = calls.summary()
    assert conteggi[calls.SOURCE_NETWORK] == 1
    assert conteggi[calls.SOURCE_CACHE] == 1


def test_una_chiamata_fallita_viene_loggata_e_l_errore_risale():
    """Un fallimento silenzioso e' peggio di uno rumoroso: la riga c'e' e l'eccezione risale."""
    with pytest.raises(ValueError):
        with calls.track("defeatbeta", "stock_statement", symbol="GLW") as chiamata:
            chiamata.from_network()
            raise ValueError("parquet illeggibile")

    riga = calls.recent(limit=1)[0]
    assert riga["status"] == calls.STATUS_ERROR
    assert "ValueError" in riga["error_msg"]


def test_chi_non_dichiara_la_provenienza_non_viene_zittito():
    """La provenienza dimenticata resta visibile come `undeclared`, non sparisce."""
    with calls.track("defeatbeta", "stock_news", symbol="INTC"):
        pass

    riga = calls.recent(limit=1)[0]
    assert riga["source"] == calls.SOURCE_UNDECLARED


def test_nessuna_chiamata_del_blocco_0_resta_non_dichiarata():
    """Il controllo che vale per tutto il progetto: zero righe `undeclared` fra le nostre."""
    with calls.track("defeatbeta", "stock_profile", symbol="AAPL") as chiamata:
        chiamata.from_network()
    with calls.track("locale", "watchlist") as chiamata:
        chiamata.from_local()

    assert calls.summary().get(calls.SOURCE_UNDECLARED, 0) == 0


def test_la_chiamata_dentro_un_lavoro_porta_il_suo_run_id():
    """Le chiamate si possono ricondurre al lavoro che le ha fatte."""
    with registry.job("prova", "lavoro con chiamate", total=1) as lavoro:
        with calls.track("defeatbeta", "stock_prices", symbol="CEG",
                         run_id=lavoro.run_id) as chiamata:
            chiamata.from_network()
        run_id = lavoro.run_id

    assert len(calls.recent(limit=10, run_id=run_id)) == 1


# --- 3. la freschezza si chiede per categoria ------------------------------

def test_un_dato_mai_preso_va_richiesto_e_il_motivo_lo_dice():
    """Prima risposta possibile: non ce l'abbiamo."""
    serve, motivo = freshness.should_fetch("AAPL", "price")
    assert serve is True
    assert "mai preso" in motivo


def test_un_dato_appena_preso_non_si_richiede_e_il_motivo_lo_dice():
    """Il rifiuto porta il motivo: chi legge deve sapere PERCHE' non si e' andati in rete."""
    freshness.mark_fetched("AAPL", "price")
    serve, motivo = freshness.should_fetch("AAPL", "price")
    assert serve is False
    assert "fresco" in motivo


def test_categorie_diverse_hanno_scadenze_diverse():
    """Il difetto che il TTL per categoria esiste per impedire: prezzo e profilo
    non possono invecchiare alla stessa velocita'."""
    assert freshness.ttl_for("price") < freshness.ttl_for("profile")


def test_la_freschezza_di_una_categoria_non_parla_per_un_altra():
    """Il guard sta sul dato che mostri, mai su un campo vicino: e' il difetto
    che teneva un prezzo di undici giorni prima spacciato per quello di oggi."""
    freshness.mark_fetched("SNDK", "profile")

    serve_prezzo, _ = freshness.should_fetch("SNDK", "price")
    serve_profilo, _ = freshness.should_fetch("SNDK", "profile")

    assert serve_prezzo is True, "il profilo fresco ha zittito la richiesta di prezzo"
    assert serve_profilo is False


def test_una_categoria_non_dichiarata_prende_il_ttl_cortissimo():
    """Una categoria dimenticata deve dare fastidio, non passare inosservata."""
    import config
    assert freshness.ttl_for("categoria_inventata") == config.FRESHNESS_TTL_UNKNOWN_S


# --- 4. gli endpoint rispondono davvero ------------------------------------

def test_endpoint_active_vede_il_lavoro_e_lo_stop_lo_ferma(client):
    """La verifica del Blocco 0 fatta come la farebbe l'utente: via HTTP."""
    visto: dict = {}
    thread = threading.Thread(target=_lavoro_finto, args=(PASSI_LAVORO_FINTO, visto))
    thread.start()
    assert _attendi(lambda: bool(registry.active()))

    risposta = client.get("/api/ops/active").get_json()
    assert risposta["success"] is True
    assert len(risposta["data"]) == 1
    run_id = risposta["data"][0]["run_id"]

    assert client.post(f"/api/ops/stop/{run_id}").get_json()["success"] is True
    thread.join(timeout=TIMEOUT_ATTESA_S)

    assert client.get("/api/ops/active").get_json()["data"] == []


def test_endpoint_stop_su_run_id_inesistente_risponde_404_col_motivo(client):
    """L'errore arriva come motivo leggibile, non come corpo vuoto."""
    risposta = client.post("/api/ops/stop/inesistente")
    assert risposta.status_code == 404
    corpo = risposta.get_json()
    assert corpo["success"] is False
    assert "nessun lavoro attivo" in corpo["error"]


def test_endpoint_calls_mostra_le_chiamate_e_il_riepilogo(client):
    """Il log e' interrogabile dal frontend, con il conteggio per provenienza."""
    with calls.track("defeatbeta", "stock_prices", symbol="AMD") as chiamata:
        chiamata.from_network()
    with calls.track("defeatbeta", "stock_prices", symbol="AMD") as chiamata:
        chiamata.from_cache()

    elenco = client.get("/api/calls?limit=10").get_json()
    assert elenco["success"] is True
    assert len(elenco["data"]) == 2

    riepilogo = client.get("/api/calls/summary").get_json()["data"]
    assert riepilogo["per_provenienza"][calls.SOURCE_NETWORK] == 1
    assert riepilogo["per_provenienza"][calls.SOURCE_CACHE] == 1
    assert riepilogo["non_dichiarate"] == 0


def test_endpoint_calls_rifiuta_un_limite_assurdo(client):
    """Ogni input esterno e' validato prima dell'uso."""
    risposta = client.get("/api/calls?limit=999999")
    assert risposta.status_code == 400
    assert risposta.get_json()["success"] is False


def test_l_avvio_non_fa_partire_nulla_da_solo(client):
    """La regola 7 verificata: creare l'app non produce una sola chiamata."""
    assert calls.recent(limit=10) == []
    assert registry.active() == []
