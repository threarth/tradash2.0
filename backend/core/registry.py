"""
registry.py — registro dei lavori: gestibili, fermabili, loggati.
# feat (Blocco 0): la meta' "controllo" della regola 1.

Il difetto che questo modulo esiste per impedire: il 28/08 girava un download
di ~500 ticker che nessun endpoint vedeva — nessun run_id, nessun cancel_event,
nessuno Stop. L'unico modo di fermarlo era uccidere il processo.

Qui non ci sono lavori privilegiati: chi non passa da `job()` non compare in
`active()` e non si puo' fermare, quindi non deve esistere.
"""
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

from core.db import db_session

logger = logging.getLogger(__name__)

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_STOPPED = "stopped"
STATUS_FAILED = "failed"

# Lavori vivi in questo processo. Il DB conserva la storia, questo dizionario
# conserva cio' che si puo' ancora fermare.
_lavori: dict[str, "Job"] = {}
_lock = threading.Lock()


class JobStopped(Exception):
    """Sollevata quando un lavoro si accorge che gli e' stato chiesto di fermarsi."""


class Job:
    """Un lavoro in corso, con il suo interruttore."""

    def __init__(self, kind: str, label: str, total: int | None):
        self.run_id = uuid.uuid4().hex
        self.kind = kind
        self.label = label
        self.total = total
        self.done = 0
        self.detail: str | None = None
        self.status = STATUS_RUNNING
        self.cancel_event = threading.Event()

    def stop_requested(self) -> bool:
        """True se qualcuno ha premuto Stop."""
        return self.cancel_event.is_set()

    def check_stop(self) -> None:
        """Solleva `JobStopped` se e' stato chiesto lo stop. Da chiamare a ogni passo."""
        if self.stop_requested():
            raise JobStopped(f"lavoro {self.run_id} fermato su richiesta")

    def advance(self, detail: str | None = None) -> None:
        """Segna un passo fatto e controlla se bisogna fermarsi."""
        self.done += 1
        if detail is not None:
            self.detail = detail
        self.check_stop()

    def as_dict(self) -> dict:
        """Rappresentazione per l'API e per il log."""
        return {
            "run_id": self.run_id, "kind": self.kind, "label": self.label,
            "status": self.status, "total": self.total, "done": self.done,
            "detail": self.detail, "stop_requested": self.stop_requested(),
        }


def _now_iso() -> str:
    """Istante corrente in ISO 8601 UTC."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _insert(lavoro: Job) -> None:
    """Registra l'avvio del lavoro nel database."""
    with db_session() as conn:
        conn.execute(
            """INSERT INTO jobs (run_id, kind, label, status, total, done, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (lavoro.run_id, lavoro.kind, lavoro.label, lavoro.status,
             lavoro.total, lavoro.done, _now_iso()),
        )


def _close(lavoro: Job) -> None:
    """Registra l'esito finale del lavoro."""
    with db_session() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, done = ?, detail = ?, ended_at = ? WHERE run_id = ?",
            (lavoro.status, lavoro.done, lavoro.detail, _now_iso(), lavoro.run_id),
        )


@contextmanager
def job(kind: str, label: str, total: int | None = None):
    """Apre un lavoro tracciato. Unico modo legittimo di fare lavoro lungo.

    Uso:
        with registry.job("ingestion", "prezzi S&P", total=500) as lavoro:
            for simbolo in simboli:
                lavoro.advance(simbolo)
    """
    lavoro = Job(kind, label, total)
    with _lock:
        _lavori[lavoro.run_id] = lavoro
    _insert(lavoro)
    logger.info("[LAVORO] avviato %s (%s) run_id=%s", label, kind, lavoro.run_id)

    try:
        yield lavoro
        lavoro.status = STATUS_DONE
    except JobStopped:
        lavoro.status = STATUS_STOPPED
        logger.info("[LAVORO] fermato %s run_id=%s dopo %s passi",
                    label, lavoro.run_id, lavoro.done)
    except Exception:
        lavoro.status = STATUS_FAILED
        logger.exception("[LAVORO] fallito %s run_id=%s", label, lavoro.run_id)
        raise
    finally:
        with _lock:
            _lavori.pop(lavoro.run_id, None)
        _close(lavoro)


def active() -> list[dict]:
    """I lavori vivi adesso, quelli che si possono ancora fermare."""
    with _lock:
        return [lavoro.as_dict() for lavoro in _lavori.values()]


def request_stop(run_id: str) -> tuple[bool, str | None]:
    """Chiede a un lavoro di fermarsi.

    Ritorna `(True, None)` se la richiesta e' stata consegnata, `(False, motivo)`
    altrimenti — mai un `None` silenzioso.
    """
    with _lock:
        lavoro = _lavori.get(run_id)

    if lavoro is None:
        return False, f"nessun lavoro attivo con run_id {run_id}"

    lavoro.cancel_event.set()
    logger.info("[LAVORO] stop richiesto per run_id=%s (%s)", run_id, lavoro.label)
    return True, None
