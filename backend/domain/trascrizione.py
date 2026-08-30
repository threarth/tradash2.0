"""
trascrizione.py — una earnings call divisa in cio' che serve leggere.
# feat (Blocco 8): matematica pura sulle parole, nessuna lettura.

Una trascrizione arriva come elenco di paragrafi `{numero, oratore, testo}`:
per NVDA, 75 paragrafi e 46.000 caratteri. Mandarla intera a un modello si puo',
ma perde la cosa che la rende utile — che una earnings call ha **due meta'
diverse**, e vanno lette in modo diverso:

* la **parte preparata**, dove il management dice cio' che ha deciso di dire, e
  dove sta la guidance dichiarata a voce;
* il **botta e risposta**, dove gli analisti chiedono cio' che il management non
  aveva messo nel comunicato — ed e' li' che si vede cosa il mercato teme.

Chi sia il management non lo si indovina: e' chi parla PRIMA che comincino le
domande. Ricavarlo dai dati invece che da un elenco di nomi vuol dire che
funziona anche per le societa' che non conosciamo.
"""

# Come si riconosce il passaggio alle domande. L'operatore lo annuncia, ma lo
# nomina anche nel saluto iniziale — "after the speakers' remarks, there will be
# a question-and-answer session" — quindi le parole da sole non bastano: vedi
# `_inizio_domande`.
SEGNI_DI_DOMANDE = ("question-and-answer", "question and answer", "first question",
                    "next question", "ask a question", "we'll take our first",
                    "will now begin the q&a")

ORATORE_OPERATORE = "operator"


def _e_operatore(oratore: str) -> bool:
    return ORATORE_OPERATORE in (oratore or "").lower()


def _inizio_domande(paragrafi: list[dict]) -> int:
    """Da quale paragrafo cominciano le domande. `len(paragrafi)` se non ci sono.

    Si cerca l'annuncio dell'operatore, non un rapporto fisso: le parti
    preparate hanno lunghezze molto diverse, e tagliare a meta' spaccherebbe la
    guidance in due.

    Ma le parole da sole sbagliano, misurato su NVDA: il **saluto iniziale**
    dell'operatore dice gia' "there will be a question-and-answer session", e
    un marcatore ingenuo aggancia il paragrafo 1 lasciando la parte preparata
    vuota. Lo stacco vero e' il primo annuncio **dopo che qualcun altro ha
    parlato** — al saluto non ha ancora parlato nessuno.
    """
    qualcuno_ha_parlato = False
    for indice, paragrafo in enumerate(paragrafi):
        oratore = paragrafo.get("speaker") or ""
        if not _e_operatore(oratore):
            qualcuno_ha_parlato = True
            continue

        testo = (paragrafo.get("content") or "").lower()
        if qualcuno_ha_parlato and any(segno in testo for segno in SEGNI_DI_DOMANDE):
            return indice

    return len(paragrafi)


def _scambi(paragrafi: list[dict]) -> list[dict]:
    """Il botta e risposta: chi ha chiesto, cosa, e cosa gli hanno risposto.

    **A dire chi e' l'analista e' l'operatore, non un elenco di nomi.** Prima
    provavo a dedurlo — "management e' chi ha parlato nella parte preparata" — e
    su NVDA il CEO risultava analista ventotto volte, perche' in quella call
    aveva parlato solo rispondendo. L'operatore invece lo nomina ogni volta:
    "Your next question comes from the line of C.J. Muse".

    Quindi: dopo ogni intervento dell'operatore, il PRIMO che parla e'
    l'analista; tutti quelli dopo, fino all'operatore successivo, stanno
    rispondendo.
    """
    scambi: list[dict] = []
    aspetta_analista = True

    for paragrafo in paragrafi:
        oratore = paragrafo.get("speaker") or ""
        testo = (paragrafo.get("content") or "").strip()

        if _e_operatore(oratore):
            # L'operatore passa la parola: il prossimo che parla e' l'analista.
            aspetta_analista = True
            continue
        if not testo:
            continue

        if aspetta_analista:
            scambi.append({"analista": oratore, "domanda": testo, "risposte": []})
            aspetta_analista = False
        elif scambi:
            scambi[-1]["risposte"].append({"chi": oratore, "testo": testo})

    return scambi


def struttura(paragrafi) -> dict:
    """Una call divisa in parte preparata e domande, con chi ha detto cosa.

    Ritorna sempre le due meta', anche vuote: una call senza sessione di
    domande esiste, e dirlo e' diverso dal non averla trovata.
    """
    # `paragrafi or []` non si puo' scrivere: i paragrafi arrivano come array
    # numpy, e su un array il valore di verita' e' ambiguo — solleva invece di
    # decidere. Il controllo esplicito su `None` dice quello che si intende.
    elenco = [dict(p) for p in paragrafi] if paragrafi is not None else []
    if not elenco:
        return {"preparata": [], "scambi": [], "management": [],
                "caratteri": 0, "ha_domande": False}

    taglio = _inizio_domande(elenco)
    preparata = [p for p in elenco[:taglio]
                 if p.get("content") and not _e_operatore(p.get("speaker", ""))]

    return {
        "preparata": [{"chi": p["speaker"], "testo": p["content"]} for p in preparata],
        "scambi": _scambi(elenco[taglio:]),
        "management": sorted({p["speaker"] for p in preparata if p.get("speaker")}),
        "caratteri": sum(len(p.get("content") or "") for p in elenco),
        "ha_domande": taglio < len(elenco),
    }
