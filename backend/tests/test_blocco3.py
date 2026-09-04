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
import re

import pytest

import config
from core import freshness
from core.db import db_session
from data import defeatbeta, watchlist
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
        {"symbol": "TSM", "tag": [], "profilo": None, "maturity": None,
         "preferito": True, "aggiunto_il": "2026-08-29T00:00:00+00:00"}
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


def test_un_titolo_puo_stare_in_piu_temi(universo_finto):
    """La decisione del 30/08: AMD sta nei semiconduttori E nell'AI infra.

    Col tag singolo del primo modello quella scelta andava fatta una volta e non
    era recuperabile.
    """
    primo = watchlist.tag_crea(AMBITO)
    secondo = watchlist.tag_crea("AI Infrastructure")
    watchlist.aggiungi("TSM", tag=primo["nome"])

    watchlist.aggiungi_tag(["TSM"], secondo["nome"])

    temi = [t["nome"] for t in watchlist.elenco()[0]["temi"]]
    assert sorted(temi) == sorted([primo["nome"], secondo["nome"]])
    assert [t["symbol"] for t in watchlist.elenco(tag=secondo["nome"])] == ["TSM"]

    watchlist.togli_tag(["TSM"], primo["nome"])
    assert [t["nome"] for t in watchlist.elenco()[0]["temi"]] == [secondo["nome"]]


def test_eliminare_un_tag_libera_i_titoli_senza_cancellarli(universo_finto):
    """Cancellare un'etichetta non e' cancellare quello che ci sta sotto."""
    ambito = watchlist.tag_crea(AMBITO)
    watchlist.aggiungi("TSM", tag=ambito["nome"])

    esito = watchlist.tag_elimina(ambito["nome"])

    assert esito["titoli_liberati"] == ["TSM"]
    rimasto = watchlist.elenco()[0]
    assert rimasto["symbol"] == "TSM" and rimasto["temi"] == []


def test_eliminare_un_ambito_con_figli_richiede_la_cascata(universo_finto):
    """Chi lo chiede deve sapere che libera anche i membri dei sotto-ambiti."""
    ambito = watchlist.tag_crea(AMBITO)
    figlio = watchlist.tag_crea(SOTTO_AMBITO, padre=ambito["nome"])
    watchlist.aggiungi("MU", tag=figlio["nome"])

    with pytest.raises(WatchlistError, match="cascata"):
        watchlist.tag_elimina(ambito["nome"])

    esito = watchlist.tag_elimina(ambito["nome"], cascata=True)
    assert sorted(esito["eliminati"]) == [ambito["nome"], figlio["nome"]]
    assert watchlist.elenco()[0]["temi"] == []


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


# --- profilo, maturity e il giro import/export ------------------------------

def test_profilo_e_maturity_si_impostano_per_titolo(universo_finto):
    """Sono giudizi, e nascono vuoti: inventarli sarebbe peggio che lasciarli in bianco."""
    watchlist.aggiungi("AAPL")
    assert watchlist.elenco()[0]["profilo"] is None

    watchlist.imposta_attributi("aapl", profilo="CORE", maturity="SCALED")

    titolo = watchlist.elenco()[0]
    assert titolo["profilo"] == "CORE"
    assert titolo["maturity"] == "SCALED"


def test_un_valore_fuori_elenco_non_entra(universo_finto):
    """CHECK in tabella e controllo nel servizio: un valore inventato si ferma."""
    watchlist.aggiungi("AAPL")

    with pytest.raises(WatchlistError, match="profilo"):
        watchlist.imposta_attributi("AAPL", profilo="FANTASTICO")
    with pytest.raises(WatchlistError, match="maturity"):
        watchlist.imposta_attributi("AAPL", maturity="QUASI")


def test_impostare_un_attributo_non_azzera_gli_altri(universo_finto):
    """Non passare un campo vuol dire 'lascialo com'e'', non 'svuotalo'."""
    ambito = watchlist.tag_crea(AMBITO)
    watchlist.aggiungi("MU", tag=ambito["nome"])
    watchlist.imposta_attributi("MU", profilo="EMERGING", maturity="OPERATIONAL")

    watchlist.imposta_attributi("MU", profilo="CORE")

    titolo = watchlist.elenco()[0]
    assert titolo["profilo"] == "CORE"
    assert titolo["maturity"] == "OPERATIONAL", "non l'abbiamo toccata"
    assert [t["nome"] for t in titolo["temi"]] == [ambito["nome"]]


