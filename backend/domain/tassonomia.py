"""
tassonomia.py — il vocabolario chiuso con cui si classifica un'azienda.
# feat (Blocco 8): le dodici dimensioni del report qualitativo, e la loro verifica.

Nel vecchio sistema queste etichette stavano nell'enum dello schema di un tool,
e a farle rispettare era la validazione del tool. Qui non ci sono tool: il
modello risponde con un JSON, e un JSON puo' contenere qualunque parola.

Per questo il vocabolario sta qui, in codice, e le etichette si controllano
dopo. Un'etichetta inventata non viene corretta d'ufficio — viene **scartata e
dichiarata**: correggerla vorrebbe dire indovinare cosa intendeva il modello, e
un'etichetta indovinata da noi finirebbe nella watchlist come se l'avesse
scelta lui.

Le dimensioni sono divise fra due fasi perche' rispondono a domande diverse:
otto descrivono come funziona l'azienda (fase 1, che legge i filing e i
numeri), quattro come si difende e da chi (fase 2, che guarda fuori).
"""

# Come si comportano ricavi, margini e cassa nel tempo.
MODELLO_ECONOMICO = ("ciclico", "difensivo", "crescita_secolare", "maturo_stabile",
                     "turnaround", "declino_strutturale")

# Come l'azienda monetizza.
MODELLO_RICAVI = ("ricorrente_abbonamento", "transazionale", "vendita_prodotti",
                  "commesse", "licenze_royalty", "pubblicitario", "utilizzo",
                  "spread", "commodity_linked", "ibrido")

# Intensita' di capitale e circolante. Su "leva_finanziaria_strutturale" si
# sbaglia spesso: significa che il BUSINESS dipende dalla leva per funzionare
# (banca, REIT, utility, infrastruttura), non che l'azienda ha emesso debito.
MODELLO_CAPITALE = ("bassa_intensita_capitale", "alta_intensita_capitale",
                    "capitale_circolante_alto", "capitale_circolante_negativo",
                    "leva_finanziaria_strutturale")

STRUTTURA_CLIENTELA = ("b2b", "b2c", "b2g", "b2b2c", "ibrida")

# Maturita' STRUTTURALE, relativamente stabile nel tempo.
FASE_CICLO_VITA = ("pre_ricavi", "crescita_iniziale", "scaling",
                   "crescita_consolidata", "maturita", "declino", "ristrutturazione")

# Cosa sta accadendo ORA. Asse indipendente dal precedente: una "maturita" puo'
# convivere con un "recupero", e confonderli e' l'errore tipico.
STATO_CORRENTE = ("espansione", "accelerazione", "rallentamento", "contrazione",
                  "fondo_ciclico", "stabilizzazione", "recupero", "normalizzazione",
                  "deterioramento_strutturale")

FASE_TURNAROUND = ("non_applicabile", "deterioramento", "stabilizzazione",
                   "prime_evidenze", "recupero_margini", "recupero_cash_flow",
                   "normalizzazione", "ritorno_crescita")

# Il MECCANISMO concreto che protegge margini e quote, non un giudizio sul moat.
MODELLO_COMPETITIVO = ("vantaggio_costo", "scala", "costi_sostituzione",
                       "effetti_rete", "marchio_intangibili", "tecnologia_proprietaria",
                       "vantaggio_distributivo", "controllo_piattaforma_ecosistema",
                       "fossato_regolatorio", "nessun_vantaggio_durevole")

MODELLO_REGOLATORIO = ("poco_regolato", "regolazione_indiretta", "fortemente_regolato",
                       "tariffa_regolata", "dipendenza_settore_pubblico",
                       "vincoli_geopolitici")

STRUTTURA_FORNITURA = ("diversificata", "concentrata", "single_source",
                       "verticalmente_integrata", "esternalizzata", "ibrida")

CONFIDENZA = ("alta", "media", "bassa")

# Le dimensioni con vocabolario chiuso, per fase. Due non ci sono e non e' una
# dimenticanza: `dipendenza_prodotti_segmenti` ed `esposizione_geografica`
# elencano prodotti e paesi, e non esiste un elenco chiuso di quelli.
DIMENSIONI_FASE1 = {
    "modello_economico": MODELLO_ECONOMICO,
    "modello_ricavi": MODELLO_RICAVI,
    "modello_capitale": MODELLO_CAPITALE,
    "struttura_clientela": STRUTTURA_CLIENTELA,
    "fase_ciclo_vita": FASE_CICLO_VITA,
    "stato_corrente": STATO_CORRENTE,
    "fase_turnaround": FASE_TURNAROUND,
}

DIMENSIONI_FASE2 = {
    "modello_competitivo": MODELLO_COMPETITIVO,
    "modello_regolatorio": MODELLO_REGOLATORIO,
    "struttura_fornitura": STRUTTURA_FORNITURA,
}

DIMENSIONI = {**DIMENSIONI_FASE1, **DIMENSIONI_FASE2}

# Le dimensioni a testo libero: si conservano come sono, senza controllo.
DIMENSIONI_APERTE = ("dipendenza_prodotti_segmenti", "esposizione_geografica")


def _etichette(valore) -> list[str]:
    """Le etichette dichiarate, comunque siano state scritte.

    Il modello puo' rispondere con una stringa, con una lista, o con un oggetto
    che ha dentro le etichette: si accettano tutte e tre le forme perche' il
    contenuto e' lo stesso, e rifiutare per la forma perderebbe una
    classificazione buona.
    """
    if isinstance(valore, str):
        return [valore]
    if isinstance(valore, dict):
        return _etichette(valore.get("etichette") or valore.get("etichetta") or [])
    if isinstance(valore, list):
        return [v for v in valore if isinstance(v, str)]
    return []


def valida(classificazione: dict) -> tuple[dict, list[str]]:
    """Separa le etichette del vocabolario da quelle inventate.

    Ritorna `(classificazione ripulita, elenco degli scarti)`. Gli scarti sono
    scritti in chiaro — «modello_economico: "iper-crescita" non e' nel
    vocabolario» — perche' chi legge il referto deve poter vedere che il modello
    ha classificato fuori elenco, non trovarsi una dimensione vuota.
    """
    pulita, scartate = {}, []

    for nome, vocabolario in DIMENSIONI.items():
        if nome not in classificazione:
            continue
        valore = classificazione[nome]
        buone = [e for e in _etichette(valore) if e in vocabolario]
        fuori = [e for e in _etichette(valore) if e not in vocabolario]
        scartate.extend(f"{nome}: {e!r} non e' nel vocabolario" for e in fuori)
        pulita[nome] = {**(valore if isinstance(valore, dict) else {}),
                        "etichette": buone}

    for nome in DIMENSIONI_APERTE:
        if nome in classificazione:
            pulita[nome] = classificazione[nome]

    mancanti = [n for n in DIMENSIONI if n not in classificazione]
    scartate.extend(f"{n}: dimensione non classificata" for n in mancanti)

    return pulita, scartate


def vocabolario_leggibile(dimensioni: dict) -> str:
    """Il vocabolario come lo legge il modello nel prompt, senza duplicarlo a mano.

    Scritto una volta sola: un elenco copiato nel prompt e divergente dal codice
    farebbe scartare come inventate etichette che avevamo chiesto noi.
    """
    return "\n".join(f"- {nome}: {' | '.join(vocabolario)}"
                     for nome, vocabolario in dimensioni.items())
