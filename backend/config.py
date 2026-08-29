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

# Percorso del database. Sovrascrivibile per i test, che non devono mai
# toccare il database reale.
DB_PATH = Path(os.environ.get("TRADASH2_DB", BASE_DIR / "tradash2.db"))

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
