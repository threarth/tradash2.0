"""
test_schema.py — lo schema fa rispettare quello che dichiara.
# feat (Blocco 0, rivisto): senza migrazioni, e' lo schema stesso la garanzia.

Un vincolo dichiarato e non applicato e' peggio di un vincolo assente: da' la
sensazione della sicurezza senza darla. Questi test verificano che i CHECK e le
tabelle STRICT respingano davvero i dati sbagliati.
"""
import sqlite3

import pytest

from core import freshness, schema
from core.db import db_session, db_read


def test_lo_schema_si_puo_applicare_due_volte():
    """`ensure_schema()` gira a ogni avvio: deve essere innocuo su un DB gia' a posto."""
    prima = schema.tables()
    schema.ensure_schema()
    assert schema.tables() == prima


def test_le_tabelle_dichiarate_esistono_tutte():
    """Le tre tabelle dell'osservabilita' ci sono."""
    assert set(schema.tables()) >= {"jobs", "calls", "freshness"}


def test_le_tabelle_sono_strict():
    """STRICT attivo: una stringa non entra in una colonna INTEGER.

    Senza STRICT, SQLite accetterebbe silenziosamente 'molti' come durata.
    """
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            conn.execute(
                """INSERT INTO calls (provider, endpoint, source, status,
                                      duration_ms, called_at)
                   VALUES ('defeatbeta', 'stock_prices', 'network', 'ok', 'molti', '2026-08-29')"""
            )


def test_uno_stato_inventato_non_entra_in_tabella():
    """Il CHECK sui valori enumerati respinge uno stato che non esiste."""
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            conn.execute(
                """INSERT INTO jobs (run_id, kind, label, status, started_at)
                   VALUES ('x', 'prova', 'etichetta', 'quasi_finito', '2026-08-29')"""
            )


def test_una_provenienza_inventata_non_entra_in_tabella():
    """Le sole provenienze ammesse sono quelle dichiarate in schema.sql."""
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            conn.execute(
                """INSERT INTO calls (provider, endpoint, source, status,
                                      duration_ms, called_at)
                   VALUES ('defeatbeta', 'stock_prices', 'forse', 'ok', 10, '2026-08-29')"""
            )


def test_una_durata_negativa_non_entra_in_tabella():
    """Un tempo che scorre all'indietro e' un bug, non un dato."""
    with pytest.raises(sqlite3.IntegrityError):
        with db_session() as conn:
            conn.execute(
                """INSERT INTO calls (provider, endpoint, source, status,
                                      duration_ms, called_at)
                   VALUES ('defeatbeta', 'stock_prices', 'network', 'ok', -1, '2026-08-29')"""
            )


def test_una_chiamata_puo_non_appartenere_a_nessun_titolo():
    """`scope` e' facoltativo: la curva dei Treasury non e' di nessun ticker."""
    with db_session() as conn:
        conn.execute(
            """INSERT INTO calls (provider, endpoint, source, status, duration_ms, called_at)
               VALUES ('defeatbeta', 'daily_treasury_yield', 'network', 'ok', 12, '2026-08-29')"""
        )
    with db_read() as conn:
        riga = conn.execute("SELECT scope FROM calls").fetchone()
    assert riga["scope"] is None


# --- la freschezza sa parlare anche di cio' che non e' un titolo ------------

def test_la_freschezza_vale_anche_per_i_dati_globali():
    """Il difetto chiuso qui: prima la freschezza sapeva parlare solo di ticker."""
    serve, motivo = freshness.should_fetch_global("universe")
    assert serve is True
    assert schema.GLOBAL_SCOPE in motivo

    freshness.mark_fetched_global("universe")
    serve, motivo = freshness.should_fetch_global("universe")
    assert serve is False
    assert "fresco" in motivo


def test_l_ambito_globale_non_puo_essere_confuso_con_un_ticker():
    """La chiave globale comincia per '@', che nessun simbolo puo' contenere."""
    assert schema.GLOBAL_SCOPE.startswith("@")
    freshness.mark_fetched_global("universe")
    serve_per_un_titolo, _ = freshness.should_fetch("AAPL", "universe")
    assert serve_per_un_titolo is True


def test_i_ticker_si_confrontano_in_maiuscolo():
    """`aapl` e `AAPL` sono lo stesso titolo; '@global' resta com'e'."""
    assert freshness.normalize_scope(" aapl ") == "AAPL"
    assert freshness.normalize_scope(schema.GLOBAL_SCOPE) == schema.GLOBAL_SCOPE

    freshness.mark_fetched("aapl", "price")
    serve, _ = freshness.should_fetch("AAPL", "price")
    assert serve is False


# --- la ricostruzione e' distruttiva e lo dichiara --------------------------

def test_rebuild_senza_conferma_si_rifiuta_di_partire():
    """Un'operazione che perde dati non parte per una chiamata dimenticata."""
    with pytest.raises(ValueError, match="confirmed=True"):
        schema.rebuild()


def test_rebuild_confermato_svuota_e_ricrea():
    """Con la conferma esplicita, il database torna vuoto ma completo."""
    freshness.mark_fetched("AAPL", "price")
    assert freshness.age_seconds("AAPL", "price") is not None

    cancellate = schema.rebuild(confirmed=True)

    assert set(cancellate) >= {"jobs", "calls", "freshness"}
    assert set(schema.tables()) >= {"jobs", "calls", "freshness"}
    assert freshness.age_seconds("AAPL", "price") is None
