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
from core.schema import GLOBAL_SCOPE

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

# I dirigenti, col ruolo e il compenso dichiarato. E' quanto piu' vicino a un
# dato di governance ci sia in Defeatbeta: il proxy statement (DEF 14A), dove
# stanno consiglio, voti e compensi deliberati, nel dataset non c'e'.
TABLE_OFFICERS = "stock_officers"

# Azioni in circolazione: non ha un lettore suo perche' da sola non dice niente.
# Serve dentro la derivazione dell'universo, dove moltiplicata per l'ultima
# chiusura da' la capitalizzazione.
TABLE_SHARES = "stock_shares_outstanding"

# Le trascrizioni delle earnings call: 2,1 GB, il file piu' grosso del dataset.
# E' la fonte su cui il PIANO rifonda l'earnings review, che prima poggiava
# sulle sorprese di Finnhub — sparite col fornitore.
TABLE_TRANSCRIPTS = "stock_earning_call_transcripts"

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
    TABLE_OFFICERS: "profile",
    TABLE_TRANSCRIPTS: "transcripts",
}

# La derivazione dell'universo non e' la lettura di una tabella: e' una query
# sola che ne unisce quattro, e non appartiene a nessun titolo.
CATEGORY_UNIVERSE = "universe"
CATEGORY_METRICHE = "metriche"

# Il DCF: non e' una tabella del dataset ma un calcolo della libreria sopra i
# bilanci, i prezzi e i rendimenti del Tesoro. Cambia quando cambiano quelli.
CATEGORY_DCF = "dcf"
ENDPOINT_UNIVERSE = "universo:derivazione"

# Tutte le tabelle che questo modulo puo' nominare. L'elenco e' chiuso perche'
# il nome finisce nella clausola FROM, dove un parametro legato non puo' andare.
TABELLE_AMMESSE = frozenset(CATEGORIA_PER_TABELLA) | {TABLE_SHARES}

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
_stato: dict = {"client": None, "cursore_attivo": None}
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


@dataclass(frozen=True)
class Dato:
    """Il risultato di una lettura che non e' una tabella.

    Il DCF della libreria torna un dizionario annidato — tassi, proiezioni,
    valore — e non una tabella. Piegarlo in un DataFrame per farlo entrare in
    `Lettura` avrebbe voluto dire appiattirlo e poi ricostruirlo: stessa forma
    di `Lettura`, campo diverso.
    """
    dato: dict | None
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

    if table not in TABELLE_AMMESSE:
        raise ValueError(f"tabella non prevista: {table!r}")
    return HuggingFaceClient().get_url_path(table)


def _prepara(table: str, extra: str) -> str:
    """Assicura il client e compone l'SQL della lettura.

    Il simbolo NON entra nel testo della query: viaggia come parametro legato
    (regola 12). Nel testo ci vanno solo l'URL della tabella e un frammento
    scritto da noi, mai da chi chiama dall'esterno.
    """
    _ensure_client()
    return f"SELECT * FROM '{_table_uri(table)}' WHERE symbol = ? {extra}".strip()


# Quante volte si riprova una lettura fallita. Una: riprovare all'infinito
# nasconderebbe un guasto vero dietro a un ritardo.
TENTATIVI = 2


def _uri_nella_query(sql: str) -> list[str]:
    """TUTTI gli URL di parquet dentro la query.

    Tutti e non il primo: la derivazione dell'universo ne unisce cinque, e
    svuotare la cache di uno solo — quello che capitava per primo nel testo —
    lascerebbe intatto proprio il file rotto.
    """
    return [pezzo for pezzo in sql.split("'") if pezzo.startswith("http")]


