"""
sezioni_filing.py — dove comincia e dove finisce una sezione di un filing.
# feat (Blocco 8): l'analisi qualitativa legge SEZIONI, non il documento intero.

Un 10-K sono centinaia di migliaia di caratteri, in gran parte tabelle di
bilancio e note contabili che l'analisi qualitativa non legge: i numeri li ha
gia' calcolati altrove. Le parti che le servono sono quattro o cinque, e hanno
un nome standard perche' la SEC prescrive l'ordine degli "Item".

## Il problema vero: ogni Item compare piu' volte

Nello stesso documento "Item 1A" compare almeno tre volte — nell'indice, come
titolo della sezione, e in ogni rimando ("see Item 1A. Risk Factors"). Cercare
la prima occorrenza pesca l'indice, e l'indice e' lungo due righe.

Qui la scelta e' fatta sulla LUNGHEZZA: fra tutte le occorrenze, quella vera e'
quella che apre il testo piu' lungo prima dell'Item successivo. Un rimando ha
davanti a se' poche righe, una voce di indice ancora meno; solo il titolo vero
ha davanti a se' la sezione. Dove il titolo atteso ("Risk Factors") compare
accanto al numero, si preferiscono quelle occorrenze — ma solo se ce n'e'
almeno una, perche' un documento che scrive il titolo in modo diverso non deve
per questo perdere la sezione.

## Cosa succede quando una sezione non c'e'

Ritorna None con il suo motivo, e chi chiama lo dichiara. Non si ripiega sul
documento intero: sarebbero decine di migliaia di token di bilanci dati in
pasto a un'analisi che cerca la descrizione del business.
"""
import re

# Le sezioni che l'analisi qualitativa legge, col numero di Item che le ospita
# e il titolo con cui la SEC le fa intestare. Il titolo serve a distinguere
# occorrenze omonime — in un 10-Q "Item 2" e' l'MD&A della Parte I, ma "Item 2"
# esiste anche nella Parte II (vendite di titoli non registrati).
SEZIONI_ANNUALE = {
    "business": {"item": "1", "titolo": "business"},
    "risk_factors": {"item": "1A", "titolo": "risk factors"},
    "legal_proceedings": {"item": "3", "titolo": "legal proceedings"},
    "mda": {"item": "7", "titolo": "management's discussion"},
    "market_risk": {"item": "7A", "titolo": "quantitative and qualitative"},
}

SEZIONI_TRIMESTRALE = {
    "mda": {"item": "2", "titolo": "management's discussion"},
    "risk_factors": {"item": "1A", "titolo": "risk factors"},
    "market_risk": {"item": "3", "titolo": "quantitative and qualitative"},
}

# Un'intestazione di Item: "Item 1.", "ITEM 1A —", "Item 7A". Il titolo puo'
# stare sulla riga dopo, perche' nell'HTML originale numero e titolo sono
# celle diverse di una tabella e l'estrattore le separa.
#
# **A INIZIO RIGA**, ed e' la regola che fa la differenza fra una sezione e un
# pezzo di sezione. Misurato su un documento con le trappole vere: senza questo
# vincolo, la frase «For a discussion of risks, see Item 1A. Risk Factors»
# scritta dentro Business tagliava Business a un terzo E faceva cominciare li'
# Risk Factors, che si portava dietro la coda di Business. Un rimando sta in
# mezzo a una frase; un titolo apre la riga.
INTESTAZIONE = re.compile(r"(?im)^[^\S\n]{0,10}item\s*(\d{1,2})\s*([a-c])?\b")

# Se in tutto il documento non c'e' nemmeno un'intestazione a inizio riga per
# l'Item cercato, si riprova senza quel vincolo: un .txt vecchio o un HTML
# estratto male puo' avere il titolo in mezzo a una riga, e perdere la sezione
# sarebbe peggio che leggerne una imprecisa.
INTESTAZIONE_LARGA = re.compile(r"(?i)\bitem\s*(\d{1,2})\s*([a-c])?\b")

# Quanto si guarda avanti per vedere se accanto al numero c'e' il titolo atteso.
FINESTRA_TITOLO = 120

# Sotto questa lunghezza non e' una sezione, e' una voce d'indice.
#
# Misurato sul 10-K vero di NVDA: la voce d'indice di «Item 3» apre 29
# caratteri, la sezione vera ne apre 197 — ed e' una sezione vera che dice
# «Please see Note 12». **Una sezione breve resta una sezione**, e la soglia
# stava a 500: rifiutava un Item 3 che c'era, dicendo per giunta che erano
# rimandi. Con le intestazioni ancorate a inizio riga i rimandi non arrivano
# nemmeno qui, e questa soglia deve solo separare l'indice dal testo.
LUNGHEZZA_MINIMA = 120


