"""
test_blocco3.py — la verifica del Blocco 3: la watchlist e' tua, e sopravvive.
# feat: se questi test non passano, non si va al Blocco 4.

Il PIANO chiede tre cose: modello a due livelli, freschezza per categoria,
storico append-only. Attorno a quelle sta la proprieta' che conta piu' di tutte
— **la fonte di verita' e' il file, non il database** — perche' e' l'unica cosa
del sistema che, se si perde, non torna.

Le regole della tassonomia sono decisioni prese il 27/08/2026 e riportate qui:
un solo tag per titolo, due livelli, il sotto-ambito implica il padre,
cancellare un tag non cancella titoli.
"""
import json

import pytest

import config
from core import freshness
from core.db import db_session
from data import watchlist
from data.watchlist import WatchlistError

AMBITO = "Semiconductor"
SOTTO_AMBITO = "Memory"


@pytest.fixture(autouse=True)
def watchlist_pulita():
    """Ogni test parte senza file e senza ricordo della sincronizzazione."""
    for percorso in (config.WATCHLIST_PATH, config.WATCHLIST_EVENTS_PATH):
        percorso.unlink(missing_ok=True)
    watchlist._vista["impronta"] = None
    yield


@pytest.fixture
def universo_finto():
    """Un universo minimo: senza, nessun simbolo risulta verificabile."""
    with db_session() as conn:
        conn.executemany(
            "INSERT INTO universe (symbol, sector, market_cap, built_at) VALUES (?, ?, ?, ?)",
            [("AAPL", "Technology", 4.6e12, "2026-08-29T00:00:00+00:00"),
             ("MU", "Technology", 2.0e11, "2026-08-29T00:00:00+00:00"),
             ("TSM", "Technology", 1.5e12, "2026-08-29T00:00:00+00:00")],
        )


# --- la proprieta' che conta: la verita' sta nel file -----------------------

def test_la_watchlist_sopravvive_alla_ricostruzione_del_database(universo_finto):
    """`manage.py rebuild` cancella la copia, non l'originale.

    E' il motivo per cui la fonte di verita' e' un file JSON e non una tabella:
    tutto il resto del database si ricostruisce da Defeatbeta, questo no.
    """
    watchlist.aggiungi("AAPL, MU")
    assert len(watchlist.elenco()) == 2

    with db_session() as conn:      # come farebbe manage.py rebuild
        conn.execute("DELETE FROM watchlist")
        conn.execute("DELETE FROM watchlist_tags")

    assert [t["symbol"] for t in watchlist.elenco()] == ["AAPL", "MU"], (
        "la copia si deve riallineare da sola: il file c'e' ancora"
    )


def test_correggere_il_file_a_mano_viene_raccolto(universo_finto):
    """Il JSON e' leggibile e correggibile: se non lo fosse, tanto varrebbe un blob."""
    watchlist.aggiungi("AAPL")

    contenuto = json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
    contenuto["titoli"].append(
        {"symbol": "TSM", "tag": None, "preferito": True,
         "aggiunto_il": "2026-08-29T00:00:00+00:00"}
    )
    config.WATCHLIST_PATH.write_text(json.dumps(contenuto), encoding="utf-8")

    assert sorted(t["symbol"] for t in watchlist.elenco()) == ["AAPL", "TSM"]


def test_un_file_illeggibile_ferma_invece_di_ripartire_da_zero():
    """Proseguire con una watchlist vuota vorrebbe dire cancellarla alla prima scrittura."""
    config.WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.WATCHLIST_PATH.write_text("{ questo non e' json", encoding="utf-8")

    with pytest.raises(WatchlistError):
        watchlist.elenco()


def test_il_file_dichiara_la_propria_versione(universo_finto):
    """Fra un anno, chi legge deve sapere cosa sta leggendo."""
    watchlist.aggiungi("AAPL")
    contenuto = json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
    assert contenuto["versione"] == config.WATCHLIST_FILE_VERSION

    contenuto["versione"] = 99
    config.WATCHLIST_PATH.write_text(json.dumps(contenuto), encoding="utf-8")
    with pytest.raises(WatchlistError, match="versione"):
        watchlist.elenco()


# --- la tassonomia a due livelli -------------------------------------------

