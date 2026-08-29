"""
freshness.py — il gate interrogato PRIMA di andare in rete.
# feat (Blocco 0): la regola 3, con la granularita' che al vecchio sistema mancava.

Due difetti che questo modulo esiste per impedire:

1. il guard di freschezza appoggiato a un campo VICINO invece che al dato che
   si mostra: `if force or meta.get("market_cap") is None` — il market cap c'e'
   sempre, quindi il prezzo non si rinfrescava mai, e un prezzo di undici
   giorni prima veniva presentato come la quotazione di oggi;
2. un TTL unico per tutto, quando un prezzo invecchia in ore e un profilo
   societario in settimane.

Qui la freschezza si chiede per (simbolo, categoria), e la risposta porta
sempre con se' il motivo — mai un booleano nudo.
"""
import logging
from datetime import datetime, timezone

import config
from core.db import db_session, db_read

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Istante corrente, sempre con fuso orario esplicito."""
    return datetime.now(timezone.utc)


def ttl_for(category: str) -> int:
    """Secondi di validita' di una categoria di dato.

    Una categoria non dichiarata in `config.FRESHNESS_TTL_S` non eredita un TTL
    generoso: prende quello cortissimo, cosi' si nota subito che manca.
    """
    if category not in config.FRESHNESS_TTL_S:
        logger.warning("[FRESCHEZZA] categoria '%s' non dichiarata in config", category)
        return config.FRESHNESS_TTL_UNKNOWN_S
    return config.FRESHNESS_TTL_S[category]


def age_seconds(symbol: str, category: str) -> float | None:
    """Da quanti secondi abbiamo questo dato. `None` se non l'abbiamo mai preso."""
    with db_read() as conn:
        riga = conn.execute(
            "SELECT fetched_at FROM freshness WHERE symbol = ? AND category = ?",
            (symbol.upper(), category),
        ).fetchone()

    if riga is None:
        return None

    try:
        preso = datetime.fromisoformat(riga["fetched_at"])
    except ValueError:
        logger.error("[FRESCHEZZA] data illeggibile per %s/%s: %r",
                     symbol, category, riga["fetched_at"])
        return None

    return (_now() - preso).total_seconds()


def should_fetch(symbol: str, category: str) -> tuple[bool, str]:
    """Va richiesto di nuovo questo dato?

    Ritorna `(serve, motivo)`. Il motivo e' sempre valorizzato, anche quando la
    risposta e' no: chi legge deve poter dire PERCHE' non e' andato in rete.
    """
    eta = age_seconds(symbol, category)
    ttl = ttl_for(category)

    if eta is None:
        return True, f"{category} mai preso per {symbol.upper()}"

    if eta >= ttl:
        return True, f"{category} vecchio di {int(eta)}s, oltre il limite di {ttl}s"

    return False, f"{category} fresco: {int(eta)}s su un limite di {ttl}s"


def mark_fetched(symbol: str, category: str) -> None:
    """Segna che il dato e' stato preso adesso."""
    with db_session() as conn:
        conn.execute(
            """INSERT INTO freshness (symbol, category, fetched_at) VALUES (?, ?, ?)
               ON CONFLICT (symbol, category) DO UPDATE SET fetched_at = excluded.fetched_at""",
            (symbol.upper(), category, _now().isoformat(timespec="seconds")),
        )