def _ricomincia_da_capo(sql: str) -> None:
    """Svuota le cache, dentro e fuori dal processo, e forza un client nuovo.

    Il dataset si aggiorna ogni notte. La libreria confronta `spec.json` con la
    cache **solo quando costruisce il client**: un processo acceso da prima
    dell'aggiornamento non ripete quel controllo mai piu' e continua a mescolare
    byte di due versioni.

    Ci sono volute tre correzioni per farlo davvero, e le prime due sbagliavano
    perche' non avevo verificato dove stessero le cose:

    1. la cache non e' solo su disco. `cache_httpfs` tiene anche i metadati dei
       parquet **in memoria, per otto ore**: svuotare i file sul disco lasciava
       in piedi i piedini di pagina vecchi;
    2. **la libreria tiene il client in un singleton suo**. Azzerare il nostro
       riferimento e richiamare `get_duckdb_client()` restituiva esattamente lo
       stesso oggetto, con le stesse cache in memoria — cioe' non ricostruiva
       niente.

    Per questo qui si tocca `duckdb_client._instance`, che e' privato: non e'
    eleganza, e' l'unico modo che la libreria lascia per ottenere davvero una
    connessione nuova, e con lei il suo controllo su `spec.json`.
    """
    cliente = _stato.get("client")
    indirizzi = _uri_nella_query(sql)

    if cliente is not None:
        for uri in indirizzi:
            try:
                cliente.connection.execute(f"SELECT cache_httpfs_clear_cache_for_file('{uri}')")
            except Exception:
                logger.exception("[DEFEATBETA] cache su disco non svuotata per %s", uri)
        try:
            # Questa svuota anche cio' che sta in memoria, che e' il pezzo che
            # le prime due correzioni non toccavano.
            cliente.connection.execute("SELECT cache_httpfs_clear_cache()")
        except Exception:
            logger.exception("[DEFEATBETA] cache in memoria non svuotata")

    _dimentica_il_client()
    logger.warning(
        "[DEFEATBETA] lettura fallita: svuotate le cache di %d file, quella in memoria "
        "e il client, riprovo una volta. Succede quando il dataset si aggiorna mentre "
        "il processo e' acceso.", len(indirizzi),
    )


def _dimentica_il_client() -> None:
    """Fa dimenticare il client anche alla libreria, non solo a noi."""
    _stato["client"] = None
    try:
        from defeatbeta_api.client import duckdb_client  # noqa: PLC0415

        duckdb_client._instance = None
    except ImportError:
        # La libreria non e' importata: non c'e' nessun singleton da azzerare.
        pass


def _esegui(sql: str, parametri: list) -> tuple[pd.DataFrame, int]:
    """Esegue la query e ritorna (righe, richieste HTTP fatte per servirla).

    Se il log HTTP non fosse leggibile, questa funzione solleva invece di
    tirare a indovinare: un percorso che non sa dichiarare la propria
    provenienza non deve poter leggere dati (regola 1).

    **Un secondo tentativo, e uno solo.** Il dataset si aggiorna ogni notte e la
    libreria confronta `spec.json` con la cache solo quando costruisce il
    client: un processo acceso da prima dell'aggiornamento continua a mescolare
    byte di due versioni. Misurato due volte in un giorno, con due errori
    diversi. Al primo fallimento si butta via cache e client e si riprova; al
    secondo si passa l'errore a chi ha chiamato, perche' e' un guasto vero.
    """
    for tentativo in range(TENTATIVI):
        cursore = _ensure_client().connection.cursor()
        _stato["cursore_attivo"] = cursore
        try:
            cursore.execute(SQL_TRUNCATE_LOG)
            frame = cursore.execute(sql, parametri).df()
            richieste = cursore.execute(SQL_COUNT_HTTP).fetchone()[0]
            return frame, int(richieste)
        except Exception:
            # Non si guarda il TESTO dell'errore. Il primo tentativo di
            # riconoscere una cache guasta lo faceva, e ha mancato la seconda
            # forma che si e' presentata il giorno dopo — `TProtocolException`
            # invece di `don't know what type`. Una query ben scritta non
            # fallisce: se fallisce, si ricomincia da capo una volta e, se
            # fallisce ancora, e' un guasto vero e passa a chi ha chiamato.
            if tentativo == TENTATIVI - 1:
                raise
            _ricomincia_da_capo(sql)
        finally:
            _stato["cursore_attivo"] = None
            cursore.close()

    raise DefeatbetaUnavailable("lettura non riuscita dopo il secondo tentativo")


