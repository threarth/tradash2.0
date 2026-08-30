"""
dcf.py — il flusso di cassa scontato, e quanto dipende da cio' che si assume.
# feat (Blocco 9): la forward analysis, ricostruita sul DCF di Defeatbeta.

Nel vecchio tradash la forward analysis erano 3.295 righe che **non sono mai
girate**: zero istantanee, zero chiamate al modello. Riportarle qui avrebbe
voluto dire riportare codice mai visto funzionare.

Defeatbeta un DCF ce l'ha gia', completo di WACC e proiezioni, e questo modulo
lo **rifa' in proprio** per una ragione sola: poterlo rifare con ipotesi
diverse. Un DCF produce un numero che sembra una misura e invece e' un'opinione
sui suoi ingressi — per NVDA, misurato: prezzo equo 52,59 dollari contro 217,55
di mercato, e quel 52,59 esce da una crescita futura fissata al 20% quando i
ricavi degli ultimi tre anni sono cresciuti dell'88% all'anno.

Il numero da solo direbbe "sopravvalutata del 300%". Con accanto la griglia di
sensibilita' dice qualcosa di piu' onesto: **a quali ipotesi il prezzo di
mercato sarebbe giustificato**, che e' la domanda vera.

## La formula, che e' quella della libreria

Anni 1-5 crescono al tasso vicino; gli anni 6-10 scendono in linea retta fino
al tasso terminale; al decimo anno si aggiunge il valore terminale con la
formula di Gordon. Tutto si sconta al tasso di sconto. L'anno zero non si
sconta e non si somma: e' il punto di partenza, non un flusso futuro.

Riprodurla invece di leggere solo il risultato serve a due cose: la griglia, e
sapere che il nostro conto e quello della libreria danno lo stesso numero — un
test lo verifica sulle cifre vere di NVDA.
"""

ANNI_VICINI = 5
ANNI_TOTALI = 10


def flussi(base_fcf: float, crescita_vicina: float, crescita_terminale: float,
           anni: int = ANNI_TOTALI) -> list[float]:
    """I flussi di cassa proiettati, dall'anno 1 all'ultimo.

    Dal sesto anno il tasso scende per gradi uguali dal vicino al terminale: e'
    l'interpolazione lineare della libreria, non una scelta nostra.
    """
    passo = (crescita_vicina - crescita_terminale) / ANNI_VICINI
    proiettati, corrente = [], base_fcf

    for anno in range(1, anni + 1):
        oltre = max(0, anno - ANNI_VICINI)
        corrente = corrente * (1 + crescita_vicina - oltre * passo)
        proiettati.append(corrente)

    return proiettati


def valore_terminale(ultimo_flusso: float, crescita_terminale: float,
                     sconto: float) -> float | None:
    """Il valore di tutto cio' che viene dopo l'ultimo anno proiettato.

    `None` se il tasso di sconto non supera la crescita terminale: la formula di
    Gordon li' divide per zero o per un numero negativo, e il risultato non
    sarebbe un valore alto — sarebbe un valore senza senso.
    """
    if sconto <= crescita_terminale:
        return None
    return ultimo_flusso * (1 + crescita_terminale) / (sconto - crescita_terminale)


def prezzo_equo(ipotesi: dict) -> dict | None:
    """Il prezzo per azione che questo DCF implica, coi pezzi da cui esce.

    `ipotesi` porta i sette ingressi: base_fcf, crescita_vicina,
    crescita_terminale, sconto, cassa, debito, azioni. Stanno in un dizionario
    e non in sette parametri perche' la griglia di sensibilita' ne cambia uno
    per volta lasciando gli altri dove sono, e cosi' si scrive una riga.

    `None` quando manca un ingresso indispensabile o quando la formula non ha
    soluzione: meglio niente che un prezzo costruito su una divisione storta.
    """
    azioni = ipotesi.get("azioni")
    base_fcf, sconto = ipotesi.get("base_fcf"), ipotesi.get("sconto")
    terminale = ipotesi["crescita_terminale"]
    if not azioni or base_fcf is None or sconto is None:
        return None

    proiettati = flussi(base_fcf, ipotesi["crescita_vicina"], terminale)
    coda = valore_terminale(proiettati[-1], terminale, sconto)
    if coda is None:
        return None

    scontati = [flusso / (1 + sconto) ** anno
                for anno, flusso in enumerate(proiettati, start=1)]
    coda_scontata = coda / (1 + sconto) ** len(proiettati)
    impresa = sum(scontati) + coda_scontata
    capitale = impresa + ipotesi.get("cassa", 0.0) - ipotesi.get("debito", 0.0)

    return {
        "valore_impresa": impresa,
        "valore_terminale": coda,
        "peso_del_valore_terminale": coda_scontata / impresa,
        "capitale_netto": capitale,
        "prezzo_equo": capitale / azioni,
        "flussi_proiettati": proiettati,
    }


def scostamento(prezzo_equo_calcolato: float, prezzo_di_mercato: float) -> float | None:
    """Quanto il mercato sta sopra o sotto il prezzo equo, in frazione di mercato.

    Si divide per il PREZZO DI MERCATO e non per il prezzo equo. La libreria fa
    il contrario, e il suo -3,14 per NVDA non significa "sopravvalutata del
    314%": significa che il prezzo equo e' un quarto del mercato. Diviso per il
    mercato, viene -0,76 — che si legge come "il DCF vede tre quarti di prezzo
    in meno", ed e' la stessa cosa detta in modo non fraintendibile.
    """
    if not prezzo_di_mercato:
        return None
    return (prezzo_equo_calcolato - prezzo_di_mercato) / prezzo_di_mercato


def sensibilita(ipotesi: dict, crescite: tuple, sconti: tuple) -> list[dict]:
    """Il prezzo equo con altre ipotesi: la griglia che rende leggibile il numero.

    Un DCF produce un numero che sembra una misura e invece e' un'opinione sui
    suoi ingressi. La griglia mostra l'opinione insieme al numero.
    """
    griglia = []
    for crescita in crescite:
        for sconto in sconti:
            calcolo = prezzo_equo({**ipotesi, "crescita_vicina": crescita,
                                   "sconto": sconto})
            griglia.append({
                "crescita_vicina": round(crescita, 4),
                "sconto": round(sconto, 4),
                "prezzo_equo": None if calcolo is None else round(calcolo["prezzo_equo"], 2),
            })
    return griglia


def crescita_implicita(ipotesi: dict, prezzo_di_mercato: float,
                       massimo: float = 1.0, passo: float = 0.005) -> float | None:
    """La crescita che renderebbe giusto il prezzo di mercato, a parita' di resto.

    E' la domanda utile davanti a un titolo che il DCF dice caro: non "quanto e'
    caro", ma "cosa dovrebbe fare l'azienda perche' non lo sia". Si cerca per
    tentativi invece che invertendo la formula, perche' la formula non e'
    invertibile in forma chiusa e il passo lo scegliamo noi.

    `None` se nemmeno la crescita massima basta: e' una risposta, e dice che il
    prezzo non si spiega con la sola crescita.
    """
    if not prezzo_di_mercato:
        return None

    crescita = ipotesi["crescita_terminale"]
    while crescita <= massimo:
        calcolo = prezzo_equo({**ipotesi, "crescita_vicina": crescita})
        if calcolo is not None and calcolo["prezzo_equo"] >= prezzo_di_mercato:
            return round(crescita, 4)
        crescita += passo

    return None
