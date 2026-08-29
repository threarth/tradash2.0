"""
manage.py — comandi di manutenzione di tradash2.0.
# feat (Blocco 0, rivisto): l'unico posto da cui si puo' ricostruire il database.

    python manage.py check      elenca le tabelle presenti
    python manage.py rebuild    cancella tutto e ricrea lo schema (chiede conferma)
"""
import argparse
import logging
import sys

import config
from core import schema

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


def comando_rebuild() -> int:
    """Ricostruisce il database, ma solo dopo che l'utente ha battuto la parola."""
    print(f"Questo CANCELLA tutti i dati in: {config.DB_PATH}")
    print(f"Tabelle che verranno cancellate: {', '.join(schema.tables()) or 'nessuna'}")
    risposta = input(f"Scrivi {CONFIRMATION_WORD} per procedere: ").strip()

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
    parser.add_argument("comando", choices=["check", "rebuild"])
    argomenti = parser.parse_args()

    if argomenti.comando == "check":
        return comando_check()
    return comando_rebuild()


if __name__ == "__main__":
    sys.exit(main())
