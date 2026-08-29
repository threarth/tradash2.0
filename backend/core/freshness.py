"""
freshness.py — il gate interrogato PRIMA di andare in rete.
# feat (Blocco 0, rivisto): la regola 3, con la granularita' che al vecchio sistema mancava.

Tre difetti che questo modulo esiste per impedire:

1. il guard di freschezza appoggiato a un campo VICINO invece che al dato che
   si mostra: `if force or meta.get("market_cap") is None` — il market cap c'e'
   sempre, quindi il prezzo non si rinfrescava mai, e un prezzo di undici
   giorni prima veniva presentato come la quotazione di oggi;
2. un TTL unico per tutto, quando un prezzo invecchia in ore e un profilo
   societario in settimane;
3. una freschezza che sa parlare solo di titoli: la curva dei Treasury e la
   lista dell'universo non appartengono a nessun ticker, e vanno comunque
   chieste prima di andare in rete. Per questo l'ambito si chiama `scope` e non
   `symbol`.

La risposta porta sempre con se' il motivo — mai un booleano nudo.
"""
import logging
from datetime import datetime, timezone

import config
from core.db import db_session, db_read
from core.schema import GLOBAL_SCOPE

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Istante corrente, sempre con fuso orario esplicito."""
    return datetime.now(timezone.utc)


def normalize_scope(scope: str) -> str:
    """Forma canonica di un ambito.

    I ticker si confrontano in maiuscolo; le chiavi globali cominciano per '@'
    e restano come sono, perche' non sono nomi di titoli.
    """
    pulito = scope.strip()
    if pulito.startswith("@"):
        return pulito
    return pulito.upper()


def ttl_for(category: str) -> int:
    """Secondi di validita' di una categoria di dato.

    Una categoria non dichiarata in `config.FRESHNESS_TTL_S` non eredita un TTL
    generoso: prende quello cortissimo, cosi' si nota subito che manca.
    """
    if category not in config.FRESHNESS_TTL_S:
        logger.warning("[FRESCHEZZA] categoria '%s' non dichiarata in config", category)
        return config.FRESHNESS_TTL_UNKNOWN_S
    return config.FRESHNESS_TTL_S[category]


def age_seconds(scope: str, category: str) -> float | None:
    """Da quanti secondi abbiamo questo dato. `None` se non l'abbiamo mai preso."""
    with db_read() as conn:
        riga = conn.execute(
            "SELECT fetched_at FROM freshness WHERE scope = ? AND category = ?",
            (normalize_scope(scope), category),
        ).fetchone()

    if riga is None:
        return None

    try:
        preso = datetime.fromisoformat(riga["fetched_at"])
    except ValueError:
        logger.error("[FRESCHEZZA] data illeggibile per %s/%s: %r",
                     scope, category, riga["fetched_at"])
        return None

    return (_now() - preso).total_seconds()


def should_fetch(scope: str, category: str) -> tuple[bool, str]:
    """Va richiesto di nuovo questo dato?

    Ritorna `(serve, motivo)`. Il motivo e' sempre valorizzato, anche quando la
    risposta e' no: chi legge deve poter dire PERCHE' non e' andato in rete.
    """
    eta = age_seconds(scope, category)
    ttl = ttl_for(category)
    ambito = normalize_scope(scope)

    if eta is None:
        return True, f"{category} mai preso per {ambito}"

    if eta >= ttl:
        return True, f"{category} vecchio di {int(eta)}s, oltre il limite di {ttl}s"

    return False, f"{category} fresco: {int(eta)}s su un limite di {ttl}s"


def should_fetch_global(category: str) -> tuple[bool, str]:
    """Come `should_fetch`, per i dati che non appartengono a nessun titolo."""
    return should_fetch(GLOBAL_SCOPE, category)


def mark_fetched(scope: str, category: str) -> None:
    """Segna che il dato e' stato preso adesso."""
    with db_session() as conn:
        conn.execute(
            """INSERT INTO freshness (scope, category, fetched_at) VALUES (?, ?, ?)
               ON CONFLICT (scope, category) DO UPDATE SET fetched_at = excluded.fetched_at""",
            (normalize_scope(scope), category, _now().isoformat(timespec="seconds")),
        )


def mark_fetched_global(category: str) -> None:
    """Come `mark_fetched`, per i dati globali."""
    mark_fetched(GLOBAL_SCOPE, category)
