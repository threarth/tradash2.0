"""
segnali.py — i cinque segnali di rischio fondamentale, dai bilanci.
# feat (Blocco 8): F1-F5 ricalcolati sulla forma dati di qui.

  F1  deterioramento dei margini
  F2  deterioramento della crescita
  F3  stress finanziario / leva
  F4  stress di liquidita'
  F5  diluizione azionaria

**Non e' un porting riga per riga.** Nel vecchio tradash questi segnali
leggevano un motore di feature che a sua volta leggeva quattro servizi; qui
leggono i prospetti cosi' come li produce `domain/prospetti.py`. Le soglie
invece sono quelle di allora, gia' tarate girando: sono in `config`, perche' un
giudizio che cambia al cambiare di una soglia deve poter dire quale soglia.

Due principi che questo modulo rende espliciti, e che vengono da li':

1. **La qualita' dell'azienda e la qualita' dei dati sono cose diverse.**
   `ignoto` dice che il dato manca, non che l'azienda e' peggiore. Non incide
   sul giudizio economico: incide sulla copertura, che si dichiara a parte.
2. **Un segnale porta sempre le sue misure.** Un verdetto senza i numeri su cui
   poggia costringe a fidarsi, ed e' invendibile alla domanda "in base a cosa?".
"""
import statistics

import config

# Gli stati di un segnale. `IGNOTO` non e' una via di mezzo fra acceso e
# spento: e' l'assenza del dato, e va contata da un'altra parte.
ACCESO = "acceso"
ATTENZIONE = "attenzione"
SPENTO = "spento"
IGNOTO = "ignoto"

# Le voci di bilancio usate, coi nomi di Defeatbeta.
VOCE_RICAVI = "total_revenue"
VOCE_RICAVI_OPERATIVI = "operating_revenue"
VOCE_MARGINE_LORDO = "gross_profit"
VOCE_REDDITO_OPERATIVO = "operating_income"
VOCE_EBITDA = "ebitda"
VOCE_INTERESSI = "interest_expense"
VOCE_DEBITO_NETTO = "net_debt"
VOCE_CASSA = "cash_and_cash_equivalents"
VOCE_FCF = "free_cash_flow"
VOCE_AZIONI = "diluted_average_shares"

# Quanti trimestri fanno un anno: serve a confrontare un periodo con lo stesso
# periodo dell'anno prima, non col trimestre precedente.
TRIMESTRI_ANNO = 4

NOMI = {
    "F1": "deterioramento dei margini",
    "F2": "deterioramento della crescita",
    "F3": "stress finanziario / leva",
    "F4": "stress di liquidita'",
    "F5": "diluizione azionaria",
}


def _segnale(stato: str, perche: str, **misure) -> dict:
    """Un segnale: lo stato, la frase che lo spiega, e i numeri su cui poggia."""
    return {"stato": stato, "perche": perche,
            "misure": {k: (round(v, 4) if isinstance(v, float) else v)
                       for k, v in misure.items() if v is not None}}


def _ignoto(perche: str, **misure) -> dict:
    return _segnale(IGNOTO, perche, **misure)


def serie(prospetto: dict, voce: str) -> list[tuple[str, float]]:
    """I valori di una voce, dal periodo piu' vecchio al piu' recente."""
    valori = prospetto.get("voci", {}).get(voce, {})
    return [(periodo, valori[periodo]) for periodo in sorted(valori)]


def _ultimo(prospetto: dict, voce: str) -> float | None:
    valori = serie(prospetto, voce)
    return valori[-1][1] if valori else None


def _somma_ttm(prospetto: dict, voce: str) -> float | None:
    """La somma degli ultimi quattro trimestri. `None` se non ce ne sono quattro."""
    valori = [v for _, v in serie(prospetto, voce)]
    return sum(valori[-TRIMESTRI_ANNO:]) if len(valori) >= TRIMESTRI_ANNO else None


def _ricavi(conto: dict) -> list[tuple[str, float]]:
    """I ricavi, col ripiego sui ricavi operativi quando la voce principale manca."""
    return serie(conto, VOCE_RICAVI) or serie(conto, VOCE_RICAVI_OPERATIVI)


# --- F1: i margini si stanno deteriorando? ---------------------------------

