"""
watchlist.py — i titoli che segui, e le etichette con cui li organizzi.
# feat (Blocco 3): l'unica cosa nel sistema che, se si perde, non torna.

Tutto il resto del database e' una vista ricostruibile da Defeatbeta. Questo no:
la watchlist e' tua, e per questo la fonte di verita' e' un **file JSON
leggibile e correggibile a mano** — `data/watchlist.json` — mentre SQLite ne
tiene una copia di lavoro che serve solo a fare JOIN con l'universo senza
reinventare i filtri in Python.

La differenza si vede il giorno in cui si lancia `manage.py rebuild`: quel
comando cancella la copia, non l'originale. E se apri il JSON con un editor e
cambi qualcosa, la copia si riallinea da sola al primo uso — il confronto e'
sulla data di modifica del file.

**Le regole della tassonomia:**

* i tag hanno **due livelli**: ambito e sotto-ambito, niente terzo livello;
* un titolo puo' stare in **piu' temi** (decisione del 30/08/2026, che rivede il
  tag singolo scelto il 27/08): AMD sta nei semiconduttori e nell'infrastruttura
  per l'AI, e con un'etichetta sola quella scelta non era recuperabile;
* il tag di un titolo puo' essere un ambito o un sotto-ambito, e **il
  sotto-ambito implica il padre**: chi guarda "Semiconductor" vede anche i
  titoli di "Semiconductor / Memory";
* cancellare un tag **non cancella titoli**: i membri lo perdono e basta.

Oltre ai temi, ogni titolo porta due attributi con valori chiusi, copiati dal
thematic-equity-monitor dove la scala e' gia' collaudata: **profilo** (quanto
del valore e' gia' provato) e **maturity** (a che punto e' arrivato il
business).

Ogni modifica lascia una riga in `data/watchlist_events.jsonl`, append-only:
cresce in fondo e non si corregge mai.
"""
import hashlib
import json
import logging
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

import config
from core import freshness
from core.db import db_read, db_session
from data.defeatbeta import SYMBOL_PATTERN

logger = logging.getLogger(__name__)

# Come si separano i simboli quando li incolli a mano: virgole, spazi, a capo,
# punti e virgola. Uno qualsiasi, e in qualsiasi combinazione.
SEPARATORI_SIMBOLI = re.compile(r"[\s,;]+")

# Da cosa e' fatto uno slug: tutto il resto diventa un trattino.
CARATTERI_NON_SLUG = re.compile(r"[^a-z0-9]+")

# Il separatore fra ambito e sotto-ambito dentro lo slug: 'semiconductor.memory'.
SEPARATORE_LIVELLI = "."

# I tipi di evento che finiscono nello storico.
EVENTO_AGGIUNTI = "titoli_aggiunti"
EVENTO_RIMOSSI = "titoli_rimossi"
EVENTO_TAG_ASSEGNATO = "tag_assegnato"
EVENTO_ATTRIBUTI = "attributi_cambiati"
EVENTO_IMPORTATI = "titoli_importati"
EVENTO_PREFERITO = "preferito_cambiato"
EVENTO_TAG_CREATO = "tag_creato"
EVENTO_TAG_ELIMINATO = "tag_eliminato"

ACTION_UNIVERSO_NON_COSTRUITO = (
    "costruisci l'universo per far verificare i simboli prima di aggiungerli"
)

# Ricordo dell'ultima sincronizzazione: l'impronta del contenuto gia'
# ricopiato. Serve a riallineare la copia se qualcuno corregge il JSON a mano,
# che e' uno dei motivi per cui la verita' sta in un file leggibile.
#
# L'impronta e non la data di modifica: il kernel aggiorna gli mtime a scatti di
# millisecondi, e due scritture ravvicinate risultano identiche — misurato, con
# una correzione al file che non veniva raccolta. Il contenuto lo leggiamo
# comunque a ogni giro, quindi l'impronta non costa niente in piu'.
_vista: dict = {"impronta": None}
_lucchetto = threading.Lock()


class WatchlistError(ValueError):
    """Errore d'uso della watchlist: tag inesistente, terzo livello, nome duplicato.

    E' un errore dell'utente, non un guasto: la route lo trasforma in un 400 con
    scritto cosa non andava, non in un 500 senza spiegazione.
    """


def _adesso() -> str:
    """Istante corrente in ISO 8601 UTC, come tutte le altre tabelle."""
    return datetime.now(UTC).isoformat(timespec="seconds")


# --- la fonte di verita': un file JSON -------------------------------------

def _vuoto() -> dict:
    """Una watchlist appena nata. Il file dichiara sempre la propria versione."""
    return {"versione": config.WATCHLIST_FILE_VERSION, "aggiornato_il": _adesso(),
            "tag": [], "titoli": []}