def interrupt() -> bool:
    """Ferma la query in corso, se ce n'e' una. Ritorna True se ha interrotto qualcosa.

    Serve alla derivazione dell'universo, che e' una query sola da minuti:
    spezzarla in pezzi per poterla fermare avrebbe significato rileggere piu'
    volte lo stesso parquet. DuckDB sa interrompere una query in corso —
    misurato: fermata in 1,00 s — e le letture qui sono serializzate, quindi il
    cursore in volo e' sempre al massimo uno.
    """
    cursore = _stato.get("cursore_attivo")
    if cursore is None:
        return False
    cursore.interrupt()
    logger.info("[DEFEATBETA] interruzione richiesta sulla query in corso")
    return True


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


def _leggi_tracciata(endpoint: str, categoria: str, ambito: str,
                     sql: str, parametri: list, run_id: str | None) -> tuple[pd.DataFrame, str]:
    """Il guscio obbligatorio: registro, provenienza, freschezza.

    Nessuna lettura parla con DuckDB per conto suo — passano tutte di qui, ed
    e' questo che rende la regola 1 non aggirabile invece che raccomandata.
    Ritorna le righe e la provenienza con cui sono arrivate.
    """
    with calls.track(PROVIDER_NAME, endpoint, scope=ambito, run_id=run_id) as chiamata:
        try:
            with _read_lock:
                frame, richieste = _esegui(sql, parametri)
        except Exception as exc:
            raise DefeatbetaUnavailable(
                f"lettura di {endpoint} per {ambito} fallita: {type(exc).__name__}: {exc}"
            ) from exc
        _dichiara_provenienza(chiamata, richieste, ambito, categoria)
        return frame, chiamata.source


def _read(table: str, symbol: str, extra: str = "",
          extra_params: list | None = None, run_id: str | None = None) -> Lettura:
    """Una lettura che riguarda un titolo: l'ambito e' il simbolo."""
    categoria = CATEGORIA_PER_TABELLA[table]
    ambito = freshness.normalize_scope(symbol)
    if not SYMBOL_PATTERN.match(ambito):
        return _simbolo_rifiutato(ambito, categoria)

    frame, provenienza = _leggi_tracciata(
        table, categoria, ambito, _prepara(table, extra), [ambito, *(extra_params or [])], run_id
    )
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


def officers(symbol: str, run_id: str | None = None) -> Lettura:
    """I dirigenti: nome, ruolo, eta', compenso dichiarato, opzioni.

    Serve alla fase governance del report qualitativo. Non e' un dato di
    governance completo e il prompt lo dichiara: consiglio di amministrazione,
    compensi deliberati e classi di voto stanno nel proxy statement, che
    Defeatbeta non porta.
    """
    return _read(TABLE_OFFICERS, symbol, run_id=run_id)


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


def news_che_nominano(symbol: str, parola: str,
                      limit: int = config.DEFEATBETA_NEWS_LIMIT_DEFAULT,
                      run_id: str | None = None) -> Lettura:
    """Le notizie su un titolo che nominano una parola, dalla piu' recente.

    Serve al rilevatore di spin-off: le notizie che ne parlano possono essere
    vecchie di mesi, e `news()` porta solo le ultime per data. Cercare nel
    TITOLO e non nel corpo e' una scelta di costo — il corpo e' un elenco di
    paragrafi da scartare riga per riga su 1,1 GB — e una di precisione: un
    articolo che nomina uno spin-off di passaggio nel decimo paragrafo non
    parla di quello.
    """
    if not 1 <= limit <= config.DEFEATBETA_NEWS_LIMIT_MAX:
        raise ValueError(
            f"limit deve stare fra 1 e {config.DEFEATBETA_NEWS_LIMIT_MAX}, ricevuto {limit}"
        )
    return _read(TABLE_NEWS, symbol,
                 extra="AND lower(title) LIKE ? ORDER BY report_date DESC LIMIT ?",
                 extra_params=[f"%{parola.strip().lower()}%", limit], run_id=run_id)


def transcripts(symbol: str, limit: int = config.TRASCRIZIONI_LETTE,
                run_id: str | None = None) -> Lettura:
    """Le trascrizioni delle earnings call, dalla piu' recente.

    Il limite non e' un lusso: una sola trascrizione sono ~46.000 caratteri, e
    la tabella pesa 2,1 GB perche' le contiene per intero. Chiederne dieci
    significa chiedere mezzo milione di caratteri.
    """
    if not 1 <= limit <= config.TRASCRIZIONI_MASSIME:
        raise ValueError(
            f"limit deve stare fra 1 e {config.TRASCRIZIONI_MASSIME}, ricevuto {limit}"
        )
    return _read(TABLE_TRANSCRIPTS, symbol,
                 extra="ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT ?",
                 extra_params=[limit], run_id=run_id)


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