def test_si_filtra_per_profilo_e_maturity(universo_finto):
    watchlist.aggiungi("AAPL, MU")
    watchlist.imposta_attributi("AAPL", profilo="CORE", maturity="SCALED")
    watchlist.imposta_attributi("MU", profilo="EMERGING", maturity="OPERATIONAL")

    assert [t["symbol"] for t in watchlist.elenco(profilo="CORE")] == ["AAPL"]
    assert [t["symbol"] for t in watchlist.elenco(maturity="OPERATIONAL")] == ["MU"]


# --- le due note: perche' lo guardi, e cosa lo distingue --------------------
#
# Il difetto da cui nascono: il prompt di scoperta chiedeva `perche` e
# `cosa_lo_distingue` fin dal primo giorno, e l'import li buttava via senza
# dirlo. Entravano i temi, il profilo e la maturity, e il ragionamento che li
# aveva prodotti spariva — cioe' l'unica parte che sei mesi dopo non si sarebbe
# potuta ricostruire da soli.

def test_l_import_tiene_il_perche_invece_di_buttarlo(universo_finto):
    """La risposta del prompt di scoperta entra intera, non a meta'."""
    esito = watchlist.importa({"titoli": [
        {"symbol": "MU", "nome": "Micron", "tag": [], "profilo": "CORE",
         "maturity": "SCALED", "perche": "Fa memorie HBM per gli acceleratori.",
         "cosa_lo_distingue": "E' l'unico dei tre a produrre in casa."},
    ]})

    assert esito["aggiunti"] == ["MU"]
    titolo = watchlist.elenco()[0]
    assert titolo["perche"] == "Fa memorie HBM per gli acceleratori."
    assert titolo["cosa_lo_distingue"] == "E' l'unico dei tre a produrre in casa."


def test_una_riclassificazione_non_cancella_il_perche(universo_finto):
    """Il prompt di classificazione le note non le produce: chi non le manda
    non le sta svuotando, e cancellarle sarebbe una perdita silenziosa."""
    watchlist.importa({"titoli": [
        {"symbol": "MU", "tag": [], "perche": "scritto a mano mesi fa"},
    ]})

    watchlist.importa({"titoli": [{"symbol": "MU", "tag": [], "profilo": "EMERGING"}]})

    titolo = watchlist.elenco()[0]
    assert titolo["profilo"] == "EMERGING", "la riclassificazione e' arrivata"
    assert titolo["perche"] == "scritto a mano mesi fa", "e non ha portato via il resto"


def test_le_note_si_correggono_a_mano(universo_finto):
    """Un perche' scritto da un modello vale finche' non lo si riscrive."""
    watchlist.aggiungi("MU")
    watchlist.imposta_attributi("MU", perche="versione del modello")

    watchlist.imposta_attributi("MU", perche="  versione mia  ")
    assert watchlist.elenco()[0]["perche"] == "versione mia", "gli spazi si tolgono"

    watchlist.imposta_attributi("MU", perche=None)
    assert watchlist.elenco()[0]["perche"] is None, "None svuota"

    watchlist.imposta_attributi("MU", profilo="CORE")
    assert watchlist.elenco()[0]["perche"] is None, "non passarlo non lo tocca"


def test_una_nota_troppo_lunga_si_rifiuta_invece_di_troncarla(universo_finto):
    """Un taglio silenzioso fa credere di aver salvato tutto."""
    watchlist.aggiungi("MU")
    troppo = "x" * (config.WATCHLIST_NOTA_MAX_CARATTERI + 1)

    with pytest.raises(WatchlistError, match=str(config.WATCHLIST_NOTA_MAX_CARATTERI)):
        watchlist.imposta_attributi("MU", perche=troppo)

    assert watchlist.elenco()[0]["perche"] is None, "non ne ha salvato un pezzo"


