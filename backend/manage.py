"""
manage.py — comandi di manutenzione di tradash2.0.
# feat (Blocco 0, rivisto): l'unico posto da cui si puo' ricostruire il database.

    python manage.py check      elenca le tabelle presenti
    python manage.py rebuild    cancella tutto e ricrea lo schema (chiede conferma)
    python manage.py costi      riapplica il listino alle chiamate gia' fatte
"""
import argparse
import logging
import sys

import config
from core import llm, schema
from core.db import db_read

CONFIRMATION_WORD = "RICOSTRUISCI"
EXIT_OK = 0
EXIT_ABORTED = 1


def comando_check() -> int:
    """Mostra dove sta il database e quali tabelle contiene."""
    schema.ensure_schema()
    print(f"database: {config.DB_PATH}")
    for tabella in schema.tables():
        print(f"  - {tabella}")
    return EXIT_OK


def comando_costi() -> int:
    """Ricalcola il costo delle chiamate gia' registrate col listino di adesso.

    Un modello nuovo si comincia a usare prima di avere il suo listino, e quelle
    chiamate restano a costo zero. I token pero' sono salvati: il costo si
    recupera dopo, senza rifare niente.
    """
    schema.ensure_schema()
    esito = llm.ricalcola_costi()
    print(f"righe in llm_calls: {esito['righe_totali']}")
    print(f"costi ricalcolati:  {esito['righe_aggiornate']}")
    if esito["modelli_ancora_senza_listino"]:
        print("ancora senza listino, e i loro costi restano a zero: "
              + ", ".join(esito["modelli_ancora_senza_listino"]))
        print("  il listino si scrive in config.LLM_PREZZI, dollari per milione di token")
    print(f"speso in tutto:     ${esito['speso']['costo_usd']}")
    return EXIT_OK


def _chiedi_conferma() -> str | None:
    """Legge la parola di conferma. `None` se non c'e' nessuno a scriverla.

    Senza terminale — lanciato da uno script, da un hook, o da una shell che
    non collega lo standard input — `input()` solleva EOFError. Prima quello
    diventava uno stack trace in faccia all'utente per un comando che si era
    semplicemente rifiutato di partire, che e' l'opposto di quello che la
    regola 16 chiede.
    """
    try:
        return input(f"Scrivi {CONFIRMATION_WORD} per procedere: ").strip()
    except EOFError:
        return None


# Cio' che il database contiene e che NON si ricostruisce da nessuna fonte.
# Tutto il resto — universo, prezzi, freschezza — si rifa' leggendo Defeatbeta;
# questi no: i referti sono stati PAGATI, e il registro delle chiamate e' il solo
# posto dove c'e' scritto quanto.
TABELLE_NON_RICOSTRUIBILI = {
    "referti": "referti delle analisi, che sono costati denaro",
    "llm_calls": "registro delle chiamate ai modelli, con i costi",
    "calls": "registro di tutte le chiamate, con la provenienza",
    "jobs": "storico dei lavori",
}


def _cosa_si_perde() -> list[str]:
    """Righe presenti nelle tabelle che nessuna fonte sa rimettere."""
    perdite = []
    presenti = set(schema.tables())
    with db_read() as conn:
        for tabella, cosa in TABELLE_NON_RICOSTRUIBILI.items():
            if tabella not in presenti:
                continue
            quante = conn.execute(f"SELECT COUNT(*) AS n FROM {tabella}").fetchone()["n"]
            if quante:
                perdite.append(f"{quante} righe in «{tabella}» — {cosa}")
    return perdite


def comando_rebuild() -> int:
    """Ricostruisce il database, ma solo dopo che l'utente ha battuto la parola.

    Prima di chiedere, dice **cosa non tornera' piu'**. Il progetto tratta questo
    database come una vista ricostruibile, ed e' vero per quasi tutto — ma i
    referti delle analisi sono stati pagati e nessuna fonte sa riprodurli. Un
    comando che dice «cancella tutto» senza dire che li' dentro ci sono cinque
    dollari di analisi e' un comando che si esegue una volta di troppo.
    """
    print(f"Questo CANCELLA tutti i dati in: {config.DB_PATH}")
    print(f"Tabelle che verranno cancellate: {', '.join(schema.tables()) or 'nessuna'}")

    perdite = _cosa_si_perde()
    if perdite:
        print()
        print("ATTENZIONE — questo non si ricostruisce da nessuna fonte:")
        for perdita in perdite:
            print(f"  - {perdita}")
        print()
        print(f"Se vuoi tenerne una copia: cp {config.DB_PATH} {config.DB_PATH}.prima-del-rebuild")
        print()

    risposta = _chiedi_conferma()

    if risposta is None:
        print("Annullato: nessuno ha confermato — qui non c'e' un terminale da cui scrivere.")
        print(f"Da un terminale vero, oppure:  echo {CONFIRMATION_WORD} | "
              f"python manage.py rebuild")
        return EXIT_ABORTED

    if risposta != CONFIRMATION_WORD:
        print("Annullato: nessuna modifica.")
        return EXIT_ABORTED

    cancellate = schema.rebuild(confirmed=True)
    print(f"Ricostruito. Tabelle cancellate e ricreate: {len(cancellate)}")
    return EXIT_OK


def main() -> int:
    """Punto di ingresso della riga di comando."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
    parser = argparse.ArgumentParser(description="Manutenzione del database di tradash2.0")
    parser.add_argument("comando", choices=["check", "rebuild", "costi"])
    argomenti = parser.parse_args()

    if argomenti.comando == "check":
        return comando_check()
    if argomenti.comando == "costi":
        return comando_costi()
    return comando_rebuild()


if __name__ == "__main__":
    sys.exit(main())
