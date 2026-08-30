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


def comando_rebuild() -> int:
    """Ricostruisce il database, ma solo dopo che l'utente ha battuto la parola."""
    print(f"Questo CANCELLA tutti i dati in: {config.DB_PATH}")
    print(f"Tabelle che verranno cancellate: {', '.join(schema.tables()) or 'nessuna'}")
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