# --- le metriche gia' calcolate dalla libreria ------------------------------
#
# `Ticker` porta un'ottantina di metodi che calcolano ROE, ROIC, margini, debito
# netto, multipli e — cosa che il vecchio tradash non aveva affatto — i
# confronti di SETTORE. Sono SQL sui parquet, non chiamate di rete in piu'.
#
# Non li si usa direttamente: passano di qui, e quindi dal registro, con la
# provenienza misurata come ogni altra lettura. La differenza fra usarli e
# scriverli a mano non deve essere che gli uni si vedono nel log e gli altri no.
#
# L'elenco e' chiuso perche' il nome del metodo finisce in un `getattr`: chiuso,
# non e' una porta.
METRICHE = {
    # sul titolo
    "roe": "capitale proprio: quanto rende",
    "roa": "attivo: quanto rende",
    "roic": "capitale investito: quanto rende",
    "roce": "capitale impiegato: quanto rende",
    "wacc": "costo medio del capitale",
    "net_debt_ttm": "debito netto",
    "debt_to_equity": "debito su patrimonio",
    "enterprise_value": "valore d'impresa",
    "ttm_revenue": "ricavi negli ultimi dodici mesi",
    "ttm_fcf": "flusso di cassa libero negli ultimi dodici mesi",
    "ttm_ebitda": "EBITDA negli ultimi dodici mesi",
    "ttm_pe": "prezzo su utili",
    "ps_ratio": "prezzo su ricavi",
    "pb_ratio": "prezzo su patrimonio",
    "peg_ratio": "prezzo su utili corretto per la crescita",
    "market_capitalization": "capitalizzazione",
    "quarterly_gross_margin": "margine lordo, per trimestre",
    "quarterly_operating_margin": "margine operativo, per trimestre",
    "quarterly_net_margin": "margine netto, per trimestre",
    "quarterly_fcf_margin": "margine di cassa, per trimestre",
    "quarterly_revenue_yoy_growth": "crescita dei ricavi su un anno",
    "beta": "beta rispetto al mercato",
    # sul settore: il confronto che il vecchio sistema non sapeva fare
    "industry_ttm_pe": "prezzo su utili dell'industria",
    "industry_roe": "capitale proprio dell'industria: quanto rende",
    "industry_roa": "attivo dell'industria: quanto rende",
    "industry_roic": "capitale investito dell'industria: quanto rende",
    "industry_quarterly_gross_margin": "margine lordo dell'industria",
    "industry_quarterly_net_margin": "margine netto dell'industria",
}

# Alcune costano molto piu' di altre: `industry_ttm_pe` misurato in 32 secondi
# contro gli 0,6 di `roe`. Chi le chiama in gruppo deve saperlo, e chi le chiama
# da una pagina deve chiamarle una alla volta.
METRICHE_LENTE = frozenset({"industry_ttm_pe", "wacc", "peg_ratio", "enterprise_value"})


def _ticker(simbolo: str):
    """L'oggetto della libreria per un titolo. Usa la connessione che abbiamo gia'."""
    from defeatbeta_api.data.ticker import Ticker  # noqa: PLC0415

    _ensure_client()
    return Ticker(simbolo, log_level=DUCKDB_LOG_LEVEL_SILENT)


def _esegui_metodo(simbolo: str, metodo: str) -> tuple[pd.DataFrame, int]:
    """Chiama un metodo della libreria contando le richieste HTTP che ha fatto.

    Il conteggio funziona anche se il metodo usa un cursore suo: il log di
    DuckDB e' della connessione, non del cursore.
    """
    cursore = _ensure_client().connection.cursor()
    _stato["cursore_attivo"] = cursore
    try:
        cursore.execute(SQL_TRUNCATE_LOG)
        frame = getattr(_ticker(simbolo), metodo)()
        richieste = cursore.execute(SQL_COUNT_HTTP).fetchone()[0]
        return frame, int(richieste)
    finally:
        _stato["cursore_attivo"] = None
        cursore.close()