def test_il_sotto_ambito_implica_il_padre(universo_finto):
    """Chi guarda 'Semiconductor' vede anche i titoli di 'Semiconductor / Memory'."""
    ambito = watchlist.tag_crea(AMBITO)
    figlio = watchlist.tag_crea(SOTTO_AMBITO, padre=ambito["nome"])
    assert figlio["nome"] == "semiconductor.memory"

    watchlist.aggiungi("TSM", tag=ambito["nome"])
    watchlist.aggiungi("MU", tag=figlio["nome"])

    nel_padre = [t["symbol"] for t in watchlist.elenco(tag=ambito["nome"])]
    assert sorted(nel_padre) == ["MU", "TSM"]
    assert [t["symbol"] for t in watchlist.elenco(tag=figlio["nome"])] == ["MU"]


def test_i_conteggi_dei_tag_comprendono_i_figli(universo_finto):
    """Il tab di un ambito deve dire quanti titoli mostrera', non quanti ne tocca."""
    ambito = watchlist.tag_crea(AMBITO)
    figlio = watchlist.tag_crea(SOTTO_AMBITO, padre=ambito["nome"])
    watchlist.aggiungi("TSM", tag=ambito["nome"])
    watchlist.aggiungi("MU", tag=figlio["nome"])

    per_nome = {t["name"]: t for t in watchlist.tag_elenco()}
    assert per_nome[ambito["nome"]]["diretti"] == 1
    assert per_nome[ambito["nome"]]["totale"] == 2
    assert per_nome[figlio["nome"]]["totale"] == 1


def test_niente_terzo_livello():
    """Un terzo livello e' un albero, e un albero vuole un'interfaccia ad albero."""
    ambito = watchlist.tag_crea(AMBITO)
    figlio = watchlist.tag_crea(SOTTO_AMBITO, padre=ambito["nome"])

    with pytest.raises(WatchlistError, match="livelli"):
        watchlist.tag_crea("DRAM", padre=figlio["nome"])


def test_un_titolo_ha_un_solo_tag(universo_finto):
    """Assegnare un tag nuovo sostituisce il precedente, non si somma."""
    primo = watchlist.tag_crea(AMBITO)
    secondo = watchlist.tag_crea("Foundry")
    watchlist.aggiungi("TSM", tag=primo["nome"])

    watchlist.assegna_tag(["TSM"], secondo["nome"])
    assert watchlist.elenco()[0]["tag"] == secondo["nome"]


def test_eliminare_un_tag_libera_i_titoli_senza_cancellarli(universo_finto):
    """Cancellare un'etichetta non e' cancellare quello che ci sta sotto."""
    ambito = watchlist.tag_crea(AMBITO)
    watchlist.aggiungi("TSM", tag=ambito["nome"])

    esito = watchlist.tag_elimina(ambito["nome"])

    assert esito["titoli_liberati"] == ["TSM"]
    rimasto = watchlist.elenco()[0]
    assert rimasto["symbol"] == "TSM" and rimasto["tag"] is None


def test_eliminare_un_ambito_con_figli_richiede_la_cascata(universo_finto):
    """Chi lo chiede deve sapere che libera anche i membri dei sotto-ambiti."""
    ambito = watchlist.tag_crea(AMBITO)
    figlio = watchlist.tag_crea(SOTTO_AMBITO, padre=ambito["nome"])
    watchlist.aggiungi("MU", tag=figlio["nome"])

    with pytest.raises(WatchlistError, match="cascata"):
        watchlist.tag_elimina(ambito["nome"])

    esito = watchlist.tag_elimina(ambito["nome"], cascata=True)
    assert sorted(esito["eliminati"]) == [ambito["nome"], figlio["nome"]]
    assert watchlist.elenco()[0]["tag"] is None


def test_i_tag_si_sincronizzano_padri_prima_dei_figli(universo_finto):
    """Il difetto del vecchio sistema: le chiavi esterne sono attive davvero.

    Nel JSON i tag possono stare in qualunque ordine — a maggior ragione se
    corretti a mano. Inserire un figlio prima del padre fallisce con
    `FOREIGN KEY constraint failed`.
    """
    ambito = watchlist.tag_crea(AMBITO)
    watchlist.tag_crea(SOTTO_AMBITO, padre=ambito["nome"])

    contenuto = json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
    contenuto["tag"].reverse()      # prima il figlio, poi il padre
    config.WATCHLIST_PATH.write_text(json.dumps(contenuto), encoding="utf-8")
    watchlist._vista["impronta"] = None

    assert len(watchlist.tag_elenco()) == 2


def test_un_tag_inesistente_non_passa_in_silenzio(universo_finto):
    """Assegnare un'etichetta che non c'e' e' un errore d'uso, non un vuoto."""
    with pytest.raises(WatchlistError, match="non esiste"):
        watchlist.aggiungi("AAPL", tag="inventato")


