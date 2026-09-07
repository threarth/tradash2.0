"""
scansione.py — decidere se un titolo soddisfa dei criteri, guardando i prezzi.
# feat (Blocco 9): la parte che decide, senza sapere da dove vengono i prezzi.

Ogni criterio e' una funzione che riceve le misure gia' calcolate e ritorna
`(soddisfatto, spiegazione)`. La spiegazione non e' un lusso: uno scanner che
dice solo "sette titoli" costringe a fidarsi, e "basato su cosa?" e' la domanda
che nel vecchio sistema non aveva risposta.

Matematica pura: entrano prezzi e soglie, escono verdetti.
"""
from domain import drawdown

# Le finestre su cui si misurano le variazioni, in sedute.
FINESTRA_BREVE = 21
FINESTRA_MEDIA = 63
FINESTRA_LUNGA = 252

# Quanti trimestri fanno un anno. Serve al confronto anno su anno, che e' l'unico
# modo di guardare i ricavi senza guardare il calendario.
TRIMESTRI_PER_ANNO = 4


def _media(valori: list[float]) -> float | None:
    return sum(valori) / len(valori) if valori else None


def _variazione(chiusure: list[float], sedute: int) -> float | None:
    """Variazione percentuale sulle ultime N sedute. `None` se non ce ne sono abbastanza."""
    if len(chiusure) <= sedute:
        return None
    prima = chiusure[-sedute - 1]
    return None if prima == 0 else (chiusure[-1] - prima) / prima


def misure(chiusure: list[float], volumi: list[float] | None = None) -> dict:
    """Tutto quello che si puo' dire di un titolo guardando solo i suoi prezzi.

    Le misure che non si possono calcolare valgono `None` e non zero: un titolo
    quotato da tre mesi non ha una variazione a un anno pari a zero, non ce
    l'ha affatto.
    """
    return {
        "ultimo_prezzo": chiusure[-1] if chiusure else None,
        "sedute": len(chiusure),
        "variazione_1m": _variazione(chiusure, FINESTRA_BREVE),
        "variazione_3m": _variazione(chiusure, FINESTRA_MEDIA),
        "variazione_1a": _variazione(chiusure, FINESTRA_LUNGA),
        "media_50": _media(chiusure[-50:]) if len(chiusure) >= 50 else None,
        "media_200": _media(chiusure[-200:]) if len(chiusure) >= 200 else None,
        "volume_medio": _media(volumi[-FINESTRA_BREVE:]) if volumi else None,
        "drawdown": drawdown.profilo(chiusure),
        # I bilanci li mette chi chiama, perche' vanno letti: qui c'e' il posto
        # dove vanno, cosi' un criterio di bilancio trova sempre la casella —
        # vuota se nessuno l'ha riempita, e allora il criterio non passa.
        "fondamentali": fondamentali({}, []),
    }


def fondamentali(voci: dict, utili: list[str]) -> dict:
    """Cosa si puo' dire di un titolo guardando i suoi ultimi due trimestri utili.

    `utili` sono i periodi gia' pubblici alla data che interessa, in ordine: chi
    chiama li ha gia' tagliati col point-in-time, perche' qui dentro non si
    legge niente e non si indovina nessun ritardo di deposito.

    Con meno di due trimestri non c'e' accelerazione da misurare, e le misure
    valgono `None` — che non e' zero: un titolo che ha pubblicato un trimestre
    solo non ha una crescita pari a zero, non ce l'ha affatto.
    """
    vuote = {"ricavi_qoq": None, "ricavi_yoy": None, "margine": None,
             "margine_variazione": None, "eps": None, "trimestri": len(utili)}
    if len(utili) < 2:
        return vuote

    ora, prima = utili[-1], utili[-2]
    ricavi, lordo, eps = (voci.get(n, {}) for n in
                          ("total_revenue", "gross_profit", "diluted_eps"))
    misurate = dict(vuote)

    if ricavi.get(prima):
        misurate["ricavi_qoq"] = ricavi[ora] / ricavi[prima] - 1 if ora in ricavi else None
    if ricavi.get(ora) and ora in lordo:
        misurate["margine"] = lordo[ora] / ricavi[ora]
        if ricavi.get(prima) and prima in lordo:
            misurate["margine_variazione"] = misurate["margine"] - lordo[prima] / ricavi[prima]
    if ora in eps:
        misurate["eps"] = eps[ora]

    # Anno su anno, cioe' contro lo STESSO trimestre dell'anno prima. Serve a
    # togliere di mezzo la stagionalita': un trimestre di Natale batte quello
    # prima quasi sempre, e un criterio sul trimestre su trimestre finisce per
    # selezionare il calendario invece della crescita. Servono cinque trimestri.
    if len(utili) >= TRIMESTRI_PER_ANNO + 1:
        anno_fa = utili[-(TRIMESTRI_PER_ANNO + 1)]
        if ricavi.get(anno_fa) and ora in ricavi:
            misurate["ricavi_yoy"] = ricavi[ora] / ricavi[anno_fa] - 1

    return misurate


