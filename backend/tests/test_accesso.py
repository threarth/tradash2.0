"""
test_accesso.py — la verifica del Blocco 10: la porta e' chiusa, e si apre solo cosi'.
# feat: se questi test non passano, il sistema non va online.

Il difetto che questo file esiste per impedire non e' teorico: prima di oggi
`POST /api/analisi/<metodo>/<simbolo>` era raggiungibile da chiunque, e **spende
soldi veri** sulle chiavi API di chi ospita. Accanto c'erano la costruzione
dell'universo (minuti di CPU e centinaia di MB di rete), la cancellazione della
watchlist e il cambio del modello, cioe' di quanto si paga.

Il test piu' importante e' il primo, ed e' STRUTTURALE: enumera le rotte che
l'applicazione registra davvero e pretende che ognuna sotto `/api/` sia chiusa,
tranne quelle nell'elenco dichiarato. Un endpoint scritto fra sei mesi lo fa
fallire finche' qualcuno non sceglie fra le due cose — ed e' la stessa forma del
controllo sul glossario del Blocco 5.
"""
import json
from datetime import UTC, datetime

import pytest

import config
from core import accesso, llm, utente
from core.db import db_session
from tests.conftest import PASSWORD_DI_PROVA, UTENTE_DI_PROVA

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401

# I metodi con cui si prova una rotta chiusa. Non basta GET: le POST sono
# proprio quelle che spendono e cancellano.
METODI = ("GET", "POST", "PUT", "DELETE", "PATCH")


def _rotte_api(app) -> list[tuple[str, str]]:
    """Ogni regola sotto `/api/`, col suo primo metodo utile.

    I segnaposti si riempiono con un valore qualunque: qui non interessa che la
    rotta funzioni, interessa che RISPONDA 401 prima ancora di provarci.
    """
    trovate = []
    for regola in app.url_map.iter_rules():
        percorso = str(regola)
        if not percorso.startswith("/api/"):
            continue
        for parte in regola.arguments:
            percorso = percorso.replace(f"<{parte}>", "x").replace(f"<path:{parte}>", "x")
            percorso = percorso.replace(f"<int:{parte}>", "1")
        metodo = next((m for m in METODI if m in regola.methods), "GET")
        trovate.append((metodo, percorso))
    return sorted(set(trovate))


# --- il test che conta ------------------------------------------------------

def test_ogni_rotta_api_e_chiusa_tranne_quelle_dichiarate(client_anonimo):
    """Si chiude per PERCORSO, non per elenco: un endpoint nuovo nasce protetto.

    Se questo test fallisce dopo che hai aggiunto una rotta, hai due strade e
    devi sceglierne una a voce: o la rotta e' privata e va bene cosi', oppure
    dev'essere pubblica e va scritta in `accesso.API_PUBBLICHE` col motivo.
    """
    rotte = _rotte_api(client_anonimo.application)
    assert len(rotte) > 30, "l'enumerazione non ha trovato le rotte: il test non misura niente"

    aperte = []
    for metodo, percorso in rotte:
        if percorso in accesso.API_PUBBLICHE:
            continue
        risposta = client_anonimo.open(percorso, method=metodo)
        if risposta.status_code != HTTP_UNAUTHORIZED:
            aperte.append(f"{metodo} {percorso} -> {risposta.status_code}")

    assert aperte == [], (
        "queste rotte rispondono a chi non ha fatto l'accesso:\n  "
        + "\n  ".join(aperte)
    )


# Le uniche famiglie di rotte che hanno una ragione strutturale per essere
# pubbliche. Tutto il resto, se compare fra le pubbliche, e' quasi certamente un
# errore — e questo test esiste per farlo notare.
#
# `/api/auth/` perche' e' la porta stessa. `/api/salute` perche' la chiedono
# nginx e systemd, che una password non ce l'hanno.
PUBBLICHE_AMMESSE = ("/api/auth/", "/api/salute")


def test_ogni_eccezione_pubblica_porta_il_suo_motivo():
    """Aprire una porta sull'internet pubblico si giustifica in una riga.

    E si giustifica anche il TIPO di porta: una rotta pubblica che non sia
    l'accesso o il controllo di salute non ha una ragione strutturale per
    esserlo, e chi ne aggiunge una deve passare da qui a voce alta.
    """
    assert accesso.API_PUBBLICHE, "l'elenco non puo' essere vuoto: il login sta li'"
    for percorso, motivo in accesso.API_PUBBLICHE.items():
        assert percorso.startswith(PUBBLICHE_AMMESSE), (
            f"{percorso} e' pubblica e non e' ne' l'accesso ne' la salute: "
            f"e' quasi certamente un errore"
        )
        assert len(motivo) > 20, f"{percorso} non ha un motivo scritto, ne ha uno accennato"


