"""
salute.py — le figure di bilancio e i rapporti di solidita', senza un punteggio.
# feat (Blocco 8, ripreso): la sezione "salute" della pagina titolo del vecchio.

**Qui non c'e' nessun voto, ed e' una decisione presa gia' nel vecchio sistema
dopo averne subito le conseguenze.** Quella sezione produceva un Health Score
0-100 con etichetta OTTIMA/BUONA/MODERATA/DEBOLE/CRITICA, calcolato da quattro
sotto-punteggi con pesi propri. Era un **secondo verdetto** sulla stessa
azienda, parallelo a quello della qualita' fondamentale e non riconciliato con
esso: due numeri diversi, nessuno dei due derivabile dall'altro, e chi leggeva
doveva scegliere a quale credere.

Restano i dati, che sono cio' che questa sezione deve mostrare. Il giudizio
appartiene all'analisi fondamentale, che ne ha uno solo.

## I quattro rapporti, e cosa vogliono dire

- **Copertura degli interessi** = EBIT / oneri finanziari. Quante volte il
  reddito operativo copre gli interessi. Sotto 1 l'azienda non li paga col
  reddito.
- **Debito su patrimonio** = debito totale / patrimonio netto. Quanto del
  capitale e' preso a prestito.
- **Copertura degli attivi** = attivo totale / passivo totale. Sopra 1 gli
  attivi coprono i debiti.
- **Debito netto su EBITDA** = (debito - cassa) / EBITDA. Quanti anni di margine
  operativo lordo servirebbero per ripagare il debito netto.

Un rapporto che non si puo' calcolare vale `None` e porta il motivo: un
denominatore a zero non fa un rapporto infinito, fa un rapporto che non esiste.

## Il ponte fra utile e cassa

L'utile e la cassa non sono la stessa cosa e la differenza si spiega voce per
voce: ammortamenti (che non escono), compensi in azioni (che non escono),
circolante (che entra o esce senza passare dal conto economico), e un residuo
che tiene dentro investimenti e imposte. La conversione — cassa su utile — dice
quanto dell'utile dichiarato diventa denaro.
"""
from domain.segnali import serie

# Le voci dei prospetti, coi nomi che usa Defeatbeta.
VOCE_PATRIMONIO = "stockholders_equity"
VOCE_DEBITO = "total_debt"
VOCE_CASSA = "cash_cash_equivalents_and_short_term_investments"
VOCE_CASSA_STRETTA = "cash_and_cash_equivalents"
VOCE_ATTIVO = "total_assets"
VOCE_PASSIVO = "total_liabilities_net_minority_interest"
VOCE_EBIT = "ebit"
VOCE_EBITDA = "ebitda"
VOCE_ONERI = "interest_expense"
VOCE_UTILE = "net_income"
VOCE_CASSA_LIBERA = "free_cash_flow"
VOCE_AMMORTAMENTI = "depreciation_and_amortization"
VOCE_AZIONI_AI_DIPENDENTI = "stock_based_compensation"
VOCE_CIRCOLANTE = "change_in_working_capital"

TRIMESTRI_ANNO = 4

# Quanti trimestri si mostrano nel ponte fra utile e cassa e nella storia del
# debito. Otto sono due anni: abbastanza per vedere una direzione, non tanti da
# trasformare una tabella in un archivio.
TRIMESTRI_MOSTRATI = 8


# Quanti trimestri entrano nei GRAFICI delle metriche. Piu' della tabella: una
# tabella di venti righe non si legge, una linea di venti punti si'.
TRIMESTRI_NEL_GRAFICO = 20


def _ultimo(prospetto: dict, voce: str) -> float | None:
    valori = serie(prospetto, voce)
    return valori[-1][1] if valori else None


def _ttm(prospetto: dict, voce: str) -> float | None:
    """La somma degli ultimi quattro trimestri. `None` se non ce ne sono quattro."""
    valori = [v for _, v in serie(prospetto, voce)]
    return sum(valori[-TRIMESTRI_ANNO:]) if len(valori) >= TRIMESTRI_ANNO else None


def _storia(prospetto: dict, voce: str) -> dict:
    """Tutti i valori di una voce, per periodo."""
    return dict(serie(prospetto, voce))


def _storia_ttm(prospetto: dict, voce: str) -> dict:
    """La somma mobile dei quattro trimestri che FINISCONO in ognuno.

    Non e' la stessa cosa del valore del trimestre: EBIT, EBITDA e oneri
    finanziari si guardano sempre su dodici mesi, perche' un trimestre solo li
    fa sembrare stagionali. Il primo periodo con un valore e' il quarto: prima
    non ci sono quattro trimestri da sommare, e il punto non esiste invece di
    valere una somma parziale.
    """
    valori = serie(prospetto, voce)
    return {
        periodo: sum(v for _, v in valori[indice - TRIMESTRI_ANNO + 1:indice + 1])
        for indice, (periodo, _) in enumerate(valori)
        if indice >= TRIMESTRI_ANNO - 1
    }


