"""
defeatbeta.py — l'unico punto di accesso ai dati Defeatbeta.
# feat (Blocco 1): profilo, prezzi, bilanci, calendario, filings, news.

Ogni lettura passa da `core/calls.py` con la provenienza dichiarata, e la
provenienza non e' una stima: e' il numero di richieste HTTP che DuckDB ha
davvero fatto per servire quella query, letto dal suo log (`duckdb_logs`) e
azzerato prima di ogni interrogazione. Zero richieste significa che i byte
erano gia' su disco, e la riga di log dice `cache`.

Tre fatti misurati il 29/08/2026 su `defeatbeta-api` 0.0.60, che spiegano
com'e' fatto questo modulo:

1. **importare la libreria fa rete**: `nltk.download('punkt_tab')` verso
   raw.githubusercontent.com e `_print_welcome()` verso huggingface.co, a
   livello di modulo, piu' una terza chiamata nel costruttore del client
   (`_validate_httpfs_cache`). Non e' un difetto di piattaforma e non si toglie
   senza monkey-patch. Qui non si nasconde: l'import avviene al PRIMO USO REALE
   dentro `calls.track()`, cosi' quelle chiamate compaiono nel registro con un
   nome, invece di partire all'avvio dell'applicazione (regola 2).
2. **la cache di `cache_httpfs` e' a byte-range, non a risposte**: 2,2 MB su
   disco bastano a servire i prezzi di un titolo da un parquet di 443 MB. Per
   questo non teniamo una nostra cache di risultati: sarebbe una seconda cache
   sopra la prima, e "ogni uso di cache loggato" diventerebbe ambiguo.
3. **la sua invalidazione la fa la libreria**: il costruttore confronta
   `update_time` di `spec.json` con quello in cache e, se Defeatbeta ha
   pubblicato dati nuovi, svuota tutto. E' la ragione principale per cui la
   libreria vale il suo peso.

Le letture sono serializzate da un lucchetto: il conteggio delle richieste HTTP
si legge azzerando un log condiviso da tutta la connessione, e due query in
parallelo si ruberebbero i numeri a vicenda. Un batch su molti titoli si scrive
come UNA query con piu' simboli, non come molte query in parallelo.
"""
import logging
import re
import threading
from dataclasses import dataclass

import pandas as pd

import config
from core import calls, freshness

logger = logging.getLogger(__name__)

# Nome con cui il provider compare nel registro delle chiamate.
PROVIDER_NAME = "defeatbeta"

# Le tabelle del dataset. Sono nomi di file che finiscono nella clausola FROM,
# dove un parametro legato non puo' andare: per questo l'elenco e' chiuso qui e
# non arriva mai da fuori.
TABLE_PROFILE = "stock_profile"
TABLE_PRICES = "stock_prices"
TABLE_STATEMENT = "stock_statement"
TABLE_EARNING_CALENDAR = "stock_earning_calendar"
TABLE_SEC_FILING = "stock_sec_filing"
TABLE_NEWS = "stock_news"

# La categoria di freschezza di ogni tabella. I nomi sono quelli dichiarati in
# `config.FRESHNESS_TTL_S`: un test verifica che non se ne inventi di nuovi,
# perche' una categoria sconosciuta prende il TTL cortissimo e non si nota.
CATEGORIA_PER_TABELLA = {
    TABLE_PROFILE: "profile",
    TABLE_PRICES: "price",
    TABLE_STATEMENT: "statements",
    TABLE_EARNING_CALENDAR: "earning_calendar",
    TABLE_SEC_FILING: "sec_filings",
    TABLE_NEWS: "news",
}

# Endpoint sotto cui si registra l'inizializzazione della libreria: le tre
# chiamate di rete che fa da sola devono avere un nome nel registro.
ENDPOINT_LIBRARY_INIT = "libreria:init"

