"""
test_isolamento.py — i test girano in fase di sviluppo e non toccano l'uso reale.
# feat (Blocco 0, rivisto): la separazione e' verificata, non promessa.

Il vecchio sistema aveva la promessa e non la verifica: un docstring diceva che
`TRADASH_OFFLINE` copriva i provider, ed era falso; la suite mandava backfill
yfinance veri per mesi senza che nessuno se ne accorgesse. Qui ogni pezzo della
separazione ha il suo test.
"""
import re
import socket
from pathlib import Path

import pytest

import config
from core import db
from tests.conftest import ReteVietata

# Cartelle del codice di produzione: tutto tranne i test.
SORGENTI_PRODUZIONE = ("core", "api", "data")
FILE_PRODUZIONE_RADICE = ("app.py", "config.py", "manage.py")

# Frasi che nel codice di produzione non devono comparire: sono i rami che
# fanno comportare l'applicazione diversamente quando "sa" di essere sotto test.
SPIE_DI_CODICE_PER_I_TEST = ("PYTEST_CURRENT_TEST", "if TESTING", "IS_TEST", "pytest")

# Il guard di db.py e' l'unico posto autorizzato a nominare PYTEST_CURRENT_TEST.
FILE_ESENTATO_DAL_CONTROLLO = "db.py"


def _file_di_produzione() -> list[Path]:
    """Tutti i sorgenti dell'applicazione, esclusi i test."""
    radice = Path(config.BASE_DIR)
    trovati = [radice / nome for nome in FILE_PRODUZIONE_RADICE]
    for cartella in SORGENTI_PRODUZIONE:
        trovati.extend(sorted((radice / cartella).rglob("*.py")))
    return [f for f in trovati if f.exists()]


# --- la rete e' spenta, sotto qualunque libreria ---------------------------

def test_la_rete_e_spenta_per_default():
    """Un test che prova a uscire non ottiene silenzio, ma un errore parlante."""
    with pytest.raises(ReteVietata):
        socket.create_connection(("example.com", 80), timeout=1)


def test_anche_la_risoluzione_dei_nomi_e_spenta():
    """Bloccare solo `connect` lascerebbe passare il DNS, che e' gia' traffico."""
    with pytest.raises(ReteVietata):
        socket.getaddrinfo("example.com", 80)


@pytest.mark.network
def test_il_marcatore_riapre_la_rete():
    """La via d'uscita esiste ed e' esplicita: `@pytest.mark.network`.

    Per dimostrarlo senza uscire davvero su internet, il test parla con un
    socket in ascolto che apre lui stesso su localhost.
    """
    ascoltatore = socket.socket()
    ascoltatore.bind(("127.0.0.1", 0))
    ascoltatore.listen(1)
    try:
        with socket.create_connection(ascoltatore.getsockname(), timeout=1):
            pass
    finally:
        ascoltatore.close()


# --- il database dell'uso reale e' irraggiungibile dalla suite -------------

def test_la_suite_gira_su_un_database_usa_e_getta():
    """Non e' il database dell'uso reale, ed e' in una cartella temporanea."""
    assert config.DB_PATH != config.PRODUCTION_DB_PATH
    assert "tradash2_test_" in str(config.DB_PATH)


def test_aprire_il_database_reale_dalla_suite_viene_rifiutato(monkeypatch):
    """Il difetto chiuso qui: la vecchia suite scriveva sul database vero.

    La difesa non e' l'attenzione di chi scrive il prossimo test: e' un rifiuto
    nel punto in cui passano tutte le connessioni.
    """
    monkeypatch.setattr(config, "DB_PATH", config.PRODUCTION_DB_PATH)
    with pytest.raises(RuntimeError, match="database dell'uso reale"):
        db.connect()


# --- il codice di produzione non sa che i test esistono --------------------

