"""
registry.py — registro dei lavori: gestibili, fermabili, loggati.
# feat (Blocco 0): la meta' "controllo" della regola 1.

Il difetto che questo modulo esiste per impedire: il 28/08 girava un download
di ~500 ticker che nessun endpoint vedeva — nessun run_id, nessun cancel_event,
nessuno Stop. L'unico modo di fermarlo era uccidere il processo.

Qui non ci sono lavori privilegiati: chi non passa da `job()` non compare in
`active()` e non si puo' fermare, quindi non deve esistere.

## La scia

Un lavoro non dice solo a che punto e': dice **cosa ha fatto finora**. Una barra
che avanza e una scritta che si sostituisce raccontano un istante; quando
un'analisi impiega tre minuti e sta in silenzio per quaranta secondi alla volta,
la domanda vera e' «e' ferma o sta pensando», e a quella risponde solo l'ora
dell'ultima riga.

La scia vive in memoria e muore col lavoro: e' una cosa che si guarda mentre
succede. La storia sta altrove e non si perde — l'esito in `jobs`, ogni chiamata
al modello con i suoi token e il suo costo in `llm_calls`.
"""
import logging
import threading
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import UTC, datetime

import config
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

    def __init__(self, kind: str, label: str, total: int | None, ambito: str | None = None):
        self.run_id = uuid.uuid4().hex
        self.kind = kind
        self.label = label
        self.ambito = ambito
        self.total = total
        self.done = 0
        self.detail: str | None = None
        self.status = STATUS_RUNNING
        self.cancel_event = threading.Event()

        # La scia tiene le ultime righe e conta tutte quelle passate: cosi' chi
        # la mostra puo' dire che ne sta mostrando una parte.
        self.eventi: deque = deque(maxlen=config.REGISTRY_EVENTI_MAX)
        self.eventi_totali = 0

    def stop_requested(self) -> bool:
        """True se qualcuno ha premuto Stop."""
        return self.cancel_event.is_set()

    def check_stop(self) -> None:
        """Solleva `JobStopped` se e' stato chiesto lo stop. Da chiamare a ogni passo."""
        if self.stop_requested():
            raise JobStopped(f"lavoro {self.run_id} fermato su richiesta")

    def nota(self, testo: str) -> None:
        """Aggiunge una riga alla scia SENZA far avanzare il contatore.

        Serve ai passi dentro a un passo — una chiamata al modello parte e
        torna, e in mezzo ci sono i quaranta secondi in cui sembra bloccata.

        **Non controlla lo stop**, a differenza di `advance()`: viene chiamata
        anche da dentro `llm.chiedi`, e far uscire un'eccezione da una riga di
        racconto vorrebbe dire far fallire il lavoro per colpa del racconto.
        """
        self.eventi.append({"quando": _now_iso(), "testo": testo})
        self.eventi_totali += 1

    def advance(self, detail: str | None = None) -> None:
        """Segna un passo fatto, lo scrive nella scia, e controlla se fermarsi."""
        self.done += 1
        if detail is not None:
            self.detail = detail
            self.nota(detail)
        self.check_stop()

    def as_dict(self) -> dict:
        """Rappresentazione per l'API e per il log."""
        return {
            "run_id": self.run_id, "kind": self.kind, "label": self.label,
            "ambito": self.ambito,
            "status": self.status, "total": self.total, "done": self.done,
            "detail": self.detail, "stop_requested": self.stop_requested(),
            "eventi": list(self.eventi),
            "eventi_totali": self.eventi_totali,
            "eventi_max": self.eventi.maxlen,
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
def job(kind: str, label: str, total: int | None = None, ambito: str | None = None):
    """Apre un lavoro tracciato. Unico modo legittimo di fare lavoro lungo.

    `ambito` e' il titolo su cui si sta lavorando, quando ce n'e' uno: serve
    alla pagina di quel titolo per riconoscere il PROPRIO lavoro fra quelli in
    corso, senza doverlo indovinare leggendo l'etichetta. Resta in memoria — la
    tabella `jobs` non cambia forma, e nessuno deve ricostruire il database.

    Uso:
        with registry.job("ingestion", "prezzi S&P", total=500) as lavoro:
            for simbolo in simboli:
                lavoro.advance(simbolo)
    """
    lavoro = Job(kind, label, total, ambito)
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


def nota(run_id: str | None, testo: str) -> None:
    """Aggiunge una riga alla scia di un lavoro vivo, se quel lavoro esiste.

    Non protesta quando non lo trova, ed e' voluto: una chiamata al modello puo'
    avvenire fuori da qualsiasi lavoro, e una riga di racconto non deve mai
    diventare il motivo per cui qualcosa fallisce.
    """
    if not run_id:
        return

    with _lock:
        lavoro = _lavori.get(run_id)
    if lavoro is not None:
        lavoro.nota(testo)


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
