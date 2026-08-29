"""
conftest.py — la suite non tocca MAI il database reale.
# feat (Blocco 0): igiene dei test.

Il difetto che questo file esiste per impedire: nel vecchio sistema una suite
girava contro il database vero e ne cancellava dati reali. Qui la variabile
d'ambiente viene impostata PRIMA che `config` venga importato, quindi non c'e'
modo che un test scriva altrove.
"""
import os
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.mkdtemp(prefix="tradash2_test_")
os.environ["TRADASH2_DB"] = str(Path(_TEMP_DIR) / "test.db")

import pytest  # noqa: E402  (l'ordine e' voluto: prima l'ambiente, poi gli import)

import config  # noqa: E402
from core.db import db_session  # noqa: E402
from core.schema import ensure_schema  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Applica lo schema una volta per tutta la suite."""
    assert str(config.DB_PATH).startswith(_TEMP_DIR), (
        f"la suite sta puntando a {config.DB_PATH}, che non e' il database temporaneo"
    )
    ensure_schema()


@pytest.fixture(autouse=True)
def tabelle_pulite(schema):
    """Ogni test parte da tabelle vuote."""
    # L'ordine conta: `calls.run_id` ha una chiave esterna verso `jobs`.
    with db_session() as conn:
        for tabella in ("calls", "jobs", "freshness"):
            conn.execute(f"DELETE FROM {tabella}")
    yield


@pytest.fixture
def client():
    """Client HTTP dell'applicazione, per provare gli endpoint davvero."""
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c