def _converti_da_v1(contenuto: dict) -> dict:
    """Porta un file della versione 1 al modello a piu' temi.

    E' la migrazione descritta in `docs/DECISIONI.md`: scritta in Python su un
    dizionario invece che in SQL, e per questo testabile. Nella versione 1 il
    tag era una stringa sola o `None`; qui diventa una lista, e i due attributi
    nuovi partono vuoti perche' inventarli sarebbe peggio che lasciarli vuoti.
    """
    for titolo in contenuto.get("titoli", []):
        vecchio_tag = titolo.pop("tag", None)
        titolo["tag"] = [vecchio_tag] if vecchio_tag else []
        titolo.setdefault("profilo", None)
        titolo.setdefault("maturity", None)
    contenuto["versione"] = config.WATCHLIST_FILE_VERSION
    logger.info("[WATCHLIST] file della versione 1 convertito al modello a piu' temi")
    return contenuto


def _carica() -> dict:
    """Legge la watchlist dal file. Se non esiste, e' vuota — non e' un errore.

    Un file illeggibile invece lo e', e si ferma qui: proseguire con una
    watchlist vuota significherebbe cancellarla alla prima scrittura.
    """
    if not config.WATCHLIST_PATH.exists():
        return _vuoto()

    try:
        contenuto = json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WatchlistError(
            f"la watchlist in {config.WATCHLIST_PATH.name} non e' leggibile: {exc}"
        ) from exc

    versione = contenuto.get("versione")
    if versione == 1:
        return _converti_da_v1(contenuto)
    if versione != config.WATCHLIST_FILE_VERSION:
        raise WatchlistError(
            f"la watchlist dichiara la versione {versione}, questo codice legge la "
            f"{config.WATCHLIST_FILE_VERSION}"
        )
    return contenuto