def metrica(simbolo: str, nome: str, run_id: str | None = None) -> Lettura:
    """Una metrica gia' calcolata dalla libreria, letta attraverso il registro.

    Ritorna la SERIE storica con le sue date, non un numero solo: il taglio a
    una data passata lo fa chi legge, come per i bilanci. E' il motivo per cui
    questi metodi si possono usare anche nelle ricostruzioni.
    """
    if nome not in METRICHE:
        raise ValueError(f"metrica non prevista: {nome!r}. "
                         f"Ci sono: {', '.join(sorted(METRICHE))}")

    ambito = freshness.normalize_scope(simbolo)
    if not SYMBOL_PATTERN.match(ambito):
        return _simbolo_rifiutato(ambito, CATEGORY_METRICHE)

    with calls.track(PROVIDER_NAME, f"metrica:{nome}", scope=ambito, run_id=run_id) as chiamata:
        try:
            with _read_lock:
                frame, richieste = _esegui_metodo(ambito, nome)
        except Exception as exc:
            raise DefeatbetaUnavailable(
                f"metrica {nome} per {ambito} fallita: {type(exc).__name__}: {exc}"
            ) from exc
        _dichiara_provenienza(chiamata, richieste, ambito, CATEGORY_METRICHE)
        provenienza = chiamata.source

    return _esito(frame, ambito, CATEGORY_METRICHE, provenienza)


def dcf(simbolo: str, run_id: str | None = None) -> Dato:
    """Il flusso di cassa scontato della libreria: tassi, proiezioni, prezzo equo.

    E' il calcolo piu' pesante che la libreria faccia — legge bilanci, prezzi,
    capitalizzazione e rendimenti del Tesoro — e per questo passa dal registro
    come tutto il resto: una chiamata che non si vede e' una chiamata che non
    si puo' fermare.

    Il risultato NON e' un verdetto, e chi lo usa non deve leggerlo come tale:
    la libreria ci mette dentro anche un campo `recommendation` con scritto
    "Buy" o "Sell", che questo sistema non propaga.
    """
    ambito = freshness.normalize_scope(simbolo)
    if not SYMBOL_PATTERN.match(ambito):
        rifiuto = _simbolo_rifiutato(ambito, CATEGORY_DCF)
        return Dato(dato=None, scope=rifiuto.scope, category=CATEGORY_DCF,
                    source=rifiuto.source, available=False, reason=rifiuto.reason,
                    action=rifiuto.action)

    with calls.track(PROVIDER_NAME, "dcf", scope=ambito, run_id=run_id) as chiamata:
        try:
            with _read_lock:
                calcolo, richieste = _esegui_metodo(ambito, "dcf_data")
        except Exception as exc:
            raise DefeatbetaUnavailable(
                f"dcf per {ambito} fallito: {type(exc).__name__}: {exc}"
            ) from exc
        _dichiara_provenienza(chiamata, richieste, ambito, CATEGORY_DCF)
        provenienza = chiamata.source

    if not isinstance(calcolo, dict) or not calcolo.get("dcf_template"):
        return Dato(dato=None, scope=ambito, category=CATEGORY_DCF, source=provenienza,
                    available=False,
                    reason=f"la libreria non ha prodotto un DCF per {ambito}: "
                           f"servono bilanci, flusso di cassa e capitalizzazione",
                    action=ACTION_SIMBOLO_ASSENTE)

    return Dato(dato=calcolo, scope=ambito, category=CATEGORY_DCF, source=provenienza,
                available=True, reason=f"DCF di {ambito}, da {provenienza}")


# --- l'universo: una query sola che ne unisce quattro ----------------------