def _rapporto(numeratore: float | None, denominatore: float | None,
              perche: str) -> dict:
    """Un rapporto col suo motivo quando non si puo' fare.

    Un denominatore a zero non da' un rapporto infinito: da' un rapporto che non
    esiste, e dirlo e' diverso da mostrare un numero enorme.
    """
    if numeratore is None or denominatore is None:
        return {"valore": None, "reason": f"manca {perche}"}
    if denominatore == 0:
        return {"valore": None, "reason": f"{perche} e' zero: il rapporto non esiste"}
    return {"valore": round(numeratore / denominatore, 4), "reason": None}


def figure(conto: dict, patrimoniale: dict) -> dict:
    """Le grandezze di bilancio da cui esce tutto il resto."""
    cassa = _ultimo(patrimoniale, VOCE_CASSA)
    if cassa is None:
        cassa = _ultimo(patrimoniale, VOCE_CASSA_STRETTA)
    debito = _ultimo(patrimoniale, VOCE_DEBITO)

    return {
        "patrimonio_netto": _ultimo(patrimoniale, VOCE_PATRIMONIO),
        "debito_totale": debito,
        "cassa": cassa,
        "debito_netto": (None if debito is None or cassa is None else debito - cassa),
        "attivo_totale": _ultimo(patrimoniale, VOCE_ATTIVO),
        "passivo_totale": _ultimo(patrimoniale, VOCE_PASSIVO),
        "ebit_ttm": _ttm(conto, VOCE_EBIT),
        "ebitda_ttm": _ttm(conto, VOCE_EBITDA),
        "oneri_finanziari_ttm": _ttm(conto, VOCE_ONERI),
    }


def rapporti(valori: dict) -> dict:
    """I quattro rapporti di solidita', ognuno col suo motivo se non si fa."""
    return {
        "copertura_interessi": _rapporto(
            valori["ebit_ttm"], valori["oneri_finanziari_ttm"], "gli oneri finanziari"),
        "debito_su_patrimonio": _rapporto(
            valori["debito_totale"], valori["patrimonio_netto"], "il patrimonio netto"),
        "copertura_attivi": _rapporto(
            valori["attivo_totale"], valori["passivo_totale"], "il passivo totale"),
        "debito_netto_su_ebitda": _rapporto(
            valori["debito_netto"], valori["ebitda_ttm"], "l'EBITDA"),
    }


def figure_storiche(conto: dict, patrimoniale: dict) -> dict:
    """Le stesse figure, ma trimestre per trimestre, per poterle disegnare.

    `figure()` da' l'ultimo valore, che e' cio' che serve a una tabella. Un
    grafico ha bisogno della storia, e finora non c'era: la pagina poteva
    mostrare il debito di adesso ma non come ci era arrivato.

    La cassa ha due voci possibili e si prende la piu' completa disponibile,
    come in `figure()`: cambiare fonte a meta' serie farebbe un gradino che
    sembra un fatto aziendale e non lo e'.
    """
    cassa = _storia(patrimoniale, VOCE_CASSA) or _storia(patrimoniale, VOCE_CASSA_STRETTA)
    debito = _storia(patrimoniale, VOCE_DEBITO)

    storie = {
        "patrimonio_netto": _storia(patrimoniale, VOCE_PATRIMONIO),
        "debito_totale": debito,
        "cassa": cassa,
        "debito_netto": {periodo: debito[periodo] - cassa[periodo]
                         for periodo in sorted(set(debito) & set(cassa))},
        "attivo_totale": _storia(patrimoniale, VOCE_ATTIVO),
        "passivo_totale": _storia(patrimoniale, VOCE_PASSIVO),
        "ebit_ttm": _storia_ttm(conto, VOCE_EBIT),
        "ebitda_ttm": _storia_ttm(conto, VOCE_EBITDA),
        "oneri_finanziari_ttm": _storia_ttm(conto, VOCE_ONERI),
    }
    return {nome: _punti(valori) for nome, valori in storie.items()}


def _punti(valori: dict) -> list[dict]:
    """Da `{periodo: valore}` alla lista ordinata che il grafico si aspetta."""
    return [{"periodo": periodo, "valore": valori[periodo]}
            for periodo in sorted(valori)[-TRIMESTRI_NEL_GRAFICO:]]


