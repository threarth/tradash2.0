"""
test_blocco5.py — il glossario, e la sottolineatura che non si puo' dimenticare.
# feat: se questi test non passano, non si va al Blocco 6.

Il PIANO chiede un requisito nuovo rispetto al vecchio tradash: la
sottolineatura dev'essere **sistematica**, applicata dal componente di testo di
default e non aggiunta a mano dove qualcuno si ricorda. Nel vecchio sistema
usavano `GlossaryText` **21 file su tutto il frontend**: una copertura parziale
che sembrava completa, perche' aprendo una pagina in cui funzionava si dava per
scontato che funzionasse ovunque.

Una regola scritta non lo impedisce. Un controllo si': qui sotto ogni
componente del frontend o passa dal componente di testo, o compare
nell'elenco delle eccezioni **con il suo motivo**. Aggiungere una pagina nuova
fa fallire la suite finche' qualcuno non sceglie fra le due cose.
"""
import json
import os
from pathlib import Path

import config
from api import glossary
from core import calls
from core.db import db_read

FRONTEND = Path(config.BASE_DIR).parent / "frontend" / "src"

# Il componente da cui passa la prosa.
COMPONENTE_TESTO = "Testo.svelte"

# Chi non lo usa, e perche'. Un'eccezione senza motivo non e' un'eccezione:
# e' una dimenticanza con l'aria di essere stata decisa.
SENZA_GLOSSARIO = {
    "Testo.svelte": "e' lui: e' il componente che fa la sottolineatura",
    "App.svelte": "sceglie quale pagina montare, non stampa testo suo",
    "Caricamento.svelte": "mostra la parola 'caricamento', non prosa dei dati",
    "Pillola.svelte": "valori enumerati (CORE, SCALED), non frasi",
    "Riquadro.svelte": "solo struttura: caricamento, errore o contenuto, delega ai figli",
    "Layout.svelte": "etichette di navigazione fisse, scritte da noi",
    "PannelloGlossario.svelte": "mostra le definizioni del glossario stesso: "
                               "sottolinearle li' dentro sarebbe un rimando a se stesse",
    "SchedaTitolo.svelte": "la prosa dei dati passa da Valore e da Assente",
    "Universo.svelte": "la prosa dei dati passa da Valore e da Assente",
    "Watchlist.svelte": "la prosa dei dati passa da Valore, Assente e SchedaTitolo",
}

# I componenti attraverso cui passa quasi tutta la prosa che arriva dal backend.
# Se uno di questi smettesse di usare il glossario, le eccezioni qui sopra
# diventerebbero false senza che nessuno se ne accorga.
PORTE_DELLA_PROSA = ("Assente.svelte", "Errore.svelte", "Valore.svelte")


def _componenti() -> list[Path]:
    """Tutti i componenti e le pagine del frontend."""
    return sorted(FRONTEND.rglob("*.svelte"))


# --- la sottolineatura e' sistematica --------------------------------------

def test_ogni_componente_passa_dal_glossario_o_dichiara_perche_no():
    """Il difetto del vecchio tradash: 21 file su tutto il frontend, e sembrava completo."""
    dimenticati = []
    for file in _componenti():
        if file.name in SENZA_GLOSSARIO:
            continue
        if COMPONENTE_TESTO not in file.read_text(encoding="utf-8"):
            dimenticati.append(file.name)

    assert not dimenticati, (
        f"questi componenti non usano {COMPONENTE_TESTO} e non sono fra le eccezioni: "
        f"{dimenticati}. O ci passano, o vanno aggiunti a SENZA_GLOSSARIO col motivo."
    )


def test_le_eccezioni_non_invecchiano():
    """Un'eccezione per un file che non esiste piu' e' una regola che si e' allentata."""
    esistenti = {file.name for file in _componenti()}
    fantasmi = sorted(set(SENZA_GLOSSARIO) - esistenti)

    assert not fantasmi, f"eccezioni per file che non esistono piu': {fantasmi}"


def test_ogni_eccezione_porta_il_suo_motivo():
    """Senza motivo, l'elenco diventa il posto dove si mette quello che non si vuole fare."""
    for nome, motivo in SENZA_GLOSSARIO.items():
        assert motivo and len(motivo) > 10, f"{nome} e' esentato senza una spiegazione"


