"""
schema.py — applica lo schema dichiarato in schema.sql.
# feat (Blocco 0, rivisto): niente migrazioni, un solo file di schema.

`ensure_schema()` gira a ogni avvio ed e' idempotente: tutte le istruzioni in
schema.sql sono `IF NOT EXISTS`, quindi su un database gia' a posto non fa
nulla e non costa niente.

`rebuild()` invece e' distruttivo e serve durante lo sviluppo: cancella le
tabelle e le ricrea. Non viene mai chiamato in automatico — solo da `manage.py`
e solo dopo una conferma battuta a mano.
"""
import logging
import sqlite3
from pathlib import Path

from core.db import db_read, db_session

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Ambito da usare per i dati che non appartengono a un titolo: la curva dei
# Treasury, la lista dell'universo. Il prefisso '@' non puo' essere un ticker.
GLOBAL_SCOPE = "@global"


def _schema_sql() -> str:
    """Legge lo schema dal file. Un errore qui deve fermare l'avvio, non passare."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema non trovato: {SCHEMA_PATH}")
    return SCHEMA_PATH.read_text(encoding="utf-8")


class SchemaDaRicostruire(RuntimeError):
    """Lo schema dichiarato non combacia con le tabelle che esistono.

    Qui non ci sono migrazioni per scelta: quando una tabella cambia forma —
    una colonna rinominata, una aggiunta — la procedura e' ricostruire il
    database, che e' una vista. Questo errore esiste per dirlo con parole
    proprie invece di lasciare passare un messaggio di SQLite che nomina una
    colonna e non spiega cosa farne.
    """


def ensure_schema() -> None:
    """Applica lo schema. Idempotente: si puo' chiamare a ogni avvio."""
    try:
        with db_session() as conn:
            conn.executescript(_schema_sql())
    except sqlite3.OperationalError as exc:
        raise SchemaDaRicostruire(
            f"lo schema in {SCHEMA_PATH.name} non combacia con il database "
            f"({exc}). Qui non ci sono migrazioni: ricostruisci con "
            f"`python manage.py rebuild`. La watchlist non si perde, sta in un file."
        ) from exc
    logger.info("[SCHEMA] applicato da %s", SCHEMA_PATH.name)


def tables() -> list[str]:
    """Le tabelle esistenti adesso nel database, in ordine alfabetico.

    Solo tabelle: le viste stanno in `views()`. Chi conta le righe di ogni
    tabella non deve ritrovarsi a contare due volte le stesse, una dalla
    tabella e una dalla vista che ci sta sopra.
    """
    return _oggetti_di_tipo("table")


def views() -> list[str]:
    """Le viste esistenti adesso nel database, in ordine alfabetico.

    Esistono da quando `universe` e' diventata l'unione di due tabelle che si
    rinfrescano a ritmi diversi. Il motivo per cui questa funzione c'e' e' che
    `rebuild()` cancellava solo cio' che `tables()` elencava: una vista sarebbe
    rimasta in piedi a puntare tabelle appena distrutte, e il guasto sarebbe
    comparso alla prima interrogazione invece che qui.
    """
    return _oggetti_di_tipo("view")


def _oggetti_di_tipo(tipo: str) -> list[str]:
    """I nomi degli oggetti di un tipo, saltando quelli interni di SQLite."""
    with db_read() as conn:
        righe = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ? "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name",
            (tipo,),
        ).fetchall()
    return [r["name"] for r in righe]