def f1_margini(conto: dict) -> dict:
    """Confronta la mediana dei margini recenti con quella dei precedenti.

    La mediana e non la media: un trimestre eccezionale — una svalutazione, una
    causa vinta — sposterebbe la media e farebbe suonare o tacere il segnale
    per un evento che non e' una tendenza.
    """
    ricavi = dict(_ricavi(conto))
    lordo = dict(serie(conto, VOCE_MARGINE_LORDO))
    periodi = sorted(p for p in ricavi if p in lordo and ricavi[p])

    if len(periodi) < config.F1_TRIMESTRI_MINIMI:
        return _ignoto(f"servono almeno {config.F1_TRIMESTRI_MINIMI} trimestri con "
                       f"ricavi e margine lordo, ce ne sono {len(periodi)}",
                       trimestri=len(periodi))

    margini = [lordo[p] / ricavi[p] for p in periodi]
    meta = len(margini) // 2
    prima = statistics.median(margini[:meta]) * 100
    dopo = statistics.median(margini[meta:]) * 100
    calo = prima - dopo

    misure = {"margine_lordo_recente_pp": dopo, "margine_lordo_precedente_pp": prima,
              "calo_pp": calo, "trimestri": len(periodi)}

    if calo >= config.F1_CALO_MARGINE_PP_ACCESO:
        return _segnale(ACCESO, f"margine lordo giu' di {calo:.1f} punti "
                                f"({prima:.1f}% → {dopo:.1f}%)", **misure)
    if calo >= config.F1_CALO_MARGINE_PP_ATTENZIONE:
        return _segnale(ATTENZIONE, f"margine lordo giu' di {calo:.1f} punti", **misure)
    return _segnale(SPENTO, f"margine lordo stabile o in crescita "
                            f"({prima:.1f}% → {dopo:.1f}%)", **misure)


# --- F2: la crescita si sta rompendo? --------------------------------------

def f2_crescita(conto: dict) -> dict:
    """Guarda due cose insieme: trimestri consecutivi in calo, e decelerazione.

    Il confronto e' sempre con lo STESSO trimestre dell'anno prima: un business
    stagionale confrontato col trimestre precedente sembra sempre in crisi
    d'inverno e in boom d'estate.
    """
    ricavi = _ricavi(conto)
    if len(ricavi) < TRIMESTRI_ANNO + 2:
        return _ignoto(f"servono almeno {TRIMESTRI_ANNO + 2} trimestri di ricavi, "
                       f"ce ne sono {len(ricavi)}", trimestri=len(ricavi))

    valori = [v for _, v in ricavi]
    crescite = [
        (valori[i] - valori[i - TRIMESTRI_ANNO]) / valori[i - TRIMESTRI_ANNO]
        for i in range(TRIMESTRI_ANNO, len(valori)) if valori[i - TRIMESTRI_ANNO]
    ]
    if not crescite:
        return _ignoto("ricavi a zero nei periodi di confronto")

    in_calo = 0
    for crescita in reversed(crescite):
        if crescita >= 0:
            break
        in_calo += 1

    ultima = crescite[-1]
    precedente = crescite[-2] if len(crescite) > 1 else None
    decelerazione = (
        None if precedente is None or precedente <= 0
        else (precedente - ultima) / precedente
    )

    misure = {"crescita_annua": ultima, "crescita_precedente": precedente,
              "decelerazione": decelerazione, "trimestri_in_calo": in_calo}

    if in_calo >= config.F2_TRIMESTRI_DI_CALO:
        return _segnale(ACCESO, f"ricavi in calo da {in_calo} trimestri "
                                f"(ultimo {ultima:.1%})", **misure)
    if decelerazione is not None and decelerazione >= config.F2_DECELERAZIONE_ACCESA:
        return _segnale(ACCESO, f"crescita rallentata del {decelerazione:.0%} "
                                f"({precedente:.1%} → {ultima:.1%})", **misure)
    if decelerazione is not None and decelerazione >= config.F2_DECELERAZIONE_ATTENZIONE:
        return _segnale(ATTENZIONE, f"crescita in rallentamento "
                                    f"({precedente:.1%} → {ultima:.1%})", **misure)
    return _segnale(SPENTO, f"crescita annua {ultima:.1%}, senza rotture", **misure)


# --- F3: la struttura finanziaria regge? -----------------------------------

def f3_leva(conto: dict, patrimoniale: dict) -> dict:
    """Debito netto sull'EBITDA e copertura degli interessi.

    Con EBITDA negativo la leva non e' misurabile in multipli: il rischio si
    sposta tutto sulla liquidita', e questo segnale lo DICE invece di produrre
    un multiplo senza senso.
    """
    ebitda = _somma_ttm(conto, VOCE_EBITDA)
    debito = _ultimo(patrimoniale, VOCE_DEBITO_NETTO)

    if ebitda is None or debito is None:
        return _ignoto("mancano EBITDA o debito netto")
    if ebitda <= 0:
        return _ignoto("EBITDA negativo: la leva non e' misurabile in multipli, "
                       "il rischio e' tutto in F4", ebitda_ttm=ebitda)

    multiplo = debito / ebitda
    interessi = _somma_ttm(conto, VOCE_INTERESSI)
    copertura = (ebitda / abs(interessi)) if interessi else None

    misure = {"debito_netto_su_ebitda": multiplo, "copertura_interessi": copertura,
              "ebitda_ttm": ebitda, "debito_netto": debito}

    if multiplo > config.F3_DEBITO_SU_EBITDA_ACCESO:
        return _segnale(ACCESO, f"debito netto pari a {multiplo:.1f} volte l'EBITDA", **misure)
    if copertura is not None and copertura < config.F3_COPERTURA_INTERESSI_ACCESA:
        return _segnale(ACCESO, f"l'EBITDA copre gli interessi solo "
                                f"{copertura:.1f} volte", **misure)
    return _segnale(SPENTO, f"debito netto a {multiplo:.1f} volte l'EBITDA", **misure)