# Forma di un simbolo accettabile. Serve a due cose: tenere fuori dalla query
# tutto cio' che non e' un ticker, e distinguere "simbolo scritto male" da
# "simbolo che non esiste nel dataset" (regola 4).
SYMBOL_MAX_LENGTH = 12
SYMBOL_PATTERN = re.compile(rf"^[A-Z0-9][A-Z0-9.\-]{{0,{SYMBOL_MAX_LENGTH - 1}}}$")

# Il log di DuckDB e' la misura della rete: si azzera prima della query e si
# conta dopo. Senza, la provenienza sarebbe un'ipotesi.
SQL_ENABLE_HTTP_LOG = "CALL enable_logging('HTTP')"
SQL_TRUNCATE_LOG = "CALL truncate_duckdb_logs()"
SQL_COUNT_HTTP = "SELECT COUNT(*) FROM duckdb_logs WHERE type = 'HTTP'"

# La libreria parla molto a livello INFO: qui il suo log resta zitto, il nostro no.
DUCKDB_LOG_LEVEL_SILENT = None

# Cosa dire all'utente quando un dato non c'e'. Regola 5: mai una casella vuota.
ACTION_SIMBOLO_ASSENTE = "verifica il simbolo: Defeatbeta copre solo il mercato USA"
ACTION_SIMBOLO_MALFORMATO = (
    f"un simbolo e' fatto di lettere, cifre, punto e trattino, "
    f"al massimo {SYMBOL_MAX_LENGTH} caratteri"
)

# Il client vive in un dizionario invece che in una variabile riassegnata:
# il singleton resta in un posto solo e nessuna funzione deve dichiarare `global`.
_stato: dict = {"client": None}
_client_lock = threading.Lock()
_read_lock = threading.Lock()


class DefeatbetaUnavailable(RuntimeError):
    """Il provider ci rifiuta: rete assente, libreria rotta, query fallita.

    Regola 4, la meta' che DEVE fermare il gruppo. E' l'opposto di un simbolo
    assente, che invece torna come `Lettura(available=False)` e lascia
    proseguire gli altri titoli del giro.
    """


@dataclass(frozen=True)
class Lettura:
    """Il risultato di una lettura, con il motivo sempre valorizzato.

    Regola 5: l'assenza si dichiara, non si lascia dedurre da un DataFrame
    vuoto. Regola 17: chi puo' fallire ritorna un risultato esplicito, mai
    `None`.
    """
    frame: pd.DataFrame
    scope: str
    category: str
    source: str
    available: bool
    reason: str
    action: str | None = None


def _build_client():
    """Importa la libreria e costruisce il client DuckDB. Solo al primo uso.

    Le tre chiamate di rete della libreria avvengono qui dentro: l'import del
    pacchetto e il costruttore, che confronta `spec.json` remoto con quello in
    cache e svuota la cache se Defeatbeta ha pubblicato dati nuovi.

    La cartella della cache viene spostata dentro il progetto: la libreria la
    mette in `/tmp/defeatbeta/cache/<versione>`, che su molte macchine sparisce
    al riavvio — e ogni byte perso e' un byte da riscaricare.
    """
    from defeatbeta_api.client.duckdb_client import get_duckdb_client  # noqa: PLC0415

    cliente = get_duckdb_client(log_level=DUCKDB_LOG_LEVEL_SILENT)
    config.DEFEATBETA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cartella = str(config.DEFEATBETA_CACHE_DIR).replace("'", "''")
    cliente.connection.execute(f"SET GLOBAL cache_httpfs_cache_directory = '{cartella}'")
    cliente.connection.execute(SQL_ENABLE_HTTP_LOG)
    logger.info("[DEFEATBETA] client pronto, cache dei byte in %s", config.DEFEATBETA_CACHE_DIR)
    return cliente


