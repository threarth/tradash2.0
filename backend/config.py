"""
config.py — configurazione centrale di tradash2.0.
# feat (Blocco 0): unico posto in cui vivono percorsi, soglie e costanti globali.

Nessun valore numerico o stringa fissa deve comparire sparso nel codice: se
serve una soglia, si dichiara qui con un nome che spiega cosa significa.
Nessuna credenziale: le chiavi API stanno in .env, mai nel sorgente.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Il file delle credenziali. Non e' nel repo — `.gitignore` lo esclude — e
# questo modulo lo legge solo per metterne il contenuto nell'ambiente, che e'
# da dove le librerie se lo aspettano.
ENV_PATH = BASE_DIR / ".env"


def _carica_env(percorso: Path) -> list[str]:
    """Mette in ambiente le variabili di `.env`, senza sovrascrivere quelle vere.

    Quindici righe invece di una dipendenza: `python-dotenv` farebbe questo, e
    un file di `CHIAVE=valore` non ha bisogno di un parser.

    **Chi c'e' gia' vince.** Una variabile esportata nella shell e' una scelta
    deliberata di chi ha lanciato il processo; un file letto da disco non deve
    poterla ribaltare di nascosto.

    Ritorna i NOMI caricati — mai i valori: questo elenco finisce nei log
    all'avvio, e un valore li' dentro sarebbe una chiave in chiaro su disco.
    """
    if not percorso.is_file():
        return []

    caricate = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        pulita = riga.strip()
        if not pulita or pulita.startswith("#") or "=" not in pulita:
            continue
        nome, _, valore = pulita.partition("=")
        nome = nome.removeprefix("export ").strip()
        if nome and nome not in os.environ:
            os.environ[nome] = valore.strip().strip("\"'")
            caricate.append(nome)
    return caricate


CHIAVI_CARICATE = _carica_env(ENV_PATH)

# Il database dell'uso reale. Dichiarato a parte perche' `core/db.py` lo usa
# per rifiutarsi di aprirlo mentre gira la suite: la vecchia suite scriveva sul
# database vero, e "stiamo attenti" non e' una difesa.
PRODUCTION_DB_PATH = BASE_DIR / "tradash2.db"

# Percorso effettivo. I test lo spostano su una cartella temporanea.
DB_PATH = Path(os.environ.get("TRADASH2_DB", PRODUCTION_DB_PATH))

# Quanto SQLite aspetta prima di dichiarare il database occupato.
SQLITE_TIMEOUT_S = 30.0

# Porta del server di sviluppo Flask.
DEV_SERVER_PORT = 5001

# Dove Vite mette il build della SPA. Flask lo serve come statici: e' l'unico
# modo di avere un solo processo invece di due (niente SvelteKit, regola 1).
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


# Ogni quanto un dato torna vecchio, per CATEGORIA. Un TTL unico globale e' il
# difetto che nel vecchio sistema teneva un prezzo fermo per undici giorni
# mentre il market cap accanto risultava "fresco": la freschezza si misura sul
# dato che mostri, non su un campo vicino.
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR

FRESHNESS_TTL_S: dict[str, int] = {
    "price": 12 * SECONDS_PER_HOUR,          # Defeatbeta pubblica la chiusura di notte
    "profile": 7 * SECONDS_PER_DAY,          # settore/industria cambiano di rado
    "statements": 1 * SECONDS_PER_DAY,       # bilanci: nuovi solo a trimestre
    "earning_calendar": 1 * SECONDS_PER_DAY,
    "sec_filings": 6 * SECONDS_PER_HOUR,
    "transcripts": 1 * SECONDS_PER_DAY,
    "news": 2 * SECONDS_PER_HOUR,
    "treasury_yield": 12 * SECONDS_PER_HOUR,
    "universe": 1 * SECONDS_PER_DAY,       # dato globale, non di un titolo
    "metriche": 1 * SECONDS_PER_DAY,       # calcolate sui bilanci: cambiano a trimestre
    "dcf": 1 * SECONDS_PER_DAY,            # idem: e' un calcolo sopra i bilanci
}

# Quali categorie riguardano UN TITOLO. Le altre — l'universo, il rendimento del
# Tesoro — sono dati globali: chiederne la freschezza «per AVGO» produrrebbe la
# frase «universe mai preso per AVGO», che sembra un buco e non lo e'.
FRESHNESS_CATEGORIE_PER_TITOLO = (
    "price", "profile", "statements", "earning_calendar", "sec_filings",
    "transcripts", "news", "metriche", "dcf",
)

# TTL usato quando una categoria non e' in tabella. Volutamente cortissimo: una
# categoria non dichiarata deve dare fastidio, non passare inosservata.
FRESHNESS_TTL_UNKNOWN_S = 5 * SECONDS_PER_MINUTE

# Quante righe di log restituisce al massimo l'endpoint delle chiamate.
CALLS_PAGE_LIMIT_DEFAULT = 100
CALLS_PAGE_LIMIT_MAX = 1000

# --- Defeatbeta: la fonte unica dei dati di mercato ------------------------

# Dove `cache_httpfs` tiene i byte gia' scaricati dei parquet. La libreria li
# metterebbe in /tmp/defeatbeta/cache/<versione>, che su molte macchine sparisce
# al riavvio: qui la cache sta nel progetto, dove sopravvive e si puo' guardare.
# Misurato il 29/08/2026: 2,2 MB bastano a servire i prezzi di un titolo da un
# parquet di 443 MB, e la seconda lettura scende da 8,9 s a 0,03 s.
PRODUCTION_DEFEATBETA_CACHE_DIR = BASE_DIR / "data" / "httpfs_cache"
DEFEATBETA_CACHE_DIR = Path(
    os.environ.get("TRADASH2_DEFEATBETA_CACHE", PRODUCTION_DEFEATBETA_CACHE_DIR)
)

# Quante notizie si leggono per volta. Il tetto non e' un lusso: la tabella
# delle news pesa 1,1 GB perche' contiene il testo degli articoli, e una
# lettura senza limite e' una lettura di cui non sai il costo.
DEFEATBETA_NEWS_LIMIT_DEFAULT = 50
DEFEATBETA_NEWS_LIMIT_MAX = 500

# --- as_of: quando un bilancio e' diventato pubblico ------------------------
#
# Un trimestre che chiude il 30 giugno viene depositato a inizio agosto. Un
# analisi ricostruita al 15 luglio, se tronca sulla fine del periodo, vede un
# bilancio che allora non esisteva: sono ~40 giorni di futuro, proprio nella
# finestra in cui il prezzo si muove di piu'. E' il look-ahead piu' grave e meno
# visibile, perche' non produce nessun errore — solo un backtest bravissimo.
#
# Dove non c'e' la data di deposito reale si usa un ritardo prudente, e prudente
# qui significa TARDI: meglio non vedere un dato che c'era, che vederne uno che
# non c'era. Sono gli estremi delle scadenze SEC per un depositante non
# accelerato.
AS_OF_RITARDO_TRIMESTRALE_GIORNI = 45
AS_OF_RITARDO_ANNUALE_GIORNI = 75

# Le due fonti non si allineano sempre al giorno: un trimestre "chiuso il 28
# giugno" nei bilanci puo' comparire come 30 giugno nell'indice dei depositi.
# Senza tolleranza si ricadrebbe sulla stima pur avendo il dato vero.
AS_OF_TOLLERANZA_PERIODO_GIORNI = 10

# Quanti documenti e quante notizie mostra la scheda di un titolo. Un tetto,
# perche' un titolo con vent'anni di storia ne ha centinaia e nessuno li legge.
FILINGS_MOSTRATI = 60
NEWS_MOSTRATE = 40

# --- Grafici ---------------------------------------------------------------

# Le impostazioni del grafico sono TUE come la watchlist: quali indicatori hai
# scelto per quale titolo non si ricostruisce da nessuna parte. Stesso trattamento:
# un file JSON leggibile, fuori da git, che il rebuild del database non tocca.
PRODUCTION_GRAFICI_PATH = BASE_DIR / "data" / "grafici.json"
GRAFICI_PATH = Path(os.environ.get("TRADASH2_GRAFICI", PRODUCTION_GRAFICI_PATH))
GRAFICI_FILE_VERSION = 1

# Gli intervalli che il selettore del grafico offre, in giorni di calendario.
# `None` significa tutta la storia disponibile.
INTERVALLI_GRAFICO = {
    "1M": 31, "3M": 92, "6M": 183, "1A": 366, "5A": 1827, "tutto": None,
}
INTERVALLO_GRAFICO_PREDEFINITO = "1A"

# --- Universo -------------------------------------------------------------

# Su quante sedute si media il volume. Sedute, non giorni di calendario: un
# titolo poco liquido puo' non scambiare per settimane, e "ultimi 30 giorni"
# gli darebbe una media costruita su tre scambi.
UNIVERSE_AVG_VOLUME_SESSIONS = 30

# Quanti titoli restituisce al massimo l'elenco dell'universo. L'universo intero
# e' 11.256 righe: mandarle tutte a una pagina e' un modo per renderla lenta.
UNIVERSE_PAGE_LIMIT_DEFAULT = 100
UNIVERSE_PAGE_LIMIT_MAX = 2000

# --- Trascrizioni delle earnings call --------------------------------------
#
# Una sola trascrizione sono circa 46.000 caratteri, e la tabella pesa 2,1 GB
# perche' le contiene per intero. Il tetto e' basso apposta: due chiamate
# coprono il trimestre e quello prima, che e' cio' che serve per vedere se la
# guidance e' stata mantenuta.
TRASCRIZIONI_LETTE = 2
TRASCRIZIONI_MASSIME = 8

# Quanto si tiene di ogni risposta prima di troncarla. Le risposte di una call
# arrivano a migliaia di caratteri; il tema si capisce dai primi. Il taglio si
# DICHIARA nel referto: un testo troncato mostrato senza dirlo si legge come se
# quella fosse tutta la risposta.
TRASCRIZIONE_RISPOSTA_CARATTERI = 1200

# --- Filing salvati a mano (Blocco 8) --------------------------------------
#
# L'analisi qualitativa ha come fonte primaria il TESTO dei documenti SEC, che
# Defeatbeta non ha: ha l'indice (tipo, date, URL) ma non il contenuto. Il testo
# lo scarichi tu da sec.gov e lo salvi qui; il sistema ti dice QUALI servono e
# con quale nome.
PRODUCTION_FILING_DIR = BASE_DIR / "data" / "filings"
FILING_DIR = Path(os.environ.get("TRADASH2_FILINGS", PRODUCTION_FILING_DIR))

# Quali documenti servono all'analisi qualitativa: l'ultimo annuale, e gli
# ultimi trimestrali. Tre documenti coprono l'anno in corso piu' il quadro
# completo dell'esercizio precedente.
FILING_QUALITATIVA_ANNUALI = 1
FILING_QUALITATIVA_TRIMESTRALI = 2

# Le estensioni che sappiamo leggere. EDGAR serve HTML; il testo semplice si
# accetta perche' e' cio' che ottieni con "salva come testo".
FILING_ESTENSIONI = (".html", ".htm", ".txt")

# Oltre questa dimensione un file non e' un filing: e' qualcos'altro salvato
# per sbaglio, e leggerlo tutto per accorgersene costa.
FILING_DIMENSIONE_MASSIMA_MB = 40

# Quanto si manda al modello di una singola sezione di filing. Le Risk Factors
# di un 10-K grande passano i 200.000 caratteri, e sono ~50.000 token per una
# sola sezione di una sola fase: il tetto e' li' perche' il costo di un report
# sia prevedibile. Il taglio si dichiara sempre — nel prompt e nel referto.
QUALITATIVA_SEZIONE_CARATTERI = 60_000

# Quanti depositi recenti si elencano alla fase prospettica. E' l'indice: tipo
# e data, non il testo, che vorrebbe dire scaricarli.
QUALITATIVA_DEPOSITI_RECENTI = 12

# Quante citazioni si chiedono al massimo. Misurato: senza tetto il modello ne
# ha prodotte tante da sbattere contro il limite di token in uscita, e il JSON
# e' arrivato troncato — cioe' si sono perse TUTTE, non le ultime. Meglio venti
# scelte che quaranta tagliate a meta' di una parentesi.
QUALITATIVA_CITAZIONI_MASSIME = 24

# Il capitale di partenza del simulatore psicologico, quando non lo si dice.
# Diecimila e' una cifra che si legge a colpo d'occhio: le variazioni in dollari
# si traducono a mente in percentuali.
SIMULATORE_CAPITALE_PREDEFINITO = 10_000.0

# Il verdetto legge i referti degli altri metodi. Quanto se ne manda di ognuno,
# e da quanti giorni un referto va segnalato come vecchio: mettere insieme una
# lettura di tre mesi fa e una di stamattina produce una sintesi coerente e
# sbagliata, e il testo da solo non direbbe quando e' stato scritto.
VERDETTO_TESTO_CARATTERI = 2_000
VERDETTO_VOCI_MASSIME = 12
VERDETTO_GIORNI_VECCHIO = 30

# --- Modelli linguistici (Blocco 8) ----------------------------------------
#
# Il modello si dichiara qui perche' e' una scelta che si paga: cambiarlo cambia
# il conto, e chi guarda un referto deve poter sapere chi l'ha scritto.
#
# MISURATO sul vecchio sistema, e da non riscoprire: **Haiku fallisce le fasi
# dell'analisi qualitativa** — su Q ha prodotto un submit invalido bruciando
# $0,24, mentre Sonnet ha chiuso a $0,99. Haiku resta buono per compressione e
# triage, non per le fasi.
LLM_MODELLO = os.environ.get("TRADASH2_MODELLO", "gpt-5.5")
LLM_MODELLO_COMPRESSIONE = "gpt-5.4-mini"

# Quanto il modello deve ragionare prima di rispondere. Vale per i modelli
# OpenAI, che vogliono un livello esplicito; quelli Anthropic decidono da soli
# (pensiero adattivo), e li' questo valore non si usa.
LLM_SFORZO = os.environ.get("TRADASH2_SFORZO", "medium")

# Il tetto di token in uscita. Sopra i 16k conviene lo streaming, altrimenti si
# rischia di sbattere contro il timeout HTTP prima della fine della risposta.
LLM_TOKEN_MASSIMI = 16000

# Le fasi che hanno bisogno di piu' spazio. Misurato dal vivo: la fase delle
# citazioni su NVDA ha prodotto 16.000 token esatti — cioe' ha sbattuto contro
# il tetto — e il JSON e' arrivato tagliato a meta'. Deve elencare una citazione
# per ogni affermazione di nove sezioni, ognuna con la sua frase letterale: e'
# la risposta piu' lunga che questo sistema chieda.
LLM_TOKEN_PER_FASE = {
    "qualitativa_fase4": 24000,
}

# Prezzo per milione di token, per calcolare il costo di ogni chiamata. Da
# aggiornare quando cambiano i listini: un costo calcolato su prezzi vecchi e'
# peggio di nessun costo, perche' sembra un dato.
# Da dove viene ogni riga, perche' un prezzo senza provenienza e' un numero in
# dollari che sembra misurato:
#
# - I modelli Anthropic: listino pubblico noto.
# - **gpt-5.5: riferito dall'utente il 31/08/2026 da una ricerca sul web**, non
#   letto dal cruscotto ne' da un'API. E' il dato migliore che abbiamo e va
#   benissimo per l'ordine di grandezza; se un giorno il conto non tornasse col
#   consuntivo OpenAI, si comincia a guardare da qui.
#
# Un modello che non e' in questa tabella non prende un costo inventato: prende
# zero, e `speso_totale()` dichiara quante chiamate non sanno quanto sono
# costate. Il listino si puo' aggiungere DOPO — `manage.py costi` ricalcola le
# chiamate gia' registrate, perche' i token sono salvati riga per riga.
LLM_PREZZI = {
    "claude-opus-5": {"ingresso": 5.00, "uscita": 25.00},
    "claude-sonnet-5": {"ingresso": 2.00, "uscita": 10.00},
    "claude-haiku-4-5": {"ingresso": 1.00, "uscita": 5.00},
    "gpt-5.5": {"ingresso": 5.00, "uscita": 30.00},
}
TOKEN_PER_MILIONE = 1_000_000

# --- Segnali fondamentali (Blocco 8) ---------------------------------------
#
# Le soglie vengono dal vecchio tradash, dove erano gia' state tarate girando:
# non sono numeri inventati qui. Stanno in config e non nel codice perche' un
# giudizio che cambia al cambiare di una soglia deve poter dire QUALE soglia.

# F1 — margini. Quanti punti percentuali di calo, sulla mediana degli ultimi
# trimestri contro quella dei precedenti, fanno scattare il segnale.
F1_CALO_MARGINE_PP_ACCESO = 2.0
F1_CALO_MARGINE_PP_ATTENZIONE = 1.0
F1_TRIMESTRI_MINIMI = 6

# F2 — crescita. Trimestri consecutivi di ricavi in calo, e quanto deve
# rallentare la crescita perche' sia una decelerazione e non rumore.
F2_TRIMESTRI_DI_CALO = 2
F2_DECELERAZIONE_ACCESA = 0.50
F2_DECELERAZIONE_ATTENZIONE = 0.30

# F3 — leva. Un debito netto oltre 3,5 volte l'EBITDA, o una copertura degli
# interessi sotto 3, sono fatti — non opinioni sul tipo di business.
F3_DEBITO_SU_EBITDA_ACCESO = 3.5
F3_COPERTURA_INTERESSI_ACCESA = 3.0

# F4 — liquidita'. Trimestri di autonomia della cassa al ritmo di consumo
# attuale. Sotto quattro e' un anno di vita.
F4_AUTONOMIA_TRIMESTRI_ACCESA = 4.0
F4_AUTONOMIA_TRIMESTRI_ATTENZIONE = 8.0

# F5 — diluizione. Il DATO e' deterministico (crescita annua del numero di
# azioni); e' la SOGLIA a dipendere dall'azienda. La stessa diluizione del 6%
# significa una cosa in una societa' che brucia cassa per finanziare la crescita
# e un'altra in una che produce cassa e emette azioni per scelta.
#
# Le quattro coppie sono quelle del vecchio sistema. A sceglierle e' la
# tolleranza, e l'ordine con cui si decide viene da li': **la generazione di
# cassa prima della fase** — verificato dal vivo su MU, che senza quella
# precedenza si prendeva tre gradini di tolleranza in piu' del dovuto.
F5_SOGLIE = {
    "alta":        {"acceso": 0.15, "attenzione": 0.10},
    "media":       {"acceso": 0.08, "attenzione": 0.05},
    "bassa":       {"acceso": 0.05, "attenzione": 0.03},
    "molto_bassa": {"acceso": 0.03, "attenzione": 0.015},
}

# Capex sui ricavi oltre cui il business e' a intensita' di capitale, e quindi
# un fabbisogno di capitale piu' alto e' fisiologico.
F5_CAPEX_SU_RICAVI_INTENSIVO = 0.10

# Crescita annua dei ricavi oltre cui si e' in una fase di espansione, e sotto
# la quale, in perdita, non si e' in scaling ma in difficolta'.
FASE_CRESCITA_FORTE = 0.25

# --- Scanner ---------------------------------------------------------------

# Quanti titoli al massimo esamina una scansione. L'universo ne ha 11.256, e
# leggerli tutti vorrebbe dire un lavoro da ore: il tetto costringe a filtrare
# prima, che e' anche il modo di ottenere un risultato leggibile.
SCANNER_TITOLI_MAX = 300

# --- Watchlist e tag: i dati TUOI ------------------------------------------
#
# Questi non sono una vista ricostruibile: sono l'unica cosa nel sistema che, se
# si perde, non torna piu'. Per questo la fonte di verita' e' un file JSON
# leggibile e modificabile a mano, e SQLite ne e' soltanto una copia di lavoro
# per poter fare JOIN con l'universo. `manage.py rebuild` cancella la copia, non
# l'originale.
# Versione 2: un titolo puo' stare in PIU' temi. La 1 aveva un tag solo, e
# viene letta e convertita al volo — la conversione e' la migrazione, scritta in
# Python su un dizionario invece che in SQL.
WATCHLIST_FILE_VERSION = 2

# Il profilo di un titolo: quanto del suo valore e' gia' provato. Tre valori,
# copiati dal thematic-equity-monitor perche' la scala e' gia' collaudata.
PROFILO_CORE = "CORE"
PROFILO_EMERGING = "EMERGING"
PROFILO_OPTIONALITY = "OPTIONALITY"
PROFILI = (PROFILO_CORE, PROFILO_EMERGING, PROFILO_OPTIONALITY)

# La maturity: a che punto e' arrivato il business. In ordine, dal piu' acerbo
# al piu' consolidato — l'ordine conta, perche' e' quello in cui si ordina.
MATURITY = ("CONCEPT", "DEVELOPMENT", "DEMONSTRATED", "CONTRACTED", "OPERATIONAL", "SCALED")

# Quanti titoli si possono importare in un colpo solo. Un tetto perche' un
# incollaggio sbagliato non diventi una watchlist da diecimila righe.
WATCHLIST_IMPORT_MAX = 500

PRODUCTION_WATCHLIST_PATH = BASE_DIR / "data" / "watchlist.json"
WATCHLIST_PATH = Path(os.environ.get("TRADASH2_WATCHLIST", PRODUCTION_WATCHLIST_PATH))

# Lo storico di cosa e' successo alla watchlist: append-only, non si corregge
# mai. Una riga JSON per evento, sul modello di `events.jsonl`.
PRODUCTION_WATCHLIST_EVENTS_PATH = BASE_DIR / "data" / "watchlist_events.jsonl"
WATCHLIST_EVENTS_PATH = Path(
    os.environ.get("TRADASH2_WATCHLIST_EVENTS", PRODUCTION_WATCHLIST_EVENTS_PATH)
)

# Quanti eventi restituisce al massimo la cronologia.
WATCHLIST_EVENTS_LIMIT_DEFAULT = 100
WATCHLIST_EVENTS_LIMIT_MAX = 1000

# Profondita' massima della tassonomia: ambito -> sotto-ambito, e basta. Un
# terzo livello e' un albero, e un albero vuole un'interfaccia ad albero.
TAG_MAX_DEPTH = 2

# Oltre quanti giorni un ultimo prezzo si considera vecchio. Non serve a
# nascondere quei titoli: serve a CONTARLI, perche' un prezzo di undici giorni
# fa presentato come quello di oggi e' il difetto che ha generato la regola 3.
UNIVERSE_STALE_PRICE_DAYS = 7
