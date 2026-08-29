"""
conftest.py — la suite gira in fase di sviluppo e non puo' toccare l'uso reale.
# feat (Blocco 0, rivisto): separazione strutturale fra test e uso.

Quattro difetti del vecchio sistema, chiusi qui uno per uno:

1. **la suite scriveva sul database vero** — qui `TRADASH2_DB` viene impostato
   su una cartella temporanea PRIMA che `config` sia importato, e una assert
   verifica dove sta puntando;
2. **la suite mandava traffico di rete vero** (backfill yfinance con dieci
   worker, per mesi, invisibile) — qui la rete e' spenta a livello di socket,
   sotto qualunque libreria: nessun mock dimenticato puo' uscire;
3. **`TRADASH_OFFLINE` non copriva i provider principali** e il docstring che
   diceva il contrario era falso — qui non c'e' un interruttore da ricordarsi
   di accendere: e' acceso sempre, e chi vuole la rete deve chiederla a voce
   alta con `@pytest.mark.network`;
4. **il codice di produzione conosceva i test** — qui non c'e' nessun ramo
   `if TESTING:`, e un test lo verifica.

Dal Blocco 1 c'e' una quinta difesa, e nasce da un buco trovato misurando: la
rete spenta a livello di socket **non ferma DuckDB**, che apre le connessioni
in C++ senza passare dal modulo `socket` di Python. Per questo `data/defeatbeta.py`
non importa mai la libreria a livello di modulo: senza import non c'e' motore, e
un test legge il sorgente per verificarlo. Qui si sposta anche la cache dei byte
su cartella temporanea, cosi' la suite non puo' scrivere in quella dell'uso reale.
"""
import os
import socket
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.mkdtemp(prefix="tradash2_test_")
os.environ["TRADASH2_DB"] = str(Path(_TEMP_DIR) / "test.db")
os.environ["TRADASH2_DEFEATBETA_CACHE"] = str(Path(_TEMP_DIR) / "httpfs_cache")

import pytest  # noqa: E402  (l'ordine e' voluto: prima l'ambiente, poi gli import)

import config  # noqa: E402
from core.db import db_session  # noqa: E402
from core.schema import ensure_schema  # noqa: E402

# Tabelle da svuotare fra un test e l'altro. L'ordine conta: `calls.run_id` ha
# una chiave esterna verso `jobs`.
TABELLE_DA_SVUOTARE = ("calls", "jobs", "freshness")


class ReteVietata(RuntimeError):
    """Sollevata quando un test prova ad aprire una connessione di rete.

    Non e' un incidente da aggirare: se compare, o manca un mock o quel test
    va marcato `@pytest.mark.network`.
    """


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Applica lo schema una volta per tutta la suite, su un database usa-e-getta."""
    assert str(config.DB_PATH).startswith(_TEMP_DIR), (
        f"la suite sta puntando a {config.DB_PATH}, che non e' il database temporaneo"
    )
    ensure_schema()


@pytest.fixture(autouse=True)
def rete_spenta(request, monkeypatch):
    """Spegne la rete a livello di socket, per ogni test che non la chiede.

    Il mock va SOTTO cio' che misuri: qui sotto tutto — requests, urllib,
    DuckDB, qualunque libreria. Un mock dimenticato non produce silenzio, ma un
    errore con scritto cosa e' successo.
    """
    if request.node.get_closest_marker("network"):
        return

    def vietato(*args, **kwargs):
        raise ReteVietata(
            "un test ha provato ad aprire una connessione. Se e' voluto, marcalo "
            "con @pytest.mark.network; altrimenti manca un mock."
        )

    monkeypatch.setattr(socket.socket, "connect", vietato)
    monkeypatch.setattr(socket.socket, "connect_ex", vietato)
    monkeypatch.setattr(socket, "create_connection", vietato)
    monkeypatch.setattr(socket, "getaddrinfo", vietato)


@pytest.fixture(autouse=True)
def tabelle_pulite(schema):
    """Ogni test parte da tabelle vuote."""
    with db_session() as conn:
        for tabella in TABELLE_DA_SVUOTARE:
            conn.execute(f"DELETE FROM {tabella}")
    yield


@pytest.fixture
def client():
    """Client HTTP dell'applicazione, per provare gli endpoint davvero.

    Non apre socket: `test_client` di Flask parla con l'app in memoria.
    """
    # Import volutamente tardivo: `app` importa `config`, che legge TRADASH2_DB.
    # In cima al file verrebbe importato prima che l'ambiente sia pronto.
    from app import create_app  # noqa: PLC0415
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c