# --- F4: la cassa dura? ----------------------------------------------------

def autonomia_trimestri(conto_cassa: dict, patrimoniale: dict) -> float | None:
    """Quanti trimestri dura la cassa al ritmo di consumo attuale.

    `None` quando l'azienda NON sta bruciando cassa, o quando i dati mancano:
    in nessuno dei due casi esiste un'autonomia da contare. Una definizione
    sola per tutto il sistema, come nel vecchio tradash.
    """
    cassa = _ultimo(patrimoniale, VOCE_CASSA)
    flussi = serie(conto_cassa, VOCE_FCF)
    if cassa is None or not flussi:
        return None

    ultimo_flusso = flussi[-1][1]
    return None if ultimo_flusso >= 0 else cassa / abs(ultimo_flusso)


def f4_liquidita(conto_cassa: dict, patrimoniale: dict) -> dict:
    """Trimestri di autonomia sono trimestri di autonomia, in ogni fase di vita."""
    autonomia = autonomia_trimestri(conto_cassa, patrimoniale)
    cassa = _ultimo(patrimoniale, VOCE_CASSA)

    if autonomia is None:
        if cassa is None:
            return _ignoto("manca la cassa")
        return _segnale(SPENTO, "non sta bruciando cassa", cassa=cassa)

    misure = {"autonomia_trimestri": autonomia, "cassa": cassa}
    if autonomia < config.F4_AUTONOMIA_TRIMESTRI_ACCESA:
        return _segnale(ACCESO, f"la cassa dura {autonomia:.1f} trimestri "
                                f"al ritmo attuale", **misure)
    if autonomia < config.F4_AUTONOMIA_TRIMESTRI_ATTENZIONE:
        return _segnale(ATTENZIONE, f"la cassa dura {autonomia:.1f} trimestri", **misure)
    return _segnale(SPENTO, f"la cassa dura {autonomia:.1f} trimestri", **misure)


# --- F5: quante azioni in piu' ---------------------------------------------

def f5_diluizione(conto: dict) -> dict:
    """Crescita annua del numero di azioni diluite.

    Il confronto e' a un anno di distanza e non col trimestre prima: un
    riacquisto concentrato in un trimestre farebbe sembrare la diluizione
    negativa proprio mentre l'anno la vede crescere.
    """
    azioni = serie(conto, VOCE_AZIONI)
    if len(azioni) <= TRIMESTRI_ANNO:
        return _ignoto(f"servono piu' di {TRIMESTRI_ANNO} trimestri di azioni diluite",
                       trimestri=len(azioni))

    adesso = azioni[-1][1]
    anno_fa = azioni[-1 - TRIMESTRI_ANNO][1]
    if not anno_fa:
        return _ignoto("numero di azioni a zero un anno fa")

    crescita = (adesso - anno_fa) / anno_fa
    misure = {"crescita_azioni_annua": crescita, "azioni_adesso": adesso,
              "azioni_un_anno_fa": anno_fa}

    if crescita >= config.F5_DILUIZIONE_ACCESA:
        return _segnale(ACCESO, f"azioni cresciute del {crescita:.1%} in un anno", **misure)
    if crescita >= config.F5_DILUIZIONE_ATTENZIONE:
        return _segnale(ATTENZIONE, f"azioni cresciute del {crescita:.1%} in un anno", **misure)
    if crescita < 0:
        return _segnale(SPENTO, f"azioni ridotte del {abs(crescita):.1%}: riacquisti", **misure)
    return _segnale(SPENTO, f"diluizione contenuta ({crescita:.1%})", **misure)


# --- tutti insieme ----------------------------------------------------------

def tutti(prospetti_per_tipo: dict) -> dict:
    """I cinque segnali, piu' la copertura — che e' una misura a parte.

    La copertura dice quanti segnali si sono potuti calcolare. Tre segnali
    spenti su cinque calcolabili non sono la stessa cosa di tre spenti su
    cinque quando gli altri due erano ignoti, e un numero solo le confonderebbe.
    """
    conto = prospetti_per_tipo.get("income_statement", {})
    patrimoniale = prospetti_per_tipo.get("balance_sheet", {})
    cassa = prospetti_per_tipo.get("cash_flow", {})

    segnali = {
        "F1": f1_margini(conto),
        "F2": f2_crescita(conto),
        "F3": f3_leva(conto, patrimoniale),
        "F4": f4_liquidita(cassa, patrimoniale),
        "F5": f5_diluizione(conto),
    }
    for chiave, segnale in segnali.items():
        segnale["nome"] = NOMI[chiave]

    calcolati = [s for s in segnali.values() if s["stato"] != IGNOTO]
    accesi = [c for c, s in segnali.items() if s["stato"] == ACCESO]
    attenzione = [c for c, s in segnali.items() if s["stato"] == ATTENZIONE]

    return {
        "segnali": segnali,
        "accesi": accesi,
        "attenzione": attenzione,
        "copertura": {
            "calcolati": len(calcolati),
            "totali": len(segnali),
            "ignoti": [c for c, s in segnali.items() if s["stato"] == IGNOTO],
        },
    }
