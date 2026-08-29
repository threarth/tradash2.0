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
}

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