def test_una_nota_smisurata_non_lascia_il_titolo_a_meta(universo_finto):
    """Chi viene rifiutato dev'essere rifiutato INTERO: un titolo che finisce
    fra i rifiutati e intanto si porta a casa i temi nuovi e' peggio di un
    errore, perche' l'esito dice una cosa e il file ne contiene un'altra."""
    watchlist.aggiungi("MU")
    watchlist.imposta_attributi("MU", profilo="CORE")

    esito = watchlist.importa({"titoli": [
        {"symbol": "MU", "tag": ["inventato"], "profilo": "EMERGING",
         "perche": "x" * (config.WATCHLIST_NOTA_MAX_CARATTERI + 1)},
    ]})

    assert [r["symbol"] for r in esito["rifiutati"]] == ["MU"]
    titolo = watchlist.elenco()[0]
    assert titolo["profilo"] == "CORE", "non e' stato toccato"
    assert titolo["temi"] == [], "e non ha preso il tema della voce rifiutata"


def test_le_note_non_stanno_nella_copia_sqlite(universo_finto):
    """Non e' una dimenticanza: la copia serve a filtrare, e su un testo libero
    non si filtra. L'elenco le rimette accanto ai titoli leggendo la verita'."""
    watchlist.aggiungi("MU")
    watchlist.imposta_attributi("MU", perche="sta nel file, non in tabella")

    with db_session() as conn:
        colonne = {r["name"] for r in conn.execute("PRAGMA table_info(watchlist)")}
    assert not colonne & set(watchlist.CAMPI_NOTA)
    assert watchlist.elenco()[0]["perche"] == "sta nel file, non in tabella"


def test_le_note_di_un_titolo_solo(universo_finto):
    """Cio' che legge la pagina di un titolo. Chi non e' in watchlist non ha
    note: `None`, che e' diverso da note vuote."""
    watchlist.aggiungi("MU")
    watchlist.imposta_attributi("MU", cosa_lo_distingue="produce in casa")

    assert watchlist.note("mu ") == {"perche": None,
                                     "cosa_lo_distingue": "produce in casa"}
    assert watchlist.note("AAPL") is None


def test_esportare_e_reimportare_non_cambia_niente(universo_finto):
    """Il giro completo: esci, torni, e la watchlist e' quella di prima."""
    ambito = watchlist.tag_crea(AMBITO)
    watchlist.aggiungi("AAPL, MU", tag=ambito["nome"])
    watchlist.imposta_attributi("AAPL", profilo="CORE", maturity="SCALED")
    prima = watchlist.esporta()

    esito = watchlist.importa(prima)

    assert esito["aggiunti"] == []
    assert sorted(esito["aggiornati"]) == ["AAPL", "MU"]
    assert watchlist.esporta()["titoli"] == prima["titoli"]


def test_l_import_crea_i_temi_che_non_esistono(universo_finto):
    """E' il punto di importare una classificazione: rifiutarla perche' i nomi
    sono nuovi vorrebbe dire ricopiarli a mano prima di poterla usare."""
    watchlist.aggiungi("MU")

    esito = watchlist.importa({
        "versione": config.WATCHLIST_FILE_VERSION,
        "tag": [{"nome": "semiconductors", "etichetta": "Semiconductors", "padre": None}],
        "titoli": [{"symbol": "MU", "tag": ["semiconductors.memory"],
                    "profilo": "CORE", "maturity": "SCALED"}],
    })

    assert sorted(esito["tag_creati"]) == ["semiconductors", "semiconductors.memory"]
    per_nome = {t["name"]: t for t in watchlist.tag_elenco()}
    assert per_nome["semiconductors.memory"]["parent"] == "semiconductors"
    assert per_nome["semiconductors.memory"]["label"] == "Memory", "etichetta dedotta dallo slug"


def test_l_import_dichiara_chi_non_ha_potuto_accettare(universo_finto):
    """Quattro esiti anche qui: aggiunti, aggiornati, scartati, sconosciuti."""
    esito = watchlist.importa({"titoli": [
        {"symbol": "AAPL", "tag": [], "profilo": "CORE", "maturity": "SCALED"},
        {"symbol": "ZZQX", "tag": []},
        {"symbol": "no@buono", "tag": []},
        {"symbol": "MU", "profilo": "INVENTATO"},
    ]})

    assert esito["aggiunti"] == ["AAPL"] or "AAPL" in esito["aggiunti"]
    assert esito["sconosciuti"] == ["ZZQX"]
    assert esito["scartati"] == ["no@buono"]
    assert esito["rifiutati"][0]["symbol"] == "MU"
    assert "profilo" in esito["rifiutati"][0]["motivo"]