def test_le_porte_della_prosa_usano_il_glossario():
    """Sono loro a rendere vere le eccezioni: se smettessero, quelle sarebbero false."""
    for nome in PORTE_DELLA_PROSA:
        trovati = [f for f in _componenti() if f.name == nome]
        assert trovati, f"{nome} non esiste piu': le eccezioni vanno riviste"
        assert COMPONENTE_TESTO in trovati[0].read_text(encoding="utf-8"), (
            f"{nome} e' una porta della prosa e deve passare dal glossario"
        )


# --- il glossario, dal backend ---------------------------------------------

def test_il_glossario_ha_i_termini_attesi():
    """171 termini curati a mano: il file e' dato, non qualcosa che generiamo."""
    voci, errore = glossary.termini()

    assert errore is None
    assert len(voci) == 171
    assert all({"id", "label", "short", "full"} <= set(v) for v in voci)


def test_gli_id_dei_termini_sono_unici():
    """Due voci con lo stesso id: una delle due sarebbe irraggiungibile."""
    voci, _ = glossary.termini()
    identificativi = [v["id"] for v in voci]

    assert len(identificativi) == len(set(identificativi))


def test_i_rimandi_puntano_a_termini_che_esistono():
    """Un rimando rotto e' peggio di nessun rimando: promette e non mantiene."""
    voci, _ = glossary.termini()
    esistenti = {v["id"] for v in voci}

    rotti = {
        v["id"]: [r for r in v.get("related", []) if r not in esistenti]
        for v in voci
    }
    rotti = {k: v for k, v in rotti.items() if v}

    assert not rotti, f"rimandi verso termini inesistenti: {rotti}"


def test_le_route_del_glossario(client):
    elenco = client.get("/api/glossario").get_json()
    assert elenco["success"] is True
    assert len(elenco["data"]) == 171

    singolo = client.get("/api/glossario/roic").get_json()
    assert singolo["data"]["id"] == "roic"

    mancante = client.get("/api/glossario/inventato")
    assert mancante.status_code == 404
    assert "non esiste" in mancante.get_json()["error"]


def test_una_lettura_del_glossario_finisce_nel_registro(client):
    """Regola 1: anche una lettura da file locale si dichiara, con la sua provenienza."""
    client.get("/api/glossario")

    with db_read() as conn:
        righe = [dict(r) for r in conn.execute("SELECT * FROM calls")]
    assert [r["source"] for r in righe] == [calls.SOURCE_LOCAL]


def test_il_file_del_glossario_si_ricarica_se_cambia(tmp_path, monkeypatch):
    """Il difetto chiuso: una voce aggiunta a server acceso non compariva mai."""
    finto = tmp_path / "glossary.json"
    finto.write_text(json.dumps([{"id": "a", "label": "A", "short": "s", "full": "f"}]),
                     encoding="utf-8")
    monkeypatch.setattr(glossary, "PERCORSO", finto)
    monkeypatch.setattr(glossary, "_cache", {"voci": None, "mtime": None})

    assert len(glossary.termini()[0]) == 1

    finto.write_text(json.dumps([
        {"id": "a", "label": "A", "short": "s", "full": "f"},
        {"id": "b", "label": "B", "short": "s", "full": "f"},
    ]), encoding="utf-8")
    # La data di modifica ha grana grossa: la si forza, come farebbe il tempo.
    os.utime(finto, (0, 0))

    assert len(glossary.termini()[0]) == 2


def test_un_glossario_illeggibile_lo_dice(tmp_path, monkeypatch):
    """Regola 17: un errore torna esplicito, non come elenco vuoto."""
    rotto = tmp_path / "glossary.json"
    rotto.write_text("{ non e' json", encoding="utf-8")
    monkeypatch.setattr(glossary, "PERCORSO", rotto)
    monkeypatch.setattr(glossary, "_cache", {"voci": None, "mtime": None})

    voci, errore = glossary.termini()

    assert voci == []
    assert "non e' leggibile" in errore
