"""
manage.py — comandi di manutenzione di tradash2.0.
# feat (Blocco 0, rivisto): l'unico posto da cui si puo' ricostruire il database.

    python manage.py check      elenca le tabelle presenti
    python manage.py rebuild    cancella tutto e ricrea lo schema (chiede conferma)
    python manage.py costi      riapplica il listino alle chiamate gia' fatte
    python manage.py referti    rimette in SQLite i referti che stanno nel file
    python manage.py rigioco    rigioca il punteggio degli spin-off all'indietro
    python manage.py criterio '{"ricavi_qoq_minimo": 0.15}'
                                rigioca un criterio dello scanner contro il non-filtrare
"""
import argparse
import json
import logging
import sys

import config
from core import llm, schema
from core.db import db_read
from data import analisi, rigioco, spinoff_rigioco
from domain import scansione

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


def comando_referti() -> int:
    """Rimette in SQLite i referti che stanno nel file, dopo un rebuild."""
    schema.ensure_schema()
    esito = analisi.ripristina_dal_file()
    if esito["reason"]:
        print(esito["reason"])
        return EXIT_OK
    print(f"referti nel file:   {esito['letti']}")
    print(f"rimessi in SQLite:  {esito['rimessi']}")
    print(f"gia' presenti:      {esito['gia_presenti']}")
    if esito["senza_lavoro"]:
        print(f"senza il lavoro:    {esito['senza_lavoro']} — il lavoro d'origine "
              f"non esiste piu'; il referto si'")
    if esito["illeggibili"]:
        print(f"righe illeggibili:  {esito['illeggibili']} — saltate, il file resta com'e'")
    return EXIT_OK


def comando_rigioco() -> int:
    """Rigioca il punteggio degli spin-off mese per mese, e dice se anticipa.

    E' la verifica dei pesi, non una funzione dell'applicazione: i sei pesi
    vengono da un caso solo — SanDisk — e finche' nessuno li rigioca su tutto
    l'elenco restano un aneddoto forte. Qui si guarda una cosa sola: le fasce di
    punteggio alte hanno avuto rendimenti migliori delle basse?
    """
    schema.ensure_schema()
    esito = spinoff_rigioco.rigioca()

    print(f"rigioco su {esito['titoli']} titoli · {len(esito['punti'])} punti "
          f"· rendimento misurato sui {esito['orizzonte_mesi']} mesi successivi")
    print(f"pesi in prova: {esito['pesi']}\n")

    print(f"{'fascia':>12}{'punti':>8}{'titoli':>8}{'mediana':>10}{'media':>9}"
          f"{'in guadagno':>13}")
    for fascia in esito["fasce"]:
        mediana = f"{fascia['mediana']:+.1%}" if fascia["mediana"] is not None else "—"
        media = f"{fascia['media']:+.1%}" if fascia["media"] is not None else "—"
        quota = (f"{fascia['quanti_in_guadagno']}/{fascia['punti']}"
                 if fascia["punti"] else "—")
        print(f"{fascia['da']:>6}-{fascia['a'] - 1:<5}{fascia['punti']:>8}"
              f"{fascia['titoli']:>8}{mediana:>10}{media:>9}{quota:>13}")

    if esito["saltati"]:
        print(f"\nsaltati: {len(esito['saltati'])}")
        for saltato in esito["saltati"]:
            print(f"  {saltato['symbol']:6} {saltato['motivo']}")

    # Il numero onesto e' quello dei TITOLI, non quello dei punti: i mesi vicini
    # dello stesso titolo dicono la stessa cosa.
    print("\nI titoli distinti per fascia sono il numero da guardare: una fascia")
    print("con cento punti e due titoli e' due casi, non cento.")
    return EXIT_OK


def comando_criterio(criteri_json: str | None) -> int:
    """Rigioca un criterio dello scanner su tutti i mesi, contro il non-filtrare.

    E' la domanda «questo criterio ha mai funzionato?» fatta PRIMA di accenderlo,
    che e' l'ordine in cui non e' stata fatta per i pesi del rilevatore spin-off.

    Il paragone col resto dell'universo e' il pezzo che conta: un criterio che
    trova titoli col +12% sembra bravo finche' non si scopre che in quei mesi
    tutto il mercato ha fatto +15%.
    """
    schema.ensure_schema()
    if not criteri_json:
        print("serve un oggetto JSON coi criteri, per esempio:")
        print("""  manage.py criterio '{"ricavi_qoq_minimo": 0.15}'""")
        print(f"criteri disponibili: {', '.join(sorted(scansione.CRITERI))}")
        return EXIT_ABORTED

    try:
        criteri = json.loads(criteri_json)
        esito = rigioco.rigioca(criteri)
    except (json.JSONDecodeError, ValueError) as problema:
        print(f"non si puo' rigiocare: {problema}")
        return EXIT_ABORTED

    conto = esito["riepilogo"]
    print(f"criterio: {esito['criteri']}")
    print(f"rendimento misurato sui {esito['orizzonte_mesi']} mesi successivi\n")

    if conto["reason"]:
        print(conto["reason"])
        return EXIT_OK

    print(f"{'mese':9}{'trovati':>9}{'loro':>10}{'tutti':>10}{'differenza':>13}")
    for mese in esito["mesi"]:
        if mese["mediana_trovati"] is None or mese["mediana_universo"] is None:
            continue
        differenza = mese["mediana_trovati"] - mese["mediana_universo"]
        print(f"{mese['mese']:9}{mese['trovati']:>9}"
              f"{mese['mediana_trovati']:>9.1%}{mese['mediana_universo']:>10.1%}"
              f"{differenza:>13.1%}")

    print(f"\nmesi giudicabili {conto['mesi_utili']} · vinti {conto['vinti']} "
          f"({conto['quota_vinti']:.0%}) · vantaggio mediano "
          f"{conto['vantaggio_mediano']:+.1%} · trovati per mese "
          f"{conto['trovati_per_mese']}")
    print("\nI mesi vinti contano piu' della media delle differenze: una media")
    print("se la porta via un mese solo, e la domanda e' «funziona spesso?».")
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
    print(f"referti corretti:   {esito['referti_aggiornati']}")
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
    "referti": "referti delle analisi — si rimettono con `manage.py referti`",
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
    parser.add_argument("comando",
                        choices=["check", "rebuild", "costi", "referti", "rigioco",
                                 "criterio"])
    parser.add_argument("criteri", nargs="?",
                        help="per «criterio»: i criteri come oggetto JSON")
    argomenti = parser.parse_args()

    if argomenti.comando == "check":
        return comando_check()
    if argomenti.comando == "costi":
        return comando_costi()
    if argomenti.comando == "referti":
        return comando_referti()
    if argomenti.comando == "rigioco":
        return comando_rigioco()
    if argomenti.comando == "criterio":
        return comando_criterio(argomenti.criteri)
    return comando_rebuild()


if __name__ == "__main__":
    sys.exit(main())
