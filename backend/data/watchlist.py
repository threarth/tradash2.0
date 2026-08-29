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

**Le regole della tassonomia**, decise il 27/08/2026 e riportate qui:

* un titolo ha **un solo tag**;
* i tag hanno **due livelli**: ambito e sotto-ambito, niente terzo livello;
* il tag di un titolo puo' essere l'uno o l'altro, e **il sotto-ambito implica
  il padre**: chi guarda "Semiconductor" vede anche i titoli di
  "Semiconductor / Memory";
* cancellare un tag **non cancella titoli**: i membri tornano senza tag.

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

    with db_session() as conn:
        conn.execute("DELETE FROM watchlist")
        conn.execute("DELETE FROM watchlist_tags")
        conn.executemany(
            "INSERT INTO watchlist_tags (name, label, parent, order_index) VALUES (?, ?, ?, ?)",
            [(t["nome"], t["etichetta"], t.get("padre"), t.get("ordine", 100))
             for t in tag_ordinati],
        )
        conn.executemany(
            "INSERT INTO watchlist (symbol, tag, favorite, added_at) VALUES (?, ?, ?, ?)",
            [(t["symbol"], t.get("tag"), 1 if t.get("preferito") else 0, t["aggiunto_il"])
             for t in stato["titoli"]],
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
        liberati = [t["symbol"] for t in stato["titoli"] if t.get("tag") in da_togliere]
        for titolo in stato["titoli"]:
            if titolo.get("tag") in da_togliere:
                titolo["tag"] = None
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
                   (SELECT COUNT(*) FROM watchlist w WHERE w.tag = t.name) AS diretti,
                   (SELECT COUNT(*) FROM watchlist w
                     WHERE w.tag = t.name
                        OR w.tag IN (SELECT f.name FROM watchlist_tags f WHERE f.parent = t.name)
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


def aggiungi(grezzo: str | list[str], tag: str | None = None) -> dict:
    """Aggiunge titoli alla watchlist, dicendo di ognuno che fine ha fatto.

    Quattro esiti distinti, mai un silenzio: aggiunti, gia' presenti, scartati
    perche' non hanno la forma di un simbolo, sconosciuti perche' non stanno
    nell'universo.
    """
    validi, scartati = parse_symbols(grezzo)

    with _lucchetto:
        stato = _assicura_vista()
        if tag is not None:
            _trova_tag(stato, tag)

        sconosciuti, avvertimento = _sconosciuti(validi) if validi else ([], None)
        presenti = {t["symbol"] for t in stato["titoli"]}
        gia_presenti = [s for s in validi if s in presenti]
        da_aggiungere = [s for s in validi if s not in presenti and s not in sconosciuti]

        istante = _adesso()
        stato["titoli"].extend(
            {"symbol": s, "tag": tag, "preferito": False, "aggiunto_il": istante}
            for s in da_aggiungere
        )
        if da_aggiungere:
            _salva(stato)

    if da_aggiungere:
        _registra_evento(EVENTO_AGGIUNTI, simboli=da_aggiungere, tag=tag)
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


def assegna_tag(simboli: list[str], tag: str | None) -> dict:
    """Assegna (o toglie, con `None`) il tag a piu' titoli in un colpo solo."""
    if tag is not None:
        _trova_tag(_carica(), tag)

    def _cambia(_stato, titolo):
        titolo["tag"] = tag

    toccati = _modifica(simboli, _cambia)
    if toccati:
        _registra_evento(EVENTO_TAG_ASSEGNATO, simboli=toccati, tag=tag)
    return {"aggiornati": toccati, "tag": tag}


def preferito(simboli: list[str], valore: bool) -> dict:
    """Accende o spegne il contrassegno di preferito su piu' titoli."""
    def _cambia(_stato, titolo):
        titolo["preferito"] = bool(valore)

    toccati = _modifica(simboli, _cambia)
    if toccati:
        _registra_evento(EVENTO_PREFERITO, simboli=toccati, preferito=bool(valore))
    return {"aggiornati": toccati, "preferito": bool(valore)}


# --- leggere ----------------------------------------------------------------

def elenco(tag: str | None = None, solo_preferiti: bool = False) -> list[dict]:
    """I titoli osservati, con quello che l'universo sa di loro.

    Il filtro per tag comprende i sotto-ambiti: chiedere "Semiconductor"
    significa chiedere anche "Semiconductor / Memory". L'unione con l'universo
    e' una LEFT JOIN: un titolo resta visibile anche se l'universo non e' stato
    ancora costruito.
    """
    _assicura_vista()
    condizioni: list[str] = []
    parametri: list = []

    if tag:
        condizioni.append(
            "(w.tag = ? OR w.tag IN (SELECT name FROM watchlist_tags WHERE parent = ?))"
        )
        parametri.extend([tag, tag])
    if solo_preferiti:
        condizioni.append("w.favorite = 1")

    dove = f"WHERE {' AND '.join(condizioni)}" if condizioni else ""
    with db_read() as conn:
        righe = conn.execute(f"""
            SELECT w.symbol, w.tag, w.favorite, w.added_at,
                   e.label AS tag_label, e.parent AS tag_parent,
                   u.sector, u.industry, u.market_cap, u.last_close, u.last_close_date
            FROM watchlist w
            LEFT JOIN watchlist_tags e ON w.tag = e.name
            LEFT JOIN universe u ON w.symbol = u.symbol
            {dove}
            ORDER BY u.market_cap DESC NULLS LAST, w.symbol
        """, parametri).fetchall()
    return [dict(r) for r in righe]


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