def _salva(stato: dict) -> None:
    """Scrive la watchlist in modo atomico, poi riallinea la copia SQLite.

    Prima si scrive un file accanto e poi lo si rinomina: una scrittura
    interrotta a meta' lascerebbe altrimenti un JSON troncato al posto
    dell'unico dato non ricostruibile del sistema.
    """
    stato["aggiornato_il"] = _adesso()
    config.WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    provvisorio = config.WATCHLIST_PATH.with_suffix(".json.tmp")
    provvisorio.write_text(
        json.dumps(stato, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(provvisorio, config.WATCHLIST_PATH)
    _sincronizza(stato)


def _registra_evento(tipo: str, **dettagli) -> None:
    """Aggiunge una riga allo storico. Append-only: non si corregge mai.

    Un errore qui non deve far fallire l'operazione vera: la watchlist e' gia'
    stata scritta, e perdere la riga di storico e' meno grave che far credere
    all'utente che la modifica non sia andata a buon fine.
    """
    riga = {"registrato_il": _adesso(), "evento": tipo, **dettagli}
    try:
        config.WATCHLIST_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with config.WATCHLIST_EVENTS_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(riga, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("[WATCHLIST] evento non registrato: %s", tipo)


# --- la copia di lavoro in SQLite ------------------------------------------

def _sincronizza(stato: dict) -> None:
    """Riscrive la copia SQLite a partire dalla verita'.

    I tag si inseriscono **padri prima dei figli**: le chiavi esterne sono
    attive, e nel vecchio sistema esattamente questo ordine mancante faceva
    fallire la cancellazione a cascata con `FOREIGN KEY constraint failed`.
    """
    tag_ordinati = sorted(stato["tag"], key=lambda t: (t.get("padre") is not None, t["nome"]))
    nomi_validi = {t["nome"] for t in tag_ordinati}

    with db_session() as conn:
        conn.execute("DELETE FROM watchlist_membri")
        conn.execute("DELETE FROM watchlist")
        conn.execute("DELETE FROM watchlist_tags")
        conn.executemany(
            "INSERT INTO watchlist_tags (name, label, parent, order_index) VALUES (?, ?, ?, ?)",
            [(t["nome"], t["etichetta"], t.get("padre"), t.get("ordine", 100))
             for t in tag_ordinati],
        )
        conn.executemany(
            "INSERT INTO watchlist (symbol, profilo, maturity, favorite, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [(t["symbol"], t.get("profilo"), t.get("maturity"),
              1 if t.get("preferito") else 0, t["aggiunto_il"])
             for t in stato["titoli"]],
        )
        # Un'etichetta scomparsa dal file (corretto a mano) non deve far
        # fallire l'intera sincronizzazione: si scarta la sola appartenenza.
        conn.executemany(
            "INSERT INTO watchlist_membri (symbol, tag) VALUES (?, ?)",
            [(t["symbol"], nome) for t in stato["titoli"]
             for nome in t.get("tag", []) if nome in nomi_validi],
        )

    _vista["impronta"] = _impronta(stato)


def _impronta(stato: dict) -> str:
    """Impronta del contenuto che conta: i tag e i titoli, non la data di scrittura."""
    canonico = json.dumps(
        {"tag": stato.get("tag", []), "titoli": stato.get("titoli", [])},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _vista_vuota() -> bool:
    """La copia SQLite non contiene niente."""
    with db_read() as conn:
        righe = conn.execute(
            "SELECT (SELECT COUNT(*) FROM watchlist) + "
            "       (SELECT COUNT(*) FROM watchlist_tags) AS n"
        ).fetchone()
    return righe["n"] == 0


def _assicura_vista() -> dict:
    """Rilegge la verita' e riallinea la copia quando serve.

    Due motivi per riallineare, e servono tutti e due:

    * **il contenuto e' cambiato** — cosi' correggere il JSON con un editor
      funziona davvero, invece di essere una proprieta' dichiarata che la prima
      scrittura dell'applicazione sovrascriverebbe;
    * **la copia e' vuota mentre la verita' no** — che e' esattamente cio' che
      succede dopo `manage.py rebuild`. Guardare solo la data di modifica non
      basterebbe: il file non e' cambiato, e la watchlist sparirebbe dalla
      vista pur essendo ancora sul disco.
    """
    stato = _carica()
    ha_contenuto = bool(stato["titoli"] or stato["tag"])
    if _vista["impronta"] != _impronta(stato) or (ha_contenuto and _vista_vuota()):
        _sincronizza(stato)
    return stato


# --- la tassonomia: due livelli e basta ------------------------------------

def _slug(etichetta: str, padre: str | None) -> str:
    """Il nome interno di un tag, ricavato dall'etichetta a video.

    Un sotto-ambito porta nello slug il nome del padre — 'semiconductor.memory'
    — cosi' la parentela si legge dal nome e non serve risalirla per capirla.
    """
    pulito = CARATTERI_NON_SLUG.sub("-", etichetta.strip().lower()).strip("-")
    if not pulito:
        raise WatchlistError(f"l'etichetta {etichetta!r} non produce un nome utilizzabile")
    return f"{padre}{SEPARATORE_LIVELLI}{pulito}" if padre else pulito


def _trova_tag(stato: dict, nome: str) -> dict:
    """Il tag con quel nome, o un errore che dice quale mancava."""
    for tag in stato["tag"]:
        if tag["nome"] == nome:
            return tag
    raise WatchlistError(f"il tag {nome!r} non esiste")


def _figli(stato: dict, nome: str) -> list[dict]:
    """I sotto-ambiti di un ambito."""
    return [tag for tag in stato["tag"] if tag.get("padre") == nome]


def tag_crea(etichetta: str, padre: str | None = None) -> dict:
    """Crea un ambito, o un sotto-ambito se `padre` e' valorizzato."""
    with _lucchetto:
        stato = _assicura_vista()
        if padre is not None:
            genitore = _trova_tag(stato, padre)
            if genitore.get("padre") is not None:
                raise WatchlistError(
                    f"{padre!r} e' gia' un sotto-ambito: la tassonomia si ferma a "
                    f"{config.TAG_MAX_DEPTH} livelli"
                )

        nuovo = {"nome": _slug(etichetta, padre), "etichetta": etichetta.strip(),
                 "padre": padre, "ordine": 100}
        if any(tag["nome"] == nuovo["nome"] for tag in stato["tag"]):
            raise WatchlistError(f"esiste gia' un tag chiamato {nuovo['nome']!r}")

        stato["tag"].append(nuovo)
        _salva(stato)

    _registra_evento(EVENTO_TAG_CREATO, tag=nuovo["nome"], etichetta=nuovo["etichetta"])
    return nuovo


def tag_elimina(nome: str, cascata: bool = False) -> dict:
    """Elimina un tag. I titoli che lo portavano tornano senza tag, non spariscono.

    Un ambito con figli si rifiuta di sparire senza `cascata`: cancellarlo
    significa liberare anche i membri dei sotto-ambiti, e chi lo chiede deve
    saperlo.
    """
    with _lucchetto:
        stato = _assicura_vista()
        _trova_tag(stato, nome)
        figli = [tag["nome"] for tag in _figli(stato, nome)]
        if figli and not cascata:
            raise WatchlistError(
                f"{nome!r} ha {len(figli)} sotto-ambiti: passa cascata=True per "
                f"eliminarli con lui, liberando anche i loro titoli"
            )

        da_togliere = {nome, *figli}
        stato["tag"] = [tag for tag in stato["tag"] if tag["nome"] not in da_togliere]

        # Il titolo perde l'etichetta cancellata e tiene le altre: con piu' temi
        # per titolo, azzerarli tutti butterebbe via classificazioni sane.
        liberati = []
        for titolo in stato["titoli"]:
            rimasti = [t for t in titolo.get("tag", []) if t not in da_togliere]
            if len(rimasti) != len(titolo.get("tag", [])):
                liberati.append(titolo["symbol"])
                titolo["tag"] = rimasti
        _salva(stato)

    _registra_evento(EVENTO_TAG_ELIMINATO, tag=nome, con_figli=figli, liberati=liberati)
    return {"eliminati": sorted(da_togliere), "titoli_liberati": liberati}


def tag_elenco() -> list[dict]:
    """L'albero dei tag con i conteggi: diretti, e comprensivi dei figli.

    `totale` e' il numero che conta per l'interfaccia: il tab di un ambito deve
    dire quanti titoli mostrera', e mostrera' anche quelli dei sotto-ambiti.
    """
    _assicura_vista()
    with db_read() as conn:
        righe = conn.execute("""
            SELECT t.name, t.label, t.parent, t.order_index,
                   (SELECT COUNT(*) FROM watchlist_membri m WHERE m.tag = t.name) AS diretti,
                   (SELECT COUNT(DISTINCT m.symbol) FROM watchlist_membri m
                     WHERE m.tag = t.name
                        OR m.tag IN (SELECT f.name FROM watchlist_tags f WHERE f.parent = t.name)
                   ) AS totale
            FROM watchlist_tags t
            ORDER BY COALESCE(t.parent, t.name), t.parent IS NOT NULL, t.order_index, t.name
        """).fetchall()
    return [dict(r) for r in righe]


# --- i titoli ---------------------------------------------------------------

def parse_symbols(grezzo: str | list[str]) -> tuple[list[str], list[str]]:
    """Legge un elenco scritto a mano e lo divide in (validi, scartati).

    Gli scartati non vengono ingoiati: tornano al chiamante, perche' un simbolo
    scritto male che sparisce in silenzio e' un titolo che credi di seguire e
    non segui.
    """
    pezzi = [str(p) for p in grezzo] if isinstance(grezzo, list) \
        else SEPARATORI_SIMBOLI.split(grezzo or "")

    validi: list[str] = []
    scartati: list[str] = []
    visti: set[str] = set()

    for pezzo in pezzi:
        candidato = pezzo.strip().upper()
        if not candidato:
            continue
        if not SYMBOL_PATTERN.match(candidato):
            scartati.append(pezzo.strip())
        elif candidato not in visti:
            visti.add(candidato)
            validi.append(candidato)

    return validi, scartati


def _sconosciuti(simboli: list[str]) -> tuple[list[str], str | None]:
    """Quali di questi simboli non esistono nell'universo.

    Se l'universo non e' stato costruito non si puo' sapere, e la risposta lo
    dice invece di far finta che vada tutto bene (regola 5): un ticker scritto
    con un refuso e' ben formato, e senza questo controllo entrerebbe in
    watchlist per produrre analisi vuote per sempre.
    """
    with db_read() as conn:
        if conn.execute("SELECT COUNT(*) AS n FROM universe").fetchone()["n"] == 0:
            return [], ACTION_UNIVERSO_NON_COSTRUITO
        segnaposti = ", ".join("?" * len(simboli))
        noti = {
            r["symbol"] for r in conn.execute(
                f"SELECT symbol FROM universe WHERE symbol IN ({segnaposti})", simboli
            ).fetchall()
        }
    return [s for s in simboli if s not in noti], None


def _nuovo_titolo(simbolo: str, tag: list[str], istante: str) -> dict:
    """Un titolo appena aggiunto: temi eventuali, attributi ancora da decidere.

    `profilo` e `maturity` nascono vuoti apposta: sono giudizi, e inventarli al
    posto di chi guarda sarebbe peggio che lasciarli in bianco.
    """
    return {"symbol": simbolo, "tag": list(tag), "profilo": None, "maturity": None,
            "preferito": False, "aggiunto_il": istante}


def aggiungi(grezzo: str | list[str], tag: str | list[str] | None = None) -> dict:
    """Aggiunge titoli alla watchlist, dicendo di ognuno che fine ha fatto.

    Quattro esiti distinti, mai un silenzio: aggiunti, gia' presenti, scartati
    perche' non hanno la forma di un simbolo, sconosciuti perche' non stanno
    nell'universo.
    """
    validi, scartati = parse_symbols(grezzo)
    etichette = [tag] if isinstance(tag, str) else list(tag or [])

    with _lucchetto:
        stato = _assicura_vista()
        for nome in etichette:
            _trova_tag(stato, nome)

        sconosciuti, avvertimento = _sconosciuti(validi) if validi else ([], None)
        presenti = {t["symbol"] for t in stato["titoli"]}
        gia_presenti = [s for s in validi if s in presenti]
        da_aggiungere = [s for s in validi if s not in presenti and s not in sconosciuti]

        istante = _adesso()
        stato["titoli"].extend(_nuovo_titolo(s, etichette, istante) for s in da_aggiungere)
        if da_aggiungere:
            _salva(stato)

    if da_aggiungere:
        _registra_evento(EVENTO_AGGIUNTI, simboli=da_aggiungere, tag=etichette)
    return {"aggiunti": da_aggiungere, "gia_presenti": gia_presenti,
            "scartati": scartati, "sconosciuti": sconosciuti, "avvertimento": avvertimento}


def _modifica(simboli: list[str], cambia) -> list[str]:
    """Applica una modifica ai titoli indicati. Ritorna quelli toccati davvero."""
    with _lucchetto:
        stato = _assicura_vista()
        richiesti = {s.strip().upper() for s in simboli}
        toccati = []
        for titolo in stato["titoli"]:
            if titolo["symbol"] in richiesti:
                cambia(stato, titolo)
                toccati.append(titolo["symbol"])
        if toccati:
            _salva(stato)
    return toccati


def rimuovi(simboli: list[str]) -> dict:
    """Toglie titoli dalla watchlist. Quelli che non c'erano si dicono."""
    with _lucchetto:
        stato = _assicura_vista()
        richiesti = {s.strip().upper() for s in simboli}
        presenti = {t["symbol"] for t in stato["titoli"]}
        rimossi = sorted(richiesti & presenti)
        stato["titoli"] = [t for t in stato["titoli"] if t["symbol"] not in richiesti]
        if rimossi:
            _salva(stato)

    if rimossi:
        _registra_evento(EVENTO_RIMOSSI, simboli=rimossi)
    return {"rimossi": rimossi, "non_presenti": sorted(richiesti - presenti)}


def aggiungi_tag(simboli: list[str], tag: str) -> dict:
    """Aggiunge un tema a piu' titoli. Chi ce l'ha gia' non lo prende due volte."""
    _trova_tag(_carica(), tag)

    def _cambia(_stato, titolo):
        if tag not in titolo["tag"]:
            titolo["tag"].append(tag)

    toccati = _modifica(simboli, _cambia)
    if toccati:
        _registra_evento(EVENTO_TAG_ASSEGNATO, simboli=toccati, tag=tag, aggiunto=True)
    return {"aggiornati": toccati, "tag": tag}


def togli_tag(simboli: list[str], tag: str) -> dict:
    """Toglie un tema da piu' titoli, senza toccare gli altri temi che hanno."""
    def _cambia(_stato, titolo):
        titolo["tag"] = [nome for nome in titolo["tag"] if nome != tag]

    toccati = _modifica(simboli, _cambia)
    if toccati:
        _registra_evento(EVENTO_TAG_ASSEGNATO, simboli=toccati, tag=tag, aggiunto=False)
    return {"aggiornati": toccati, "tag": tag}


def _valida_attributo(valore: str | None, ammessi: tuple, nome: str) -> str | None:
    """Un valore fuori dall'elenco e' un errore d'uso, non un dato da accettare."""
    if valore in (None, ""):
        return None
    if valore not in ammessi:
        raise WatchlistError(
            f"{nome} {valore!r} non e' fra i valori ammessi: {', '.join(ammessi)}"
        )
    return valore


def imposta_attributi(simbolo: str, tag=..., profilo=..., maturity=...) -> dict:
    """Cambia i temi e/o gli attributi di UN titolo. E' l'editor della scheda.

    I parametri non passati restano come sono: `...` distingue "non toccare" da
    "svuota", che con `None` sarebbero la stessa cosa.
    """
    simbolo_pulito = simbolo.strip().upper()

    with _lucchetto:
        stato = _assicura_vista()
        titolo = next((t for t in stato["titoli"] if t["symbol"] == simbolo_pulito), None)
        if titolo is None:
            raise WatchlistError(f"{simbolo_pulito} non e' in watchlist")

        if tag is not ...:
            etichette = [tag] if isinstance(tag, str) else list(tag or [])
            for nome in etichette:
                _trova_tag(stato, nome)
            titolo["tag"] = etichette
        if profilo is not ...:
            titolo["profilo"] = _valida_attributo(profilo, config.PROFILI, "profilo")
        if maturity is not ...:
            titolo["maturity"] = _valida_attributo(maturity, config.MATURITY, "maturity")

        _salva(stato)
        aggiornato = dict(titolo)

    _registra_evento(EVENTO_ATTRIBUTI, simbolo=simbolo_pulito, tag=aggiornato["tag"],
                     profilo=aggiornato["profilo"], maturity=aggiornato["maturity"])
    return aggiornato


def preferito(simboli: list[str], valore: bool) -> dict:
    """Accende o spegne il contrassegno di preferito su piu' titoli."""
    def _cambia(_stato, titolo):
        titolo["preferito"] = bool(valore)

    toccati = _modifica(simboli, _cambia)
    if toccati:
        _registra_evento(EVENTO_PREFERITO, simboli=toccati, preferito=bool(valore))
    return {"aggiornati": toccati, "preferito": bool(valore)}


# --- leggere ----------------------------------------------------------------

def _temi_per_simbolo(conn) -> dict[str, list[dict]]:
    """Le etichette di ogni titolo, con nome, etichetta a video e ambito padre.

    Una query sola per tutti: chiederle titolo per titolo sarebbe la N+1 che
    rende lenta una pagina senza che nessuno capisca perche'.
    """
    righe = conn.execute("""
        SELECT m.symbol, m.tag, t.label, t.parent
        FROM watchlist_membri m
        JOIN watchlist_tags t ON m.tag = t.name
        ORDER BY t.parent IS NOT NULL, t.name
    """).fetchall()

    per_simbolo: dict[str, list[dict]] = {}
    for riga in righe:
        per_simbolo.setdefault(riga["symbol"], []).append(
            {"nome": riga["tag"], "etichetta": riga["label"], "padre": riga["parent"]}
        )
    return per_simbolo


def _filtri_elenco(tag, profilo, maturity, solo_preferiti) -> tuple[str, list]:
    """Le condizioni della ricerca, tutte parametrizzate.

    Il filtro per tema dice "CONTIENE", non "e' uguale a": un titolo con piu'
    temi deve comparire sotto ciascuno. E comprende i sotto-ambiti, perche'
    chiedere "Semiconductor" significa chiedere anche "Semiconductor / Memory".
    """
    condizioni: list[str] = []
    parametri: list = []

    if tag:
        condizioni.append("""
            EXISTS (SELECT 1 FROM watchlist_membri m
                     WHERE m.symbol = w.symbol
                       AND (m.tag = ?
                            OR m.tag IN (SELECT name FROM watchlist_tags WHERE parent = ?)))
        """)
        parametri.extend([tag, tag])
    if profilo:
        condizioni.append("w.profilo = ?")
        parametri.append(profilo)
    if maturity:
        condizioni.append("w.maturity = ?")
        parametri.append(maturity)
    if solo_preferiti:
        condizioni.append("w.favorite = 1")

    return (f"WHERE {' AND '.join(condizioni)}" if condizioni else ""), parametri


def elenco(tag: str | None = None, solo_preferiti: bool = False,
           profilo: str | None = None, maturity: str | None = None) -> list[dict]:
    """I titoli osservati, coi loro temi e con quello che l'universo sa di loro.

    L'unione con l'universo e' una LEFT JOIN: un titolo resta visibile anche se
    l'universo non e' stato ancora costruito.
    """
    _assicura_vista()
    dove, parametri = _filtri_elenco(tag, profilo, maturity, solo_preferiti)

    with db_read() as conn:
        righe = conn.execute(f"""
            SELECT w.symbol, w.profilo, w.maturity, w.favorite, w.added_at,
                   u.name, u.sector, u.industry, u.market_cap, u.last_close, u.last_close_date
            FROM watchlist w
            LEFT JOIN universe u ON w.symbol = u.symbol
            {dove}
            ORDER BY u.market_cap DESC NULLS LAST, w.symbol
        """, parametri).fetchall()
        temi = _temi_per_simbolo(conn)

    return [{**dict(r), "temi": temi.get(r["symbol"], [])} for r in righe]


def simboli() -> list[str]:
    """I simboli osservati, in ordine. E' la lista che guida tutto il resto."""
    _assicura_vista()
    with db_read() as conn:
        return [r["symbol"] for r in
                conn.execute("SELECT symbol FROM watchlist ORDER BY symbol").fetchall()]


def da_aggiornare(categoria: str) -> list[dict]:
    """Quali titoli osservati hanno quel dato ormai vecchio, e da quanto.

    E' la freschezza per CATEGORIA applicata alla watchlist: il prezzo di un
    titolo puo' essere da rinfrescare mentre il suo profilo e' ancora buono, e
    chiederlo per categoria e' l'unico modo di non rinfrescare tutto ogni volta.
    """
    risposta = []
    for simbolo in simboli():
        serve, motivo = freshness.should_fetch(simbolo, categoria)
        if serve:
            risposta.append({"symbol": simbolo, "motivo": motivo,
                             "eta_s": freshness.age_seconds(simbolo, categoria)})
    return risposta


def eventi(limit: int = config.WATCHLIST_EVENTS_LIMIT_DEFAULT) -> list[dict]:
    """Lo storico, dal piu' recente. Append-only: qui non si corregge niente."""
    if not 1 <= limit <= config.WATCHLIST_EVENTS_LIMIT_MAX:
        raise WatchlistError(
            f"limit deve stare fra 1 e {config.WATCHLIST_EVENTS_LIMIT_MAX}, ricevuto {limit}"
        )
    if not config.WATCHLIST_EVENTS_PATH.exists():
        return []

    righe = config.WATCHLIST_EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    letti = []
    for riga in reversed(righe[-limit:]):
        try:
            letti.append(json.loads(riga))
        except json.JSONDecodeError:
            logger.warning("[WATCHLIST] riga di storico illeggibile, saltata")
    return letti


# --- portare dentro e portare fuori ----------------------------------------
#
# Il giro previsto: si esporta la watchlist, si incolla in un LLM insieme al
# prompt che questo modulo compone, e si reimporta il JSON classificato. Per
# questo l'esportato e l'importato hanno la STESSA forma: un formato per uscire
# e un altro per rientrare sarebbero due occasioni di sbagliare.

# Dove stanno i prompt della watchlist. Sono tre, e rispondono a tre domande
# diverse: classifica quelli che ti do, proponimene di nuovi, dimmi cosa qui
# dentro non ci sta piu' bene.
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_CLASSIFICAZIONE = PROMPT_DIR / "watchlist_classificazione.txt"


def esporta() -> dict:
    """La watchlist in una forma portabile, pronta da incollare altrove."""
    stato = _assicura_vista()
    return {
        "versione": config.WATCHLIST_FILE_VERSION,
        "esportato_il": _adesso(),
        "tag": [{"nome": t["nome"], "etichetta": t["etichetta"], "padre": t.get("padre")}
                for t in stato["tag"]],
        "titoli": [{"symbol": t["symbol"], "tag": t.get("tag", []),
                    "profilo": t.get("profilo"), "maturity": t.get("maturity")}
                   for t in stato["titoli"]],
    }


def _valori_ammessi() -> dict:
    """I due vocabolari chiusi, nella forma in cui i prompt li mostrano."""
    return {
        "profili": "\n".join(f"   - {v}" for v in config.PROFILI),
        "maturity": "\n".join(f"   - {v}" for v in config.MATURITY),
    }


def _temi_esistenti(stato: dict) -> str:
    """I temi gia' in uso, coi nomi esatti: senza, il modello ne inventa di
    paralleli e l'import si riempie di doppioni che dicono la stessa cosa."""
    return "\n".join(
        f"- `{t['nome']}` — {t['etichetta']}"
        + (f" (sotto-ambito di {t['padre']})" if t.get("padre") else "")
        for t in stato["tag"]
    ) or "- (nessuno: creali tu)"


def prompt_scoperta(temi: list[str]) -> str:
    """Il testo per farsi proporre titoli NUOVI su temi precisi.

    Porta con se' cosa c'e' gia': un titolo gia' in watchlist non e' una
    scoperta, e proporlo occupa il posto di una.
    """
    voluti = [t.strip() for t in (temi or []) if t.strip()]
    if not voluti:
        raise WatchlistError("serve almeno un tema su cui cercare")

    stato = _assicura_vista()
    # Nello STATO i temi stanno sotto `tag` come elenco di nomi; `temi` e' la
    # forma arricchita che produce `elenco()`. Leggere la chiave sbagliata non
    # dava errore: dava una watchlist che sembrava senza temi.
    presenti = "\n".join(
        f"- {t['symbol']}"
        + (f" — {', '.join(t['tag'])}" if t.get("tag") else " — senza tema")
        for t in stato["titoli"]
    ) or "- (la watchlist e' vuota)"

    return _componi("watchlist_scoperta",
                    temi_chiesti="\n".join(f"- {t}" for t in voluti),
                    tag_esistenti=_temi_esistenti(stato),
                    gia_presenti=presenti,
                    **_valori_ammessi())


def prompt_revisione() -> str:
    """Il testo per farsi dire cosa nella watchlist non ci sta piu' bene.

    Riceve la classificazione, non i numeri: bilanci e prezzi il sistema li
    calcola da se', e meglio. Quello che il modello puo' vedere e' se la
    classificazione e' coerente e se ci sono doppioni.
    """
    stato = _assicura_vista()
    if not stato["titoli"]:
        raise WatchlistError("non c'e' niente da rivedere: la watchlist e' vuota")

    righe = []
    for titolo in stato["titoli"]:
        temi = ", ".join(titolo.get("tag") or []) or "nessun tema"
        righe.append(f"- {titolo['symbol']}: temi [{temi}], "
                     f"profilo {titolo.get('profilo') or 'non classificato'}, "
                     f"maturity {titolo.get('maturity') or 'non classificata'}")

    return _componi("watchlist_revisione",
                    watchlist="\n".join(righe),
                    tag_esistenti=_temi_esistenti(stato),
                    **_valori_ammessi())


def _componi(nome: str, **pezzi) -> str:
    """Sostituisce i segnaposti di un prompt, e si accorge se ne resta uno vuoto.

    I segnaposti si sostituiscono a mano perche' il testo contiene graffe di
    esempio JSON che `format` interpreterebbe come segnaposti suoi.
    """
    testo = (PROMPT_DIR / f"{nome}.txt").read_text(encoding="utf-8")
    for chiave, valore in pezzi.items():
        testo = testo.replace(f"{{{chiave}}}", valore)

    rimasti = sorted(set(re.findall(r"\{([a-z_][a-z0-9_]*)\}", testo)))
    if rimasti:
        raise WatchlistError(f"il prompt {nome} ha segnaposti non riempiti: "
                             f"{', '.join(rimasti)}")
    return testo


def prompt_classificazione(simboli_richiesti: list[str] | None = None) -> str:
    """Il testo da incollare in un LLM perche' classifichi i titoli.

    Porta con se' i valori ammessi e i temi che esistono gia': senza, l'LLM ne
    inventa di paralleli e l'import si riempie di doppioni che dicono la stessa
    cosa con parole diverse.
    """
    stato = _assicura_vista()
    da_classificare = simboli_richiesti or [t["symbol"] for t in stato["titoli"]]
    if not da_classificare:
        raise WatchlistError("non c'e' niente da classificare: la watchlist e' vuota")

    esistenti = "\n".join(
        f"- `{t['nome']}` — {t['etichetta']}"
        + (f" (sotto-ambito di {t['padre']})" if t.get("padre") else "")
        for t in stato["tag"]
    ) or "- (nessuno: creali tu)"

    modello = PROMPT_CLASSIFICAZIONE.read_text(encoding="utf-8")
    # Sostituzione mirata: il testo contiene graffe di esempio JSON, quindi
    # `str.format` lo tratterebbe come segnaposti e fallirebbe.
    for segnaposto, valore in (
        ("{profili}", "\n".join(f"   - {v}" for v in config.PROFILI)),
        ("{maturity}", "\n".join(f"   - {v}" for v in config.MATURITY)),
        ("{tag_esistenti}", esistenti),
        ("{titoli}", "\n".join(f"- {s}" for s in da_classificare)),
        ("{versione}", str(config.WATCHLIST_FILE_VERSION)),
    ):
        modello = modello.replace(segnaposto, valore)
    return modello


def _assicura_tag(stato: dict, definizioni: list[dict], slug: str) -> list[str]:
    """Crea il tema se manca, ricavandone padre ed etichetta. Ritorna cosa ha creato.

    L'import crea i temi che non esistono: e' il punto di importare una
    classificazione, e rifiutarla perche' i nomi sono nuovi vorrebbe dire
    ricopiarli a mano prima di poterla usare.

    Ritorna la LISTA dei creati e non un si'/no perche' creare un sotto-ambito
    puo' voler dire creare anche il suo ambito, e un padre nato di soppiatto e'
    proprio il genere di cosa che il resoconto deve nominare.
    """
    if any(t["nome"] == slug for t in stato["tag"]):
        return []

    dichiarato = next((d for d in definizioni if d.get("nome") == slug), {})
    padre = dichiarato.get("padre")
    if padre is None and SEPARATORE_LIVELLI in slug:
        padre = slug.split(SEPARATORE_LIVELLI, maxsplit=1)[0]

    creati = _assicura_tag(stato, definizioni, padre) if padre else []

    etichetta = dichiarato.get("etichetta") or \
        slug.rsplit(SEPARATORE_LIVELLI, maxsplit=1)[-1].replace("-", " ").title()
    stato["tag"].append({"nome": slug, "etichetta": etichetta, "padre": padre, "ordine": 100})
    return [*creati, slug]


def _applica_importato(stato: dict, voce: dict, definizioni: list[dict], esito: dict) -> None:
    """Porta una voce importata dentro lo stato, dichiarando cosa e' successo."""
    simbolo = str(voce.get("symbol", "")).strip().upper()
    profilo = _valida_attributo(voce.get("profilo"), config.PROFILI, "profilo")
    maturity = _valida_attributo(voce.get("maturity"), config.MATURITY, "maturity")

    etichette = [str(nome) for nome in (voce.get("tag") or [])]
    for slug in etichette:
        esito["tag_creati"].extend(_assicura_tag(stato, definizioni, slug))

    titolo = next((t for t in stato["titoli"] if t["symbol"] == simbolo), None)
    if titolo is None:
        titolo = _nuovo_titolo(simbolo, [], _adesso())
        stato["titoli"].append(titolo)
        esito["aggiunti"].append(simbolo)
    else:
        esito["aggiornati"].append(simbolo)

    titolo["tag"] = etichette
    titolo["profilo"] = profilo
    titolo["maturity"] = maturity


def importa(dati: dict) -> dict:
    """Carica una classificazione prodotta altrove, dicendo di ognuno che fine ha fatto.

    Un titolo gia' in watchlist viene aggiornato; uno nuovo entra, purche' esista
    nell'universo. Quello che non si puo' accettare non sparisce: torna indietro
    con il motivo.
    """
    voci = dati.get("titoli")
    if not isinstance(voci, list):
        raise WatchlistError("il JSON non contiene un elenco 'titoli'")
    if len(voci) > config.WATCHLIST_IMPORT_MAX:
        raise WatchlistError(
            f"{len(voci)} titoli superano il tetto di {config.WATCHLIST_IMPORT_MAX}"
        )

    definizioni = dati.get("tag") or []
    esito = {"aggiunti": [], "aggiornati": [], "tag_creati": [],
             "scartati": [], "sconosciuti": [], "rifiutati": []}

    with _lucchetto:
        stato = _assicura_vista()
        presenti = {t["symbol"] for t in stato["titoli"]}
        ammessi = _simboli_importabili(voci, presenti, esito)

        for voce in voci:
            simbolo = str(voce.get("symbol", "")).strip().upper()
            if simbolo not in ammessi:
                continue
            try:
                _applica_importato(stato, voce, definizioni, esito)
            except WatchlistError as problema:
                esito["rifiutati"].append({"symbol": simbolo, "motivo": str(problema)})

        _salva(stato)

    _registra_evento(EVENTO_IMPORTATI, aggiunti=esito["aggiunti"],
                     aggiornati=esito["aggiornati"], tag_creati=esito["tag_creati"])
    return esito


def _simboli_importabili(voci: list[dict], presenti: set[str], esito: dict) -> set[str]:
    """Quali simboli dell'importazione si possono accettare, scartando gli altri.

    La verifica sull'universo si fa in una volta sola per tutti: farla titolo
    per titolo sarebbe una query per riga su un elenco che puo' averne 500.
    """
    grezzi = [str(v.get("symbol", "")) for v in voci]
    validi, scartati = parse_symbols(grezzi)
    esito["scartati"].extend(scartati)

    nuovi = [s for s in validi if s not in presenti]
    sconosciuti, _ = _sconosciuti(nuovi) if nuovi else ([], None)
    esito["sconosciuti"].extend(sconosciuti)
    return set(validi) - set(sconosciuti)