def rapporti_storici(storiche: dict) -> dict:
    """I quattro rapporti, trimestre per trimestre.

    Si calcolano dalle figure storiche e non dai prospetti: un rapporto e' il
    quoziente di due figure, e ricavarlo altrove vorrebbe dire due strade per
    lo stesso numero, cioe' due modi di farlo diverso.

    Un periodo in cui manca uno dei due lati, o il denominatore e' zero, **non
    produce un punto**. Un buco nella linea dice «qui non si sapeva»; uno zero
    direbbe una cosa falsa.
    """
    def dividi(sopra: str, sotto: str) -> list[dict]:
        numeratori = {p["periodo"]: p["valore"] for p in storiche[sopra]}
        denominatori = {p["periodo"]: p["valore"] for p in storiche[sotto]}
        return [
            {"periodo": periodo,
             "valore": round(numeratori[periodo] / denominatori[periodo], 4)}
            for periodo in sorted(set(numeratori) & set(denominatori))
            if denominatori[periodo]
        ]

    return {
        "copertura_interessi": dividi("ebit_ttm", "oneri_finanziari_ttm"),
        "debito_su_patrimonio": dividi("debito_totale", "patrimonio_netto"),
        "copertura_attivi": dividi("attivo_totale", "passivo_totale"),
        "debito_netto_su_ebitda": dividi("debito_netto", "ebitda_ttm"),
    }


def storia_del_debito(patrimoniale: dict) -> list[dict]:
    """Debito, patrimonio e loro rapporto, trimestre per trimestre.

    Il rapporto da solo non basta: puo' scendere perche' il debito cala o perche'
    il patrimonio sale, e sono due storie diverse. Per questo ci sono tutti e tre.
    """
    debiti = dict(serie(patrimoniale, VOCE_DEBITO))
    patrimoni = dict(serie(patrimoniale, VOCE_PATRIMONIO))
    periodi = sorted(set(debiti) & set(patrimoni))[-TRIMESTRI_MOSTRATI:]

    return [{
        "periodo": periodo,
        "debito": debiti[periodo],
        "patrimonio": patrimoni[periodo],
        "debito_su_patrimonio": _rapporto(debiti[periodo], patrimoni[periodo],
                                          "il patrimonio netto")["valore"],
    } for periodo in periodi]


def dall_utile_alla_cassa(conto: dict, conto_cassa: dict) -> list[dict]:
    """Il ponte fra utile e cassa, trimestre per trimestre.

    Il residuo tiene dentro investimenti, imposte e tutto cio' che non e' nelle
    tre voci esplicite: si calcola per differenza e si chiama «altro» invece di
    sparire, perche' se e' grande e' proprio quello da guardare.
    """
    utili = dict(serie(conto, VOCE_UTILE))
    casse = dict(serie(conto_cassa, VOCE_CASSA_LIBERA))
    ammortamenti = dict(serie(conto_cassa, VOCE_AMMORTAMENTI))
    azioni = dict(serie(conto_cassa, VOCE_AZIONI_AI_DIPENDENTI))
    circolante = dict(serie(conto_cassa, VOCE_CIRCOLANTE))

    periodi = sorted(set(utili) & set(casse))[-TRIMESTRI_MOSTRATI:]
    ponte = []
    for periodo in periodi:
        utile, cassa = utili[periodo], casse[periodo]
        pezzi = {
            "ammortamenti": ammortamenti.get(periodo),
            "azioni_ai_dipendenti": azioni.get(periodo),
            "circolante": circolante.get(periodo),
        }
        spiegato = sum(v for v in pezzi.values() if v is not None)
        ponte.append({
            "periodo": periodo, "utile": utile, **pezzi,
            "altro": round(cassa - utile - spiegato, 2),
            "cassa_libera": cassa,
            "conversione": (round(cassa / utile, 4) if utile and utile > 0 else None),
        })
    return ponte


def quadro(tabelle: dict) -> dict:
    """Tutta la sezione: figure, rapporti, storia del debito, ponte verso la cassa."""
    conto = tabelle.get("income_statement", {})
    patrimoniale = tabelle.get("balance_sheet", {})
    conto_cassa = tabelle.get("cash_flow", {})

    valori = figure(conto, patrimoniale)
    mancanti = [nome for nome, valore in valori.items() if valore is None]
    storiche = figure_storiche(conto, patrimoniale)

    return {
        "figure": valori,
        "rapporti": rapporti(valori),
        # Le stesse grandezze nel tempo: la tabella mostra dov'e' adesso, il
        # grafico come ci e' arrivato. Sono due domande diverse sullo stesso dato.
        "figure_storiche": storiche,
        "rapporti_storici": rapporti_storici(storiche),
        "storia_del_debito": storia_del_debito(patrimoniale),
        "dall_utile_alla_cassa": dall_utile_alla_cassa(conto, conto_cassa),
        "figure_mancanti": mancanti,
        "nota": ("Nessun punteggio di sintesi: qui ci sono i dati. Il giudizio "
                 "sulla qualita' economica lo da' l'analisi fondamentale, ed e' "
                 "uno solo."),
    }