def test_il_codice_di_produzione_non_importa_i_test():
    """Una dipendenza in questa direzione fa entrare i test nell'uso reale."""
    colpevoli = [
        f.name for f in _file_di_produzione()
        if "from tests" in f.read_text(encoding="utf-8")
        or "import tests" in f.read_text(encoding="utf-8")
    ]
    assert colpevoli == [], f"il codice di produzione importa i test: {colpevoli}"


def test_il_codice_di_produzione_non_si_comporta_diversamente_sotto_test():
    """Nessun ramo `if TESTING:`.

    Un'applicazione che sa di essere sotto test e' un'applicazione di cui i
    test non dimostrano niente. L'unica eccezione e' il guard di db.py, che non
    cambia comportamento: rifiuta e basta.
    """
    colpevoli = []
    for sorgente in _file_di_produzione():
        if sorgente.name == FILE_ESENTATO_DAL_CONTROLLO:
            continue
        testo = sorgente.read_text(encoding="utf-8")
        for spia in SPIE_DI_CODICE_PER_I_TEST:
            if spia in testo:
                colpevoli.append(f"{sorgente.name}: {spia}")
    assert colpevoli == [], f"il codice di produzione conosce i test: {colpevoli}"


def test_l_applicazione_all_avvio_non_fa_lavoro_sui_dati():
    """Il difetto misurato sul vecchio sistema: `create_app()` faceva cose.

    Un UPDATE su tutti gli universi, tre ALTER TABLE e un ripopolamento di temi
    giravano a OGNI costruzione dell'app — 88 volte per giro di suite. Qui
    `create_app` fa due cose: applica lo schema e registra i blueprint.
    """
    sorgente = (Path(config.BASE_DIR) / "app.py").read_text(encoding="utf-8")
    for istruzione in ("UPDATE", "INSERT", "ALTER TABLE", "DELETE"):
        assert istruzione not in sorgente, f"app.py contiene {istruzione}"


# --- ogni percorso configurabile e' dirottato, senza doverselo ricordare ----

def test_ogni_percorso_dell_uso_reale_e_dirottato_nella_suite():
    """Il difetto che questo test esiste per impedire, e che e' gia' successo:
    ho aggiunto `TRADASH2_REFERTI` a config e ho dimenticato di aggiungerlo al
    conftest. Tre referti di prova, con simbolo «AAA», sono finiti nel FILE VERO
    dei referti — quello che da oggi e' la copia di sicurezza di analisi pagate.

    L'isolamento era una lista da tenere allineata a un'altra, ed e' la forma di
    difetto che questo progetto incontra piu' spesso. Adesso l'allineamento si
    verifica invece di ricordarselo.
    """
    sorgente = (Path(config.BASE_DIR) / "config.py").read_text(encoding="utf-8")
    lette = set(re.findall(r'os\.environ\.get\("(TRADASH2_[A-Z_]+)"', sorgente))

    conftest = (Path(config.BASE_DIR) / "tests" / "conftest.py").read_text(encoding="utf-8")
    dirottate = set(re.findall(r'os\.environ\["(TRADASH2_[A-Z_]+)"\]', conftest))

    dimenticate = sorted(lette - dirottate - VARIABILI_SENZA_PERCORSO)
    assert not dimenticate, (
        f"config legge {dimenticate} ma il conftest non le dirotta: la suite "
        f"scriverebbe sui dati veri"
    )


# Le variabili che NON puntano a un percorso: dirottarle non avrebbe senso.
VARIABILI_SENZA_PERCORSO = {"TRADASH2_MODELLO", "TRADASH2_SFORZO"}


def test_i_percorsi_della_suite_stanno_tutti_nella_cartella_temporanea():
    """Non basta che siano dirottati: devono finire dove si buttano."""
    for percorso in (config.DB_PATH, config.WATCHLIST_PATH, config.REFERTI_PATH,
                     config.GRAFICI_PATH, config.FILING_DIR):
        assert "tradash2_test_" in str(percorso), percorso
