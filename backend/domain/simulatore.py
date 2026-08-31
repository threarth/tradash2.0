"""
simulatore.py — cosa si sarebbe vissuto tenendo un titolo, giorno per giorno.
# feat (Blocco 9, ripreso): il simulatore psicologico del vecchio tradash.

Non e' un backtest di strategia: non c'e' nessuna strategia. C'e' una posizione
sola, comprata un giorno e tenuta fino a oggi, e la domanda a cui risponde non
e' «quanto avrei guadagnato» ma **«cosa avrei passato»**.

Sono due domande diverse e la seconda si dimentica sempre. Un titolo che ha
fatto +150% in tre anni si racconta come una buona idea; se nel mezzo e' sceso
del 40% e ci ha messo undici mesi a tornare in pari, la buona idea l'avrebbero
tenuta in pochi. Le misure qui sotto servono a mostrare quel mezzo.

## La tabella rossa e verde

Le variazioni giornaliere disposte con **i mesi in colonna e i giorni in riga**.
Il giorno della settimana cambia da un mese all'altro — il 5 e' lunedi' a marzo
e giovedi' ad aprile — quindi ogni cella se lo porta dietro: senza, si legge una
griglia di numeri credendo che le righe siano settimane.

Le celle vuote non sono zeri: sono giorni in cui la borsa era chiusa, oppure
giorni che quel mese non ha. Un calendario che disegna lo zero dove non c'e'
stata contrattazione fa sembrare piatti i fine settimana.

## Il periodo come base

Ogni variazione si puo' leggere in due modi, e la differenza non e' estetica:
**giorno su giorno** dice com'e' stata la giornata; **dal punto di partenza**
dice a che punto si era arrivati. La prima e' quello che si sente, la seconda e'
quello che si ricorda. Il simulatore le tiene tutte e due.
"""
import calendar
from datetime import date

# Le lettere con cui si nomina il giorno della settimana in italiano. Servono
# nella tabella, dove lo spazio per una parola non c'e'.
GIORNI_SETTIMANA = ("L", "M", "M", "G", "V", "S", "D")

# Sotto questo numero di sedute non c'e' niente da rivivere: una settimana di
# prezzi non racconta nessuna esperienza.
SEDUTE_MINIME = 20


def _giorno(iso: str) -> date:
    return date.fromisoformat(str(iso)[:10])


def variazioni(barre: list[dict]) -> list[dict]:
    """Ogni seduta con la sua variazione rispetto alla precedente.

    La prima seduta non ha un giorno prima: la sua variazione e' `None`, non
    zero. Zero vorrebbe dire «non si e' mossa», e non e' quello che sappiamo.
    """
    fatte = []
    precedente = None
    for barra in barre:
        chiusura = barra.get("close")
        if chiusura is None:
            continue
        quando = _giorno(barra["timestamp"])
        fatte.append({
            "data": quando.isoformat(),
            "chiusura": round(float(chiusura), 4),
            "variazione": (None if not precedente
                           else round(float(chiusura) / precedente - 1, 6)),
            "giorno_settimana": GIORNI_SETTIMANA[quando.weekday()],
        })
        precedente = float(chiusura)
    return fatte


def dal_punto(sedute: list[dict], riferimento: str | None = None) -> list[dict]:
    """Le stesse sedute, ma con la variazione misurata dal punto di partenza.

    `riferimento` e' la data da cui contare; se manca, e' la prima seduta. Le
    sedute PRIMA del riferimento restano nell'elenco con variazione `None`:
    toglierle nasconderebbe che il periodo scelto comincia piu' tardi.
    """
    if not sedute:
        return []

    base = None
    fatte = []
    for seduta in sedute:
        if base is None and (riferimento is None or seduta["data"] >= riferimento):
            base = seduta["chiusura"]
        fatte.append({
            **seduta,
            "variazione": (None if base is None or not base
                           else round(seduta["chiusura"] / base - 1, 6)),
        })
    return fatte