# --- i simboli: quattro esiti, nessun silenzio ------------------------------

def test_ogni_simbolo_riceve_un_esito(universo_finto):
    """Aggiunti, gia' presenti, scartati, sconosciuti: mai un silenzio."""
    watchlist.aggiungi("AAPL")

    esito = watchlist.aggiungi("aapl, mu; no@buono, ZZQX")

    assert esito["aggiunti"] == ["MU"]
    assert esito["gia_presenti"] == ["AAPL"]
    assert esito["scartati"] == ["no@buono"]
    assert esito["sconosciuti"] == ["ZZQX"], "ben formato ma non esiste: non entra"


def test_senza_universo_lo_dice_invece_di_fare_finta():
    """Regola 5: se non si puo' verificare, si dichiara — non si tace."""
    esito = watchlist.aggiungi("QUALUNQUE")

    assert esito["aggiunti"] == ["QUALUNQUE"]
    assert esito["avvertimento"] == watchlist.ACTION_UNIVERSO_NON_COSTRUITO


def test_rimuovere_dice_anche_chi_non_c_era(universo_finto):
    watchlist.aggiungi("AAPL")
    esito = watchlist.rimuovi(["AAPL", "MU"])

    assert esito["rimossi"] == ["AAPL"]
    assert esito["non_presenti"] == ["MU"]


def test_i_preferiti_si_filtrano(universo_finto):
    watchlist.aggiungi("AAPL, MU")
    watchlist.preferito(["MU"], True)

    assert [t["symbol"] for t in watchlist.elenco(solo_preferiti=True)] == ["MU"]


# --- freschezza per categoria ----------------------------------------------

def test_la_freschezza_si_chiede_per_categoria(universo_finto):
    """Il prezzo puo' essere da rinfrescare mentre il profilo va ancora bene."""
    watchlist.aggiungi("AAPL, MU")
    freshness.mark_fetched("AAPL", "price")

    da_fare = [t["symbol"] for t in watchlist.da_aggiornare("price")]
    assert da_fare == ["MU"]
    assert len(watchlist.da_aggiornare("profile")) == 2, "il profilo non l'ha preso nessuno"


# --- lo storico append-only -------------------------------------------------

def test_lo_storico_registra_e_non_corregge(universo_finto):
    """Cresce in fondo: una rimozione non cancella l'aggiunta che c'era prima."""
    watchlist.aggiungi("AAPL")
    watchlist.rimuovi(["AAPL"])

    eventi = watchlist.eventi()
    assert [e["evento"] for e in eventi] == [watchlist.EVENTO_RIMOSSI, watchlist.EVENTO_AGGIUNTI]
    assert eventi[1]["simboli"] == ["AAPL"]
    assert all("registrato_il" in e for e in eventi)


def test_lo_storico_non_esiste_finche_non_succede_niente():
    assert watchlist.eventi() == []


# --- le route ---------------------------------------------------------------

def test_le_route_della_watchlist(client, universo_finto):
    creato = client.post("/api/watchlist/tag", json={"etichetta": AMBITO}).get_json()
    assert creato["success"] is True
    nome = creato["data"]["nome"]

    aggiunta = client.post("/api/watchlist", json={"testo": "AAPL, MU", "tag": nome}).get_json()
    assert aggiunta["data"]["aggiunti"] == ["AAPL", "MU"]

    elenco = client.get(f"/api/watchlist?tag={nome}").get_json()
    assert len(elenco["data"]["titoli"]) == 2
    assert elenco["data"]["tag"][0]["totale"] == 2

    client.patch("/api/watchlist", json={"simboli": ["MU"], "preferito": True})
    assert len(client.get("/api/watchlist?preferiti=1").get_json()["data"]["titoli"]) == 1

    assert client.delete("/api/watchlist", json={"simboli": ["AAPL"]}).get_json()["data"][
        "rimossi"] == ["AAPL"]
    assert len(client.get("/api/watchlist/storico").get_json()["data"]) == 4


def test_un_errore_d_uso_torna_come_400_non_come_guasto(client):
    risposta = client.post("/api/watchlist/tag", json={"etichetta": ""})
    assert risposta.status_code == 400
    assert "etichetta" in risposta.get_json()["error"]

    risposta = client.get("/api/watchlist/da-aggiornare/inventata")
    assert risposta.status_code == 400
    assert "categoria sconosciuta" in risposta.get_json()["error"]
