"""
raffica.py — quanti 8-K ha depositato ogni titolo, mese per mese.
# feat: la tabella derivata su cui poggia il criterio della raffica.

Non si chiama `depositi.py` perche' quel nome e' gia' preso, e da una cosa
diversa: `data/depositi.py` legge le date di deposito **di un titolo** per
sapere quando un bilancio e' diventato pubblico. Qui si contano gli 8-K
**di tutti, per mese**. Due domande diverse sulla stessa tabella di
Defeatbeta, e tenerle in due moduli evita che un modulo risponda a due
padroni.

Un 8-K e' il modulo con cui una societa' dichiara un fatto rilevante:
acquisizioni, contratti, dirigenti che se ne vanno, ristrutturazioni, cause.
Contarli per mese da' il ritmo con cui a una societa' succedono cose.

## Perche' solo gli 8-K

Nell'indice dei depositi i **Form 4** — operazioni degli insider — sono il
45,9% del totale, contro il 16,3% degli 8-K. Contare «i depositi» vorrebbe
dire contare i Form 4 e chiamarli altro. La scelta di cosa contare *e'*
l'indicatore.

## Il point-in-time viene gratis, ed e' l'unico caso

`filing_date` e' la data in cui il documento e' stato depositato. Contare i
depositi per mese di deposito da' quindi esattamente cio' che si sapeva allora,
senza passare da `publication_dates` e senza stimare nessun ritardo. E' l'unico
dato del sistema che non ha questo problema, perche' e' gia' una data di
pubblicazione invece che una data di periodo.

## Cosa ci si e' scoperto

Il criterio che ci poggia sopra e' nato per avvertire di una crescita in arrivo
e fa il contrario: chi deposita a raffica va **peggio**, con costanza e in modo
crescente con l'orizzonte. E' rimasto come filtro di esclusione. I numeri
stanno in `domain/scansione.depositi()` e in `docs/SCANNER.md`.

## Il costo

Una lettura sola, misurata il 18/09/2026: 447.956 righe, 8.464 simboli, **6,4 s
e 250 MB di picco**. Il parquet dei depositi e' piccolo accanto a quello dei
prezzi, che ne vuole 3.076.
"""
import logging
import queue
import threading
from datetime import UTC, datetime

import config
from core import freshness, registry
from core.db import db_read, db_session
from core.schema import GLOBAL_SCOPE
from core.tipi import python_puro
from data import defeatbeta

logger = logging.getLogger(__name__)

JOB_KIND = "ingestion"
JOB_LABEL = "depositi 8-K per mese"

# Leggere, scrivere, marcare la freschezza.
PASSI_COSTRUZIONE = 3

ATTESA_AVVIO_S = 5.0


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _scrivi(frame) -> int:
    """Riscrive la tabella per intero, in una transazione sola (regola 22).

    Si svuota e si riempie come le altre derivate: un aggiornamento a pezzi puo'
    restare a meta' fra due versioni della sorgente senza che nessuno lo veda.
    """
    istante = _adesso()
    righe = [(str(r["symbol"]).upper(), str(r["mese"]),
              int(python_puro(r["depositi"])), istante)
             for r in frame.to_dict("records")
             if python_puro(r.get("depositi")) is not None]

    with db_session() as conn:
        conn.execute("DELETE FROM universe_depositi_mensili")
        conn.executemany(
            "INSERT OR REPLACE INTO universe_depositi_mensili "
            "(symbol, mese, depositi, built_at) VALUES (?, ?, ?, ?)",
            righe,
        )
    return len(righe)


def _costruisci(consegna: queue.Queue | None = None) -> dict:
    """Legge e scrive i depositi per mese. Sta nel registro, si ferma."""
    with registry.job(JOB_KIND, JOB_LABEL, total=PASSI_COSTRUZIONE) as lavoro:
        if consegna is not None:
            consegna.put(lavoro.run_id)

        lettura = defeatbeta.depositi_mensili_universo(run_id=lavoro.run_id)
        if not lettura.available:
            lavoro.advance(detail=f"non disponibile: {lettura.reason}")
            return {"scritte": 0, "reason": lettura.reason, "action": lettura.action}

        lavoro.advance(detail=f"letti {len(lettura.frame)} mesi di depositi")
        scritte = _scrivi(lettura.frame)
        lavoro.advance(detail=f"scritte {scritte} righe")
        freshness.mark_fetched_global(defeatbeta.CATEGORY_DEPOSITI)
        lavoro.advance(detail="freschezza aggiornata")

    logger.info("[DEPOSITI] %d righe", scritte)
    return {"scritte": scritte, "reason": None, "action": None}


def costruisci() -> dict:
    """Deriva i depositi adesso, e aspetta che finisca."""
    return _costruisci()


def costruisci_in_background() -> str:
    """Avvia la derivazione e ritorna il run_id."""
    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_costruisci, args=(consegna,),
                     name="depositi-mensili", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def per_mese(simboli: list[str] | None = None) -> dict[str, dict[str, int]]:
    """`{simbolo: {mese: quanti 8-K}}`. Senza elenco, tutti.

    Si legge in blocco perche' chi rigioca ha bisogno di tutti insieme: una
    query per titolo sarebbe la N+1 che rende lento un lavoro che dev'essere
    aritmetica locale.
    """
    with db_read() as conn:
        if simboli:
            segnaposti = ", ".join("?" for _ in simboli)
            righe = conn.execute(
                f"SELECT symbol, mese, depositi FROM universe_depositi_mensili "
                f"WHERE symbol IN ({segnaposti})",
                [s.strip().upper() for s in simboli],
            ).fetchall()
        else:
            righe = conn.execute(
                "SELECT symbol, mese, depositi FROM universe_depositi_mensili"
            ).fetchall()

    per_simbolo: dict[str, dict[str, int]] = {}
    for riga in righe:
        per_simbolo.setdefault(riga["symbol"], {})[riga["mese"]] = riga["depositi"]
    return per_simbolo


def stato() -> dict:
    """Se la tabella c'e', quanto e' vecchia, e cosa fare se non c'e' (regola 5)."""
    with db_read() as conn:
        riga = conn.execute(
            "SELECT COUNT(*) AS righe, COUNT(DISTINCT symbol) AS titoli, "
            "MAX(built_at) AS costruita_il, MAX(mese) AS ultimo_mese "
            "FROM universe_depositi_mensili"
        ).fetchone()

    if not riga["righe"]:
        return {"available": False, "titoli": 0,
                "reason": "i depositi 8-K non sono mai stati derivati",
                "action": "premi «Deriva i depositi»: e' una lettura sola, "
                          "circa dieci secondi"}

    serve, motivo = freshness.should_fetch_global(defeatbeta.CATEGORY_DEPOSITI)
    return {
        "available": True,
        "righe": riga["righe"],
        "titoli": riga["titoli"],
        "ultimo_mese": riga["ultimo_mese"],
        "costruita_il": riga["costruita_il"],
        "eta_s": freshness.age_seconds(GLOBAL_SCOPE, defeatbeta.CATEGORY_DEPOSITI),
        "da_riderivare": serve,
        "reason": motivo,
        "forme_contate": list(config.DEPOSITI_FORME),
    }