def test_la_salute_risponde_senza_accesso_e_dice_pochissimo():
    """E' l'unica rotta pubblica che tocca il database, quindi anche l'unica che
    uno sconosciuto puo' far lavorare: fa un SELECT 1 e nient'altro.

    E non dice COSA c'e' dentro. Che il servizio sia vivo non e' un segreto;
    quanti titoli ha in pancia, o dove tiene i suoi file, lo e'.
    """
    # Volutamente `client_anonimo`: e' il punto.
    pass


def test_la_salute_e_pubblica_e_minimale(client_anonimo):
    """Il controllo che nginx e systemd possono fare senza credenziali."""
    risposta = client_anonimo.get("/api/salute")

    assert risposta.status_code == HTTP_OK
    dati = risposta.get_json()["data"]
    assert dati["stato"] == "vivo"
    assert dati["avviato_il"]
    assert set(dati) == {"stato", "avviato_il"}, (
        "la salute dice se sei vivo, non cosa hai in pancia: ogni campo in piu' "
        "e' un'informazione regalata a chi non si e' presentato"
    )


def test_chi_non_e_entrato_riceve_un_motivo_non_un_muro(client_anonimo):
    """Regola 16: all'utente arriva il perche', non uno stack ne' un 500."""
    risposta = client_anonimo.get("/api/universe/stato")

    assert risposta.status_code == HTTP_UNAUTHORIZED
    corpo = risposta.get_json()
    assert corpo["success"] is False
    assert "accedere" in corpo["error"]


# --- entrare e uscire -------------------------------------------------------

def test_si_entra_e_lo_stato_lo_dice(client_anonimo):
    """Il giro completo, senza scorciatoie sulla sessione."""
    utente.crea(UTENTE_DI_PROVA, PASSWORD_DI_PROVA)

    prima = client_anonimo.get("/api/auth/stato").get_json()["data"]
    assert prima["connesso"] is False and prima["configurato"] is True

    entrata = client_anonimo.post("/api/auth/login",
                                  json={"nome": UTENTE_DI_PROVA,
                                        "password": PASSWORD_DI_PROVA})
    assert entrata.status_code == HTTP_OK
    assert entrata.get_json()["data"]["utente"] == UTENTE_DI_PROVA

    assert client_anonimo.get("/api/auth/stato").get_json()["data"]["connesso"] is True
    assert client_anonimo.get("/api/universe/stato").status_code == HTTP_OK

    client_anonimo.post("/api/auth/logout")
    assert client_anonimo.get("/api/universe/stato").status_code == HTTP_UNAUTHORIZED


def test_il_fallimento_non_dice_quale_dei_due_campi_era_sbagliato(client_anonimo):
    """Dire «nome inesistente» e' dire meta' della risposta a chi sta provando."""
    utente.crea(UTENTE_DI_PROVA, PASSWORD_DI_PROVA)

    nome_sbagliato = client_anonimo.post(
        "/api/auth/login", json={"nome": "nessuno", "password": PASSWORD_DI_PROVA})
    password_sbagliata = client_anonimo.post(
        "/api/auth/login", json={"nome": UTENTE_DI_PROVA, "password": "non e' questa"})

    assert nome_sbagliato.status_code == HTTP_UNAUTHORIZED
    assert password_sbagliata.status_code == HTTP_UNAUTHORIZED
    assert (nome_sbagliato.get_json()["error"]
            == password_sbagliata.get_json()["error"])


def test_il_cookie_e_di_sola_sessione_e_non_lo_legge_il_javascript(client_anonimo):
    """E' cio' che l'informativa dichiara, e va tenuto vero.

    Nessuna scadenza significa che muore chiudendo il browser. `HttpOnly` che un
    XSS non se lo porta via. `SameSite=Lax` che non viaggia su una POST partita
    da un altro sito — ed e' la difesa contro le richieste cross-site, dato che
    le POST qui sono tutto cio' che spende o cancella.
    """
    utente.crea(UTENTE_DI_PROVA, PASSWORD_DI_PROVA)
    risposta = client_anonimo.post("/api/auth/login",
                                   json={"nome": UTENTE_DI_PROVA,
                                         "password": PASSWORD_DI_PROVA})

    cookie = next(c for c in risposta.headers.getlist("Set-Cookie")
                  if c.startswith(config.COOKIE_SESSIONE))

    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Expires=" not in cookie and "Max-Age=" not in cookie, (
        "un cookie con scadenza sopravvive alla chiusura del browser: "
        "l'informativa direbbe il falso"
    )