def test_l_import_rifiuta_un_elenco_smisurato(universo_finto):
    """Un incollaggio sbagliato non deve diventare una watchlist da diecimila righe."""
    troppi = [{"symbol": f"AAA{i}"} for i in range(config.WATCHLIST_IMPORT_MAX + 1)]
    with pytest.raises(WatchlistError, match="tetto"):
        watchlist.importa({"titoli": troppi})


def test_il_prompt_porta_con_se_valori_e_temi_esistenti(universo_finto):
    """Senza, l'LLM inventa temi paralleli e l'import si riempie di doppioni."""
    ambito = watchlist.tag_crea(AMBITO)
    watchlist.aggiungi("MU", tag=ambito["nome"])

    testo = watchlist.prompt_classificazione()

    assert "MU" in testo
    assert ambito["nome"] in testo
    for valore in (*config.PROFILI, *config.MATURITY):
        assert valore in testo
    assert "{profili}" not in testo and "{titoli}" not in testo


def test_il_prompt_su_una_watchlist_vuota_lo_dice():
    with pytest.raises(WatchlistError, match="vuota"):
        watchlist.prompt_classificazione()


def test_un_file_della_versione_1_viene_convertito(universo_finto):
    """La migrazione descritta in DECISIONI: Python su un dizionario, e testabile."""
    config.WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.WATCHLIST_PATH.write_text(json.dumps({
        "versione": 1,
        "tag": [{"nome": "semi", "etichetta": "Semi", "padre": None, "ordine": 100}],
        "titoli": [{"symbol": "MU", "tag": "semi", "preferito": True,
                    "aggiunto_il": "2026-08-29T00:00:00+00:00"}],
    }), encoding="utf-8")
    watchlist._vista["impronta"] = None

    titolo = watchlist.elenco()[0]

    assert [t["nome"] for t in titolo["temi"]] == ["semi"]
    assert titolo["profilo"] is None
    assert titolo["favorite"] == 1


def test_le_route_di_attributi_e_import(client, universo_finto):
    client.post("/api/watchlist", json={"testo": "AAPL"})

    modificato = client.patch("/api/watchlist/AAPL",
                              json={"profilo": "CORE", "maturity": "SCALED"}).get_json()
    assert modificato["data"]["profilo"] == "CORE"

    assert client.patch("/api/watchlist/AAPL", json={"profilo": "BOH"}).status_code == 400

    esportato = client.get("/api/watchlist/esporta").get_json()["data"]
    assert esportato["titoli"][0]["profilo"] == "CORE"

    prompt = client.get("/api/watchlist/prompt").get_json()["data"]
    assert "AAPL" in prompt["prompt"]

    reimportato = client.post("/api/watchlist/importa", json=esportato).get_json()
    assert reimportato["data"]["aggiornati"] == ["AAPL"]

    elenco = client.get("/api/watchlist?profilo=CORE").get_json()["data"]
    assert len(elenco["titoli"]) == 1
    assert elenco["profili"] == list(config.PROFILI)


def test_le_route_portano_le_note_e_dichiarano_il_tetto(client, universo_finto):
    """Il tetto lo dichiara il backend: l'interfaccia lo mostra mentre si
    scrive, invece di farlo scoprire da un errore a salvataggio gia' tentato."""
    client.post("/api/watchlist", json={"testo": "MU"})

    modificato = client.patch("/api/watchlist/MU",
                              json={"perche": "fa memorie HBM"}).get_json()
    assert modificato["data"]["perche"] == "fa memorie HBM"

    elenco = client.get("/api/watchlist").get_json()["data"]
    assert elenco["titoli"][0]["perche"] == "fa memorie HBM"
    assert elenco["nota_max_caratteri"] == config.WATCHLIST_NOTA_MAX_CARATTERI

    troppo = "x" * (config.WATCHLIST_NOTA_MAX_CARATTERI + 1)
    assert client.patch("/api/watchlist/MU", json={"perche": troppo}).status_code == 400

    esportato = client.get("/api/watchlist/esporta").get_json()["data"]
    assert esportato["titoli"][0]["perche"] == "fa memorie HBM"