def divergenze() -> list[str]:
    """Colonne che `schema.sql` dichiara e il database vivo non ha.

    ## Il buco che questa funzione esiste per rendere visibile

    `ensure_schema()` esegue `CREATE TABLE IF NOT EXISTS`. Su un database che
    esiste gia' quella riga **non fa niente**: se qualcuno aggiunge una colonna
    a `schema.sql`, il file e il database divergono in silenzio. Nessun errore,
    nessun log — solo query che falliscono piu' tardi, o peggio, codice nuovo
    che legge una colonna che li' dentro non c'e'.

    E' successo il 18/09/2026 aggiungendo `close_1a_fa` a `universe_mercato`:
    la suite era tutta verde, perche' i test partono da un database nuovo dove
    lo schema si applica per intero. Solo il database vero era indietro.

    ## Il confronto lo fa SQLite, non un parser nostro

    Lo schema si applica a un database **in memoria**, e poi si confrontano i
    `PRAGMA table_info` dei due. Il primo tentativo leggeva `schema.sql` riga
    per riga e prendeva la prima parola di ognuna: dichiarava colonne di nome
    `REFERENCES` e `('CORE',` perche' una definizione di colonna puo' continuare
    sulla riga dopo e un `CHECK ... IN (...)` puo' stare su tre. Il posto giusto
    dove sapere cos'e' una colonna e' il motore che le crea.

    ## Non bastano i nomi delle colonne

    La prima versione confrontava solo quelli, e si e' bucata subito: le due
    colonne aggiunte a `universe_mercato` con `ALTER TABLE ADD COLUMN` c'erano,
    quindi diceva «allineato» — ma `ALTER TABLE` **non porta il vincolo**, e la
    tabella vera aveva 2 `CHECK` dove il file ne dichiara 3. Un controllo che
    guarda i nomi e non i vincoli non vede la meta' di cio' che uno schema dice.

    Quindi si confrontano anche i `CHECK` e i `NOT NULL`, colonna per colonna.

    Qui non si ripara niente: si DICE. Riparare vuol dire o un `ALTER TABLE`
    scelto da chi sa cosa c'e' dentro, o `manage.py rebuild` — e sono due
    decisioni diverse con due costi diversi.
    """
    atteso = sqlite3.connect(":memory:")
    try:
        atteso.executescript(_schema_sql())
        dichiarate = {
            riga[0]: _descrizione(atteso, riga[0])
            for riga in atteso.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        atteso.close()

    presenti = set(tables())
    problemi = []
    with db_read() as conn:
        for nome, atteso_per_tabella in sorted(dichiarate.items()):
            if nome not in presenti:
                continue
            reale = _descrizione(conn, nome)

            for colonna in sorted(set(atteso_per_tabella) - set(reale)):
                problemi.append(f"{nome}.{colonna} — colonna dichiarata e assente")

            if atteso_per_tabella["__vincoli__"] != reale["__vincoli__"]:
                problemi.append(
                    f"{nome} — i vincoli CHECK non combaciano: "
                    f"il file ne dichiara {atteso_per_tabella['__vincoli__']}, "
                    f"il database ne ha {reale['__vincoli__']}. "
                    f"Succede dopo un ALTER TABLE, che la colonna la aggiunge "
                    f"e il vincolo no"
                )
    return problemi


def _descrizione(conn, tabella: str) -> dict:
    """Le colonne di una tabella, e quanti `CHECK` porta la sua definizione.

    I `CHECK` si contano sul testo del `CREATE TABLE` perche' SQLite non li
    espone in nessun `PRAGMA`: non e' un confronto fine — due vincoli diversi
    in pari numero non verrebbero distinti — ma prende il caso che capita
    davvero, cioe' un vincolo che manca del tutto.
    """
    descrizione = {r[1] if isinstance(r, tuple) else r["name"]: True
                   for r in conn.execute(f"PRAGMA table_info({tabella})")}
    riga = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tabella,)
    ).fetchone()
    testo = (riga[0] if isinstance(riga, tuple) else riga["sql"]) or ""
    descrizione["__vincoli__"] = testo.upper().count("CHECK")
    return descrizione


def rebuild(confirmed: bool = False) -> list[str]:
    """DISTRUTTIVO: cancella tutte le tabelle e le ricrea da schema.sql.

    Richiede `confirmed=True`: un'operazione che perde dati non deve poter
    partire per sbaglio da una chiamata dimenticata. Ritorna le tabelle
    cancellate.
    """
    if not confirmed:
        raise ValueError("rebuild() cancella tutti i dati: chiamalo con confirmed=True")

    viste = views()
    da_cancellare = tables()
    with db_session() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        # Prima le viste: una vista che sopravvive alle tabelle su cui poggia
        # non da' errore adesso, lo da' alla prima lettura — e li' sembra un
        # guasto dei dati invece che una ricostruzione lasciata a meta'.
        for vista in viste:
            conn.execute(f"DROP VIEW IF EXISTS {vista}")
        for tabella in da_cancellare:
            conn.execute(f"DROP TABLE IF EXISTS {tabella}")
        conn.executescript(_schema_sql())

    logger.warning("[SCHEMA] database ricostruito, cancellate %d tabelle (%s) "
                   "e %d viste (%s)",
                   len(da_cancellare), ", ".join(da_cancellare) or "nessuna",
                   len(viste), ", ".join(viste) or "nessuna")
    return da_cancellare