def test_le_intestazioni_di_sicurezza_ci_sono_su_ogni_risposta(client_anonimo):
    """Anche su un 401: le intestazioni non dipendono dall'esito."""
    risposta = client_anonimo.get("/api/universe/stato")

    assert risposta.headers["X-Frame-Options"] == "DENY"
    assert risposta.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in risposta.headers["Content-Security-Policy"]
    assert "unsafe-eval" not in risposta.headers["Content-Security-Policy"]


# --- la password ------------------------------------------------------------

def test_la_password_non_si_puo_leggere_dal_file():
    """Nel file c'e' un hash scrypt, non la password ne' qualcosa di reversibile."""
    utente.crea(UTENTE_DI_PROVA, PASSWORD_DI_PROVA)

    testo = config.UTENTE_PATH.read_text(encoding="utf-8")
    dati = json.loads(testo)

    assert PASSWORD_DI_PROVA not in testo
    assert dati["password_hash"].startswith("scrypt:")
    assert "password" not in {k for k in dati if k != "password_hash"}


def test_cambiare_password_fa_scadere_le_sessioni_aperte(client):
    """Senza questo, cambiare password sarebbe un gesto simbolico.

    Il cookie e' firmato ma stateless: chi ne ha gia' uno resterebbe dentro per
    sempre, che e' esattamente cio' che si cambia la password per evitare. Il
    cookie porta un numero di generazione, e cambiare password lo fa salire.
    """
    assert client.get("/api/universe/stato").status_code == HTTP_OK

    cambio = client.post("/api/auth/password",
                         json={"vecchia": PASSWORD_DI_PROVA, "nuova": "una-nuova-password"})
    assert cambio.status_code == HTTP_OK
    assert cambio.get_json()["data"]["generazione"] == 2

    assert client.get("/api/universe/stato").status_code == HTTP_UNAUTHORIZED, (
        "la sessione di chi ha cambiato password deve scadere come tutte le altre"
    )


def test_una_password_sbagliata_o_troppo_corta_non_passa(client):
    """Il motivo e' scritto, e le due cose si distinguono."""
    sbagliata = client.post("/api/auth/password",
                            json={"vecchia": "non e' questa", "nuova": "abbastanza-lunga"})
    assert sbagliata.status_code == HTTP_BAD_REQUEST
    assert "attuale" in sbagliata.get_json()["error"]

    corta = client.post("/api/auth/password",
                        json={"vecchia": PASSWORD_DI_PROVA, "nuova": "ab"})
    assert corta.status_code == HTTP_BAD_REQUEST
    assert str(config.PASSWORD_LUNGHEZZA_MINIMA) in corta.get_json()["error"]


def test_il_freno_scatta_dopo_i_tentativi_dichiarati(client_anonimo, monkeypatch):
    """Una password di sei caratteri regge finche' provarle tutte costa tempo."""
    utente.crea(UTENTE_DI_PROVA, PASSWORD_DI_PROVA)
    monkeypatch.setattr(accesso, "_tentativi", {})

    for _ in range(config.ACCESSO_TENTATIVI_PRIMA_DEL_FRENO):
        risposta = client_anonimo.post("/api/auth/login",
                                       json={"nome": UTENTE_DI_PROVA, "password": "no"})
        assert "non corretti" in risposta.get_json()["error"]

    # Il tentativo successivo fa scattare l'attesa...
    client_anonimo.post("/api/auth/login", json={"nome": UTENTE_DI_PROVA, "password": "no"})
    # ...e da qui in poi nemmeno la password GIUSTA passa, finche' non si aspetta.
    frenato = client_anonimo.post("/api/auth/login",
                                  json={"nome": UTENTE_DI_PROVA,
                                        "password": PASSWORD_DI_PROVA})
    assert "troppi tentativi" in frenato.get_json()["error"]


# --- il consenso ------------------------------------------------------------