def _ensure_client():
    """Il client, costruito al primo uso reale e mai all'avvio dell'applicazione."""
    if _stato["client"] is not None:
        return _stato["client"]

    with _client_lock:
        # Ricontrollo dentro il lucchetto: due thread possono arrivare insieme.
        if _stato["client"] is not None:
            return _stato["client"]
        with calls.track(PROVIDER_NAME, ENDPOINT_LIBRARY_INIT) as chiamata:
            # Misurato: import + costruttore fanno tre chiamate di rete.
            chiamata.from_network()
            try:
                _stato["client"] = _build_client()
            except Exception as exc:
                raise DefeatbetaUnavailable(
                    f"inizializzazione di defeatbeta-api fallita: {type(exc).__name__}: {exc}"
                ) from exc
    return _stato["client"]


def _table_uri(table: str) -> str:
    """URL del parquet di una tabella, chiesto alla libreria e non scritto a mano.

    E' il motivo per cui la libreria e' una dipendenza e non una copia: se
    Defeatbeta sposta i file, la forma dell'URL cambia con un aggiornamento.
    """
    from defeatbeta_api.client.hugging_face_client import HuggingFaceClient  # noqa: PLC0415

    if table not in CATEGORIA_PER_TABELLA:
        raise ValueError(f"tabella non prevista dal Blocco 1: {table!r}")
    return HuggingFaceClient().get_url_path(table)


def _prepara(table: str, extra: str) -> str:
    """Assicura il client e compone l'SQL della lettura.

    Il simbolo NON entra nel testo della query: viaggia come parametro legato
    (regola 12). Nel testo ci vanno solo l'URL della tabella e un frammento
    scritto da noi, mai da chi chiama dall'esterno.
    """
    _ensure_client()
    return f"SELECT * FROM '{_table_uri(table)}' WHERE symbol = ? {extra}".strip()


def _esegui(sql: str, parametri: list) -> tuple[pd.DataFrame, int]:
    """Esegue la query e ritorna (righe, richieste HTTP fatte per servirla).

    Se il log HTTP non fosse leggibile, questa funzione solleva invece di
    tirare a indovinare: un percorso che non sa dichiarare la propria
    provenienza non deve poter leggere dati (regola 1).
    """
    cursore = _ensure_client().connection.cursor()
    try:
        cursore.execute(SQL_TRUNCATE_LOG)
        frame = cursore.execute(sql, parametri).df()
        richieste = cursore.execute(SQL_COUNT_HTTP).fetchone()[0]
        return frame, int(richieste)
    finally:
        cursore.close()


def _dichiara_provenienza(chiamata, richieste_http: int, ambito: str, categoria: str) -> None:
    """Scrive nel registro da dove e' arrivato il dato, e aggiorna la freschezza.

    La freschezza si marca SOLO quando si e' usciti in rete: e' la data in cui
    quel dato e' stato preso davvero, non quella in cui e' stato riletto.
    """
    if richieste_http > 0:
        chiamata.from_network()
        freshness.mark_fetched(ambito, categoria)
        return
    chiamata.from_cache()


def _esito(frame: pd.DataFrame, ambito: str, categoria: str, provenienza: str) -> Lettura:
    """Confeziona il risultato, con il motivo anche quando e' andata bene."""
    if frame.empty:
        return Lettura(
            frame=frame, scope=ambito, category=categoria, source=provenienza,
            available=False,
            reason=f"nessun dato '{categoria}' per {ambito} nel dataset Defeatbeta",
            action=ACTION_SIMBOLO_ASSENTE,
        )
    return Lettura(
        frame=frame, scope=ambito, category=categoria, source=provenienza,
        available=True,
        reason=f"{len(frame)} righe '{categoria}' per {ambito}, da {provenienza}",
    )


def _simbolo_rifiutato(ambito: str, categoria: str) -> Lettura:
    """Un simbolo scritto male si ferma qui, senza toccare la rete."""
    logger.warning("[DEFEATBETA] simbolo rifiutato: %r", ambito)
    return Lettura(
        frame=pd.DataFrame(), scope=ambito, category=categoria, source=calls.SOURCE_LOCAL,
        available=False,
        reason=f"{ambito!r} non ha la forma di un simbolo",
        action=ACTION_SIMBOLO_MALFORMATO,
    )