def griglia(sedute: list[dict]) -> dict:
    """Le sedute disposte per mese e giorno: i mesi in colonna, i giorni in riga.

    Ritorna le colonne (un mese ciascuna, in ordine), le righe (1-31) e le celle
    indicizzate per `(mese, giorno)`. Chi disegna non deve fare conti di
    calendario: qui c'e' gia' tutto, comprese le caselle che quel mese non ha.
    """
    celle: dict[str, dict] = {}
    mesi: list[str] = []

    for seduta in sedute:
        quando = _giorno(seduta["data"])
        mese = f"{quando.year}-{quando.month:02d}"
        if mese not in celle:
            celle[mese] = {}
            mesi.append(mese)
        celle[mese][quando.day] = seduta

    return {
        "mesi": [{"chiave": mese, "anno": int(mese[:4]), "mese": int(mese[5:]),
                  "giorni_del_mese": calendar.monthrange(int(mese[:4]), int(mese[5:]))[1]}
                 for mese in mesi],
        "giorni": list(range(1, 32)),
        "celle": celle,
    }


def esperienza(sedute: list[dict], capitale: float) -> dict:
    """Cosa si sarebbe vissuto: il valore, il peggio attraversato, il tempo perso.

    Il «peggio attraversato» non e' la perdita finale: e' la discesa massima dal
    punto piu' alto raggiunto fino ad allora, che e' il numero che si guarda
    mentre sta succedendo. E i «giorni sotto» sono quelli passati in perdita
    rispetto al prezzo pagato — il tempo, che nessun rendimento annuo racconta.
    """
    if len(sedute) < SEDUTE_MINIME:
        return {"available": False,
                "reason": f"servono almeno {SEDUTE_MINIME} sedute per raccontare "
                          f"un'esperienza, ce ne sono {len(sedute)}",
                "action": "scegli una data d'acquisto piu' lontana"}

    prezzo_pagato = sedute[0]["chiusura"]
    quote = capitale / prezzo_pagato if prezzo_pagato else 0.0

    massimo = prezzo_pagato
    discesa_peggiore = 0.0
    giorni_sotto = 0
    giorni_dal_massimo = 0
    attesa_piu_lunga = 0
    migliore = peggiore = None

    for seduta in sedute:
        chiusura = seduta["chiusura"]
        if chiusura >= massimo:
            massimo = chiusura
            giorni_dal_massimo = 0
        else:
            giorni_dal_massimo += 1
            attesa_piu_lunga = max(attesa_piu_lunga, giorni_dal_massimo)
        discesa_peggiore = min(discesa_peggiore, chiusura / massimo - 1)
        giorni_sotto += int(chiusura < prezzo_pagato)

        movimento = seduta.get("variazione")
        if movimento is not None:
            if migliore is None or movimento > migliore["variazione"]:
                migliore = seduta
            if peggiore is None or movimento < peggiore["variazione"]:
                peggiore = seduta

    ultima = sedute[-1]
    return {
        "available": True,
        "reason": f"{len(sedute)} sedute dal {sedute[0]['data']} al {ultima['data']}",
        "prezzo_pagato": round(prezzo_pagato, 4),
        "quote": round(quote, 6),
        "capitale": round(capitale, 2),
        "valore_oggi": round(quote * ultima["chiusura"], 2),
        "rendimento": round(ultima["chiusura"] / prezzo_pagato - 1, 6),
        "discesa_peggiore": round(discesa_peggiore, 6),
        "giorni_sotto_il_prezzo_pagato": giorni_sotto,
        "quota_del_tempo_in_perdita": round(giorni_sotto / len(sedute), 4),
        "attesa_piu_lunga_sotto_il_massimo": attesa_piu_lunga,
        "giorno_migliore": migliore,
        "giorno_peggiore": peggiore,
    }