def _confronta(valore, soglia, minimo: bool) -> bool:
    """Un confronto che non inventa: se il valore manca, il criterio non passa."""
    if valore is None or soglia is None:
        return False
    return valore >= soglia if minimo else valore <= soglia


# I criteri disponibili: nome → (come si misura, se la soglia e' un minimo, come si spiega).
CRITERI = {
    "drawdown_minimo": (
        lambda m: abs(m["drawdown"]["profondita_attuale"]) if m["drawdown"] else None,
        True, "sceso almeno del {soglia:.0%} dal suo massimo (adesso {valore:.1%})",
    ),
    "drawdown_massimo": (
        lambda m: abs(m["drawdown"]["profondita_attuale"]) if m["drawdown"] else None,
        False, "sceso non piu' del {soglia:.0%} (adesso {valore:.1%})",
    ),
    "recupero_minimo": (
        lambda m: m["drawdown"]["recupero_dal_fondo"] if m["drawdown"] else None,
        True, "ha recuperato almeno il {soglia:.0%} dal fondo (adesso {valore:.0%})",
    ),
    "variazione_1a_minima": (
        lambda m: m["variazione_1a"], True,
        "in crescita di almeno il {soglia:.0%} in un anno (adesso {valore:.1%})",
    ),
    "sopra_media_200": (
        lambda m: (m["ultimo_prezzo"] / m["media_200"] - 1) if m["media_200"] else None,
        True, "sopra la media a 200 sedute di almeno il {soglia:.0%} (adesso {valore:.1%})",
    ),
    "volume_medio_minimo": (
        lambda m: m["volume_medio"], True,
        "volume medio di almeno {soglia:,.0f} (adesso {valore:,.0f})",
    ),
    # --- i criteri di bilancio ---------------------------------------------
    #
    # Prima lo scanner sapeva solo com'e' andato il PREZZO: undicimila titoli e
    # nessuna domanda sull'azienda. Questi tre chiedono la stessa cosa che il
    # rilevatore spin-off chiede ai suoi ventisette — «i numeri stanno
    # girando?» — a tutto l'universo.
    #
    # Valgono `None` per chi non ha due trimestri pubblici, e un criterio su un
    # valore che manca NON passa: e' la stessa regola di `_confronta`.
    "ricavi_qoq_minimo": (
        lambda m: m["fondamentali"]["ricavi_qoq"], True,
        "ricavi in crescita di almeno il {soglia:.0%} sul trimestre prima "
        "(adesso {valore:+.1%})",
    ),
    "ricavi_yoy_minimo": (
        lambda m: m["fondamentali"]["ricavi_yoy"], True,
        "ricavi in crescita di almeno il {soglia:.0%} sullo stesso trimestre "
        "dell'anno prima (adesso {valore:+.1%})",
    ),
    "margine_crescita_minima": (
        lambda m: m["fondamentali"]["margine_variazione"], True,
        "margine lordo in crescita di almeno {soglia:.1%} in un trimestre "
        "(adesso {valore:+.1%})",
    ),
    "eps_minimo": (
        lambda m: m["fondamentali"]["eps"], True,
        "EPS dell'ultimo trimestre pubblicato almeno {soglia:.2f} "
        "(adesso {valore:.2f})",
    ),
}


def valuta(misurato: dict, criteri: dict) -> tuple[bool, list[str]]:
    """Il titolo soddisfa tutti i criteri? Ritorna anche PERCHE'.

    Un criterio su una misura che manca non passa: fingere che un dato assente
    valga zero e' il modo piu' rapido di riempire uno scanner di titoli che non
    c'entrano niente.
    """
    spiegazioni: list[str] = []
    for nome, soglia in criteri.items():
        definizione = CRITERI.get(nome)
        if definizione is None or soglia is None:
            continue
        misura, minimo, testo = definizione
        valore = misura(misurato)
        if not _confronta(valore, soglia, minimo):
            return False, []
        spiegazioni.append(testo.format(soglia=soglia, valore=valore))

    return True, spiegazioni