def _rango(numero: str, lettera: str | None) -> tuple[int, str]:
    """L'ordine di un Item nel documento: 1 < 1A < 2 < 7 < 7A."""
    return int(numero), (lettera or "").upper()


def _intestazioni(testo: str, espressione) -> list[tuple[int, tuple[int, str]]]:
    """Ogni "Item N" del documento: dove sta e che rango ha."""
    return [(m.start(), _rango(m.group(1), m.group(2)))
            for m in espressione.finditer(testo)]


def _fine(testo_minuscolo: str, tutte: list, inizio: int, rango: tuple) -> int:
    """Dove finisce la sezione: alla prossima intestazione di un Item DIVERSO.

    Diverso e non "successivo", ed e' una differenza che si paga a non fare: in
    un 10-Q la numerazione **riparte** nella Parte II, quindi l'MD&A (Item 2
    della Parte I) e' seguito dai Risk Factors (Item 1A della Parte II), che
    hanno un numero piu' basso. Cercando l'Item successivo, l'MD&A si prendeva
    dentro anche i rischi.

    Che sia diverso e non semplicemente il prossimo serve invece ai documenti
    che ripetono il titolo dell'Item in testa a ogni pagina: quelle ripetizioni
    hanno lo stesso rango, e non chiudono la sezione dopo mezza riga.
    """
    for posizione, altro in tutte:
        if posizione > inizio and altro != rango:
            return posizione
    return len(testo_minuscolo)


def _intervalli(testo: str, cercato: tuple, titolo: str,
                espressione) -> list[tuple[int, int]]:
    """Gli intervalli plausibili per una sezione, con una sola lettura del testo.

    Se in almeno una occorrenza il titolo atteso segue il numero, si tengono
    solo quelle: e' il segnale piu' forte che quello e' un titolo e non un
    rimando.
    """
    minuscolo = testo.lower()
    tutte = _intestazioni(testo, espressione)

    con_titolo, senza = [], []
    for posizione, rango in tutte:
        if rango != cercato:
            continue
        intervallo = (posizione, _fine(minuscolo, tutte, posizione, rango))
        vicino = minuscolo[posizione:posizione + FINESTRA_TITOLO]
        (con_titolo if titolo in vicino else senza).append(intervallo)

    return con_titolo or senza


def _candidati(testo: str, item: str, titolo: str) -> list[tuple[int, int]]:
    """Gli intervalli plausibili: prima con le intestazioni vere, poi allargando."""
    numero, lettera = re.match(r"(\d{1,2})([A-C]?)", item).groups()
    cercato = _rango(numero, lettera or None)

    stretti = _intervalli(testo, cercato, titolo, INTESTAZIONE)
    return stretti or _intervalli(testo, cercato, titolo, INTESTAZIONE_LARGA)


def estrai(testo: str, sezione: str, forma: str) -> tuple[str | None, str | None]:
    """Il testo di una sezione. Ritorna `(testo, motivo)`, mai un None muto.

    `forma` e' il tipo di documento: cambia quale Item ospita cosa.
    """
    mappa = SEZIONI_ANNUALE if forma == "10-K" else SEZIONI_TRIMESTRALE
    definizione = mappa.get(sezione)
    if definizione is None:
        return None, (f"la sezione {sezione!r} non e' prevista per un {forma}: "
                      f"ci sono {', '.join(mappa)}")

    intervalli = _candidati(testo or "", definizione["item"], definizione["titolo"])
    if not intervalli:
        return None, (f"nessun «Item {definizione['item']}» nel documento: "
                      f"il testo estratto potrebbe non essere il documento principale")

    inizio, fine = max(intervalli, key=lambda coppia: coppia[1] - coppia[0])
    estratto = (testo[inizio:fine]).strip()

    if len(estratto) < LUNGHEZZA_MINIMA:
        return None, (f"«Item {definizione['item']}» compare ma apre solo "
                      f"{len(estratto)} caratteri: e' la voce dell'indice, non "
                      f"la sezione — nel documento la sezione potrebbe mancare")

    return estratto, None


def disponibili(testo: str, forma: str) -> dict[str, int]:
    """Quali sezioni si riescono a leggere, e quanto sono lunghe.

    Serve a dire cosa c'e' PRIMA di costruire un prompt: una sezione che manca
    si dichiara, non si scopre a meta' analisi.
    """
    mappa = SEZIONI_ANNUALE if forma == "10-K" else SEZIONI_TRIMESTRALE
    trovate = {}
    for nome in mappa:
        estratto, _ = estrai(testo, nome, forma)
        if estratto is not None:
            trovate[nome] = len(estratto)
    return trovate