def test_il_consenso_si_salva_sul_server_e_torna_nello_stato(client):
    """Ricordare in `localStorage` il rifiuto di `localStorage` sarebbe la prima
    cosa che quel rifiuto vieta."""
    assert client.get("/api/auth/stato").get_json()["data"]["consenso"] is None

    client.put("/api/auth/consenso", json={"preferenze": False})

    consenso = client.get("/api/auth/stato").get_json()["data"]["consenso"]
    assert consenso["preferenze"] is False
    assert consenso["deciso_il"]
    assert json.loads(config.UTENTE_PATH.read_text(encoding="utf-8"))["consenso"]


def test_il_consenso_vuole_un_si_o_un_no_esplicito(client):
    """Un campo mancante non e' un rifiuto: e' una domanda senza risposta."""
    risposta = client.put("/api/auth/consenso", json={})
    assert risposta.status_code == HTTP_BAD_REQUEST
    assert "preferenze" in risposta.get_json()["error"]


def test_lo_stato_dichiara_cosa_viene_salvato_nel_browser(client_anonimo):
    """L'elenco lo compone il BACKEND: scritto a mano nella pagina, invecchierebbe."""
    dati = client_anonimo.get("/api/auth/stato").get_json()["data"]["cosa_si_salva"]

    assert dati["tracciamento"] is False
    assert dati["terze_parti"] == []
    assert len(dati["cookie"]) == 1, "se ne aggiungi uno, l'informativa deve saperlo"
    assert dati["cookie"][0]["rifiutabile"] is False
    assert len(dati["preferenze"]) == 4


# --- il tetto di spesa ------------------------------------------------------

def _spendi(quanto: float) -> None:
    """Scrive una chiamata gia' pagata, come farebbe una analisi vera.

    L'istante si scrive nella STESSA forma del codice vero — ISO 8601 con lo
    scarto di fuso — perche' la somma di oggi confronta due stringhe. Con
    `datetime('now')` di SQLite, che usa lo spazio al posto della T, il
    confronto cadeva e il tetto risultava sempre lontanissimo: il test sarebbe
    passato dicendo «sotto il tetto» per il motivo sbagliato.
    """
    adesso = datetime.now(UTC).isoformat(timespec="seconds")
    with db_session() as conn:
        conn.execute(
            "INSERT INTO llm_calls (modello, fase, token_entrata, token_uscita, "
            "costo_usd, status, called_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("gpt-5.5", "prova", 100, 100, quanto, "ok", adesso),
        )


def test_il_tetto_di_spesa_ferma_prima_di_chiamare(monkeypatch):
    """L'accesso tiene fuori gli estranei, questo tiene fuori i nostri errori.

    Si ferma PRIMA di costruire il client: un ciclo impazzito non deve nemmeno
    arrivare a toccare il fornitore.
    """
    monkeypatch.setattr(config, "LLM_TETTO_GIORNALIERO_USD", 2.0)
    _spendi(2.5)

    with pytest.raises(llm.TettoSuperato) as errore:
        llm.chiedi("prova", "sistema", "messaggio")

    messaggio = str(errore.value)
    assert "2.50" in messaggio and "2.00" in messaggio, "deve dire quanto e quale tetto"
    assert "mezzanotte" in messaggio, "e quando riparte"


def test_sotto_il_tetto_non_ferma_niente(monkeypatch):
    """Un limite che scatta in anticipo e' peggio di nessun limite: blocca il lavoro
    vero e insegna a disattivarlo."""
    monkeypatch.setattr(config, "LLM_TETTO_GIORNALIERO_USD", 10.0)
    _spendi(2.5)

    assert llm.speso_oggi() == pytest.approx(2.5)
    # Non arriva al fornitore per un'altra ragione — nessuna chiave nella suite —
    # ma l'importante e' che NON sia il tetto a fermarlo.
    with pytest.raises(llm.LlmNonDisponibile) as errore:
        llm.chiedi("prova", "sistema", "messaggio")
    assert not isinstance(errore.value, llm.TettoSuperato)


def test_un_tetto_a_zero_significa_nessun_tetto(monkeypatch):
    """Chi lo spegne deve poterlo spegnere, e in modo evidente."""
    monkeypatch.setattr(config, "LLM_TETTO_GIORNALIERO_USD", 0.0)
    _spendi(999.0)

    with pytest.raises(llm.LlmNonDisponibile) as errore:
        llm.chiedi("prova", "sistema", "messaggio")
    assert not isinstance(errore.value, llm.TettoSuperato)