def test_la_pagina_di_un_titolo_riceve_il_perche(client, universo_finto, monkeypatch):
    """La descrizione dice cosa fa la societa', la nota dice cosa ci fa QUI.

    Si legge anche quando l'anagrafica non c'e': sono due dati diversi e da due
    fonti diverse, e far dipendere il proprio giudizio dalla disponibilita' di
    Defeatbeta non avrebbe senso.
    """
    class _AnagraficaAssente:
        available = False
        reason = "in questo test non serve"
        action = None

    monkeypatch.setattr(defeatbeta, "profile", lambda *a, **k: _AnagraficaAssente())
    client.post("/api/watchlist", json={"testo": "MU"})
    client.patch("/api/watchlist/MU", json={"perche": "fa memorie HBM"})

    scheda = client.get("/api/titolo/MU").get_json()["data"]

    assert scheda["note_watchlist"]["perche"] == "fa memorie HBM"
    assert client.get("/api/titolo/AAPL").get_json()["data"]["note_watchlist"] is None


# --- Flask serve anche la SPA ----------------------------------------------

def test_le_rotte_del_frontend_ricevono_la_pagina_iniziale(client, monkeypatch, tmp_path):
    """Ricaricare /watchlist non e' un endpoint mancante: e' una rotta della SPA."""
    (tmp_path / "index.html").write_text("<html>tradash</html>", encoding="utf-8")
    monkeypatch.setattr(config, "FRONTEND_DIST", tmp_path)

    for percorso in ("/", "/watchlist", "/operazioni"):
        risposta = client.get(percorso)
        assert risposta.status_code == 200, percorso
        assert b"tradash" in risposta.data


def test_senza_build_lo_dice_col_comando_da_lanciare(client, monkeypatch, tmp_path):
    """Un 404 muto manderebbe a cercare un errore di rotte che non esiste."""
    monkeypatch.setattr(config, "FRONTEND_DIST", tmp_path / "inesistente")

    risposta = client.get("/")

    assert risposta.status_code == 503
    assert "pnpm build" in risposta.get_json()["error"]


def test_un_endpoint_api_inesistente_resta_un_404(client, monkeypatch, tmp_path):
    """La rotta generica della SPA non deve inghiottire le API."""
    (tmp_path / "index.html").write_text("<html>tradash</html>", encoding="utf-8")
    monkeypatch.setattr(config, "FRONTEND_DIST", tmp_path)

    risposta = client.get("/api/inventata")

    assert risposta.status_code == 404
    assert "inesistente" in risposta.get_json()["error"]


def test_il_prompt_si_puo_chiedere_per_titoli_che_non_hai_ancora(universo_finto):
    """E' il caso utile: classificarne di NUOVI prima di aggiungerli. Il backend
    lo accettava dall'inizio e l'interfaccia non glielo passava mai, quindi si
    poteva chiedere solo per la watchlist com'e' — il caso meno interessante."""
    watchlist.aggiungi("AAA")

    testo = watchlist.prompt_classificazione(["PLTR", "CRWD"])

    assert "- PLTR" in testo and "- CRWD" in testo
    assert "- AAA" not in testo, "chiedendone di precisi, gli altri non c'entrano"


def test_la_rotta_del_prompt_accetta_i_simboli_separati_come_capita(client, universo_finto):
    """Virgole o spazi: chi incolla un elenco non deve badare al separatore."""
    watchlist.aggiungi("AAA")

    for grezzo in ("PLTR,CRWD", "PLTR CRWD", "PLTR, CRWD"):
        risposta = client.get(f"/api/watchlist/prompt?simboli={grezzo}").get_json()["data"]
        assert "- PLTR" in risposta["prompt"], grezzo
        assert "- CRWD" in risposta["prompt"], grezzo


