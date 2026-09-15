"""
salute.py — l'app e' viva? Una domanda sola, e la piu' economica possibile.
# feat: l'endpoint che nginx e systemd possono chiedere senza credenziali.

## Perche' esiste

Senza, l'unico modo di sapere se il servizio e' su e' aprirlo dal browser — cioe'
accorgersene quando serve, invece che prima. nginx e systemd vogliono una rotta
che risponda 200 quando va tutto bene e qualcos'altro quando no, e la vogliono
**senza fare l'accesso**, perche' un supervisore non ha una password.

## Perche' dice cosi' poco

E' l'unica rotta pubblica che tocca il database, quindi e' anche l'unica che uno
sconosciuto puo' far lavorare. Fa un `SELECT 1` e niente altro: nessun conteggio,
nessun percorso, nessun nome di file. Chi la interroga mille volte al secondo non
ottiene niente di piu' che mille `SELECT 1`.

E non dice **cosa** c'e' dentro: sapere che il servizio e' vivo non e' un
segreto, sapere quanti titoli ha in pancia o dove tiene i suoi file lo e'.
"""
import logging

from flask import Blueprint

from api import ok
from api.ops import AVVIATO_IL
from core.db import db_read

logger = logging.getLogger(__name__)

bp = Blueprint("salute", __name__, url_prefix="/api/salute")

# `AVVIATO_IL` si prende da `api.ops` invece di dichiararlo qui: e' l'istante in
# cui il processo e' partito, e due moduli che se lo calcolano per conto proprio
# darebbero due risposte diverse alla stessa domanda. Serve a distinguere «e'
# vivo» da «e' appena stato riavviato»: un supervisore che vede l'istante
# cambiare sa che qualcosa lo ha fatto ripartire.


@bp.get("")
def salute():
    """Vivo e col database raggiungibile? Nient'altro, di proposito."""
    with db_read() as conn:
        conn.execute("SELECT 1").fetchone()
    return ok({"stato": "vivo", "avviato_il": AVVIATO_IL})