def _read(table: str, symbol: str, extra: str = "",
          extra_params: list | None = None, run_id: str | None = None) -> Lettura:
    """Il guscio obbligatorio di ogni lettura: registro, provenienza, freschezza.

    Nessun lettore pubblico parla con DuckDB per conto suo: passano tutti di
    qui, ed e' questo che rende la regola 1 non aggirabile invece che raccomandata.
    """
    categoria = CATEGORIA_PER_TABELLA[table]
    ambito = freshness.normalize_scope(symbol)
    if not SYMBOL_PATTERN.match(ambito):
        return _simbolo_rifiutato(ambito, categoria)

    sql = _prepara(table, extra)
    parametri = [ambito, *(extra_params or [])]

    with calls.track(PROVIDER_NAME, table, scope=ambito, run_id=run_id) as chiamata:
        try:
            with _read_lock:
                frame, richieste = _esegui(sql, parametri)
        except Exception as exc:
            raise DefeatbetaUnavailable(
                f"lettura di {table} per {ambito} fallita: {type(exc).__name__}: {exc}"
            ) from exc
        _dichiara_provenienza(chiamata, richieste, ambito, categoria)
        provenienza = chiamata.source

    return _esito(frame, ambito, categoria, provenienza)


# --- i sei lettori del Blocco 1 --------------------------------------------
#
# Firme volutamente strette: nessun parametro che oggi nessuno passa. Il vecchio
# tradash esponeva `before` su `get_recent_filings` e nessuno dei nove chiamanti
# di produzione lo usava — un controllo sul look-ahead che sembrava esserci.
# I filtri per data e periodo arrivano nel blocco che li usa davvero.

def profile(symbol: str, run_id: str | None = None) -> Lettura:
    """Anagrafica del titolo: settore, industria, paese, descrizione, dipendenti."""
    return _read(TABLE_PROFILE, symbol, run_id=run_id)


def prices(symbol: str, run_id: str | None = None) -> Lettura:
    """Storico OHLCV giornaliero, dal piu' vecchio al piu' recente.

    Il dato piu' fresco e' la chiusura del giorno prima: Defeatbeta non ha
    intraday, ed e' un prezzo che abbiamo accettato di pagare.
    """
    return _read(TABLE_PRICES, symbol, extra="ORDER BY report_date", run_id=run_id)


def statements(symbol: str, run_id: str | None = None) -> Lettura:
    """Bilanci in forma lunga: una riga per (data, voce, tipo, periodo).

    Ritorna tutto quello che c'e' per il titolo — misurato: 3.844 righe per
    AAPL. Selezionare conto e periodicita' e' compito di chi calcola.
    """
    return _read(TABLE_STATEMENT, symbol, run_id=run_id)


def earning_calendar(symbol: str, run_id: str | None = None) -> Lettura:
    """Date degli annunci di risultati, passate e annunciate."""
    return _read(TABLE_EARNING_CALENDAR, symbol, extra="ORDER BY report_date", run_id=run_id)


def sec_filings(symbol: str, run_id: str | None = None) -> Lettura:
    """Documenti depositati alla SEC, dal piu' recente, con l'URL su sec.gov."""
    return _read(TABLE_SEC_FILING, symbol, extra="ORDER BY filing_date DESC", run_id=run_id)


def news(symbol: str, limit: int = config.DEFEATBETA_NEWS_LIMIT_DEFAULT,
         run_id: str | None = None) -> Lettura:
    """Notizie sul titolo, dalla piu' recente. Il limite qui non e' un lusso.

    La tabella pesa 1,1 GB perche' contiene il TESTO degli articoli: una
    lettura senza tetto e' una lettura che non sai quanto ti costa.
    """
    if not 1 <= limit <= config.DEFEATBETA_NEWS_LIMIT_MAX:
        raise ValueError(
            f"limit deve stare fra 1 e {config.DEFEATBETA_NEWS_LIMIT_MAX}, ricevuto {limit}"
        )
    return _read(TABLE_NEWS, symbol, extra="ORDER BY report_date DESC LIMIT ?",
                 extra_params=[limit], run_id=run_id)