def _prepara_universo() -> str:
    """Compone la derivazione dell'universo. Nessun parametro: riguarda tutti.

    Quattro tabelle in una query sola perche' il pezzo caro e' leggere il
    parquet dei prezzi (443 MB): farlo una volta e portarsi via ultimo prezzo e
    volume medio insieme costa meno che passarci due volte.

    Il JOIN parte dal profilo ed e' un LEFT: chi non ha prezzo entra lo stesso,
    con la casella vuota, e quante siano si dichiara (regola 5). Il contrario —
    tenere solo chi ha tutto — farebbe sparire in silenzio 2.636 titoli senza
    capitalizzazione.
    """
    _ensure_client()
    profilo = _table_uri(TABLE_PROFILE)
    prezzi = _table_uri(TABLE_PRICES)
    azioni = _table_uri(TABLE_SHARES)
    calendario = _table_uri(TABLE_EARNING_CALENDAR)
    depositi = _table_uri(TABLE_SEC_FILING)
    return f"""
        WITH prezzi AS (
            SELECT symbol,
                   CAST(report_date AS DATE) AS giorno,
                   close, volume,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol ORDER BY CAST(report_date AS DATE) DESC
                   ) AS posizione
            FROM '{prezzi}'
        ),
        ultimo_prezzo AS (
            SELECT symbol, close AS last_close, giorno AS last_close_date
            FROM prezzi WHERE posizione = 1
        ),
        volume_medio AS (
            SELECT symbol, AVG(volume) AS avg_volume_30d
            FROM prezzi WHERE posizione <= {config.UNIVERSE_AVG_VOLUME_SESSIONS}
            GROUP BY symbol
        ),
        azioni_recenti AS (
            SELECT symbol, shares_outstanding,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol ORDER BY CAST(report_date AS DATE) DESC
                   ) AS posizione
            FROM '{azioni}'
        ),
        ultime_azioni AS (
            SELECT symbol, shares_outstanding FROM azioni_recenti WHERE posizione = 1
        ),
        -- Il nome della societa' non sta nel profilo: sta in queste due, con
        -- forme diverse. Il calendario scrive "NVIDIA Corporation", l'indice
        -- dei depositi "NVIDIA CORP" — si preferisce il primo, che e' scritto
        -- per essere letto, e si ripiega sul secondo, che copre molti piu'
        -- titoli (ETF compresi).
        nome_calendario AS (
            SELECT symbol, MAX(name) AS nome FROM '{calendario}'
            WHERE name IS NOT NULL AND name <> '' GROUP BY symbol
        ),
        nome_deposito AS (
            SELECT symbol, MAX(company_name) AS nome FROM '{depositi}'
            WHERE company_name IS NOT NULL AND company_name <> '' GROUP BY symbol
        )
        SELECT p.symbol,
               COALESCE(nc.nome, nd.nome) AS name,
               p.sector,
               p.industry,
               -- Nome esplicito: e' il paese della societa', non della borsa.
               p.country AS company_country,
               p.full_time_employees AS employees,
               u.last_close,
               CAST(u.last_close_date AS VARCHAR) AS last_close_date,
               v.avg_volume_30d,
               a.shares_outstanding,
               u.last_close * a.shares_outstanding AS market_cap
        FROM '{profilo}' p
        LEFT JOIN ultimo_prezzo  u ON p.symbol = u.symbol
        LEFT JOIN volume_medio   v ON p.symbol = v.symbol
        LEFT JOIN ultime_azioni  a ON p.symbol = a.symbol
        LEFT JOIN nome_calendario nc ON p.symbol = nc.symbol
        LEFT JOIN nome_deposito   nd ON p.symbol = nd.symbol
    """


def universe(run_id: str | None = None) -> Lettura:
    """L'universo derivato: un titolo per riga, con quanto serve a filtrarlo.

    Misurato il 29/08/2026: 11.256 titoli. La prima volta costa 214 s e circa
    443 MB — l'intero parquet dei prezzi finisce nella cache; dopo, a cache
    calda, 7,85 s. E' un lavoro lungo: chi lo chiama deve aprirlo con
    `registry.job` e poterlo fermare con `interrupt()`.

    ATTENZIONE alla colonna `country`: e' il paese della SOCIETA', non della
    borsa. BABA risulta 'China' e SHOP 'Canada' pur essendo quotate negli USA,
    e 635 titoli non ce l'hanno affatto. Filtrare l'universo su
    `country = 'United States'` butterebbe via 3.783 titoli quotati negli USA:
    il perimetro "solo mercato USA" e' gia' garantito dal dataset, che contiene
    solo listini americani.
    """
    frame, provenienza = _leggi_tracciata(
        ENDPOINT_UNIVERSE, CATEGORY_UNIVERSE, GLOBAL_SCOPE, _prepara_universo(), [], run_id
    )
    return _esito(frame, GLOBAL_SCOPE, CATEGORY_UNIVERSE, provenienza)