def test_la_freschezza_si_chiede_solo_per_i_dati_di_un_titolo(client):
    """«universe mai preso per AVGO» sembra un buco e non lo e': l'universo e'
    un dato globale, e la sua freschezza non riguarda un simbolo."""
    risposta = client.get("/api/watchlist/da-aggiornare/universe")

    assert risposta.status_code == 400
    assert "dato globale" in risposta.get_json()["error"]


def test_una_categoria_inventata_elenca_quelle_vere(client):
    risposta = client.get("/api/watchlist/da-aggiornare/oroscopo")

    assert risposta.status_code == 400
    assert "price" in risposta.get_json()["error"]


def test_l_elenco_delle_categorie_lo_decide_il_backend(client):
    """Quali riguardino un titolo e quali siano globali e' una proprieta' dei
    dati, non una scelta di chi disegna la pagina."""
    dati = client.get("/api/watchlist/da-aggiornare").get_json()["data"]

    nomi = [c["nome"] for c in dati["categorie"]]
    assert "price" in nomi
    assert "universe" not in nomi and "treasury_yield" not in nomi
    assert all(c["ttl_s"] > 0 for c in dati["categorie"])


def test_ogni_categoria_dichiarata_per_titolo_ha_un_ttl():
    """Una categoria senza TTL prenderebbe quello cortissimo di ripiego, e
    risulterebbe vecchia sempre."""
    for nome in config.FRESHNESS_CATEGORIE_PER_TITOLO:
        assert nome in config.FRESHNESS_TTL_S, nome


# --- i due prompt nuovi: trovarne, e rivedere quelli che ci sono ------------

def test_il_prompt_di_scoperta_porta_con_se_cosa_c_e_gia(universo_finto):
    """Un titolo gia' in watchlist non e' una scoperta, e proporlo occupa il
    posto di una."""
    watchlist.tag_crea("Semiconductors")
    watchlist.aggiungi("MU", tag=["semiconductors"])

    testo = watchlist.prompt_scoperta(["quantum-computing"])

    assert "- quantum-computing" in testo
    assert "MU" in testo, "deve sapere cosa c'e' gia'"
    assert "semiconductors" in testo, "e i temi che esistono"
    for ammesso in config.PROFILI:
        assert ammesso in testo


def test_senza_temi_la_scoperta_non_parte():
    with pytest.raises(watchlist.WatchlistError, match="almeno un tema"):
        watchlist.prompt_scoperta([])


def test_la_revisione_mostra_i_temi_veri_di_ogni_titolo(universo_finto):
    """Nello stato i temi stanno sotto `tag`; leggere la chiave sbagliata non
    dava errore — dava una watchlist che sembrava senza temi."""
    watchlist.tag_crea("Semiconductors")
    watchlist.aggiungi("MU", tag=["semiconductors"])

    testo = watchlist.prompt_revisione()

    assert "MU: temi [semiconductors]" in testo


def test_su_una_watchlist_vuota_non_c_e_niente_da_rivedere():
    with pytest.raises(watchlist.WatchlistError, match="vuota"):
        watchlist.prompt_revisione()


def test_la_revisione_non_riceve_ne_bilanci_ne_prezzi(universo_finto):
    """Quelli il sistema li calcola da se', e meglio di quanto un modello se li
    ricordi. Dargli numeri a memoria vorrebbe dire farglieli usare."""
    watchlist.tag_crea("Semiconductors")
    watchlist.aggiungi("MU", tag=["semiconductors"])

    testo = watchlist.prompt_revisione()

    assert "non hai i numeri" in testo.lower()
    for vietato in ("prezzo attuale", "capitalizzazione di", "ROE del"):
        assert vietato not in testo


def test_ogni_prompt_della_watchlist_riempie_tutti_i_suoi_segnaposti(universo_finto):
    """Un segnaposto rimasto vuoto arriva al modello come la parola «{tema}»
    sotto un titolo che promette un contenuto."""
    watchlist.tag_crea("Semiconductors")
    watchlist.aggiungi("MU", tag=["semiconductors"])

    for testo in (watchlist.prompt_classificazione(),
                  watchlist.prompt_scoperta(["quantum"]),
                  watchlist.prompt_revisione()):
        assert not re.findall(r"\{[a-z_][a-z0-9_]*\}", testo)
