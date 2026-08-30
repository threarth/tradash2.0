"""
ricostruzione.py — cosa si poteva sapere a una certa data, e cosa e' successo dopo.
# feat (Blocco 7, chiuso col Blocco 8): il confronto point-in-time.

Una lettura scritta oggi non si puo' giudicare oggi: dice cosa sembra adesso, e
se aveva ragione si sapra' fra un anno. Ricostruirla a una data passata invece
si puo' giudicare subito, perche' il dopo e' gia' successo.

Il valore di questa pagina sta tutto in una condizione: **cio' che si mostra
come "quello che si sapeva" deve essere davvero quello che si sapeva.** Bastano
un paio di sedute in piu' nel taglio perche' il confronto diventi una
dimostrazione che il metodo funziona, e sarebbe una dimostrazione falsa.

Per questo il taglio dei prezzi e' rigido — solo le sedute con data **minore o
uguale** — e quello dei bilanci passa dalle date di deposito, non dalla fine
del periodo: un trimestre chiuso il 31 gennaio diventa pubblico a fine
febbraio, e usarlo prima e' guardare il futuro.

Qui dentro non c'e' nessuna lettura I/O: prezzi e date arrivano gia' letti.
"""

# Gli orizzonti a cui si guarda cosa e' successo, in giorni di calendario. Sono
# di calendario e non di borsa perche' "tre mesi dopo" e' una domanda che ci si
# pone in giorni, non in sedute.
ORIZZONTI_IN_GIORNI = (30, 90, 180, 365)

# Quanto ci si puo' allontanare dalla data cercata prima di dire che quella
# seduta non c'e'. Una settimana copre feste e sospensioni; oltre, il numero
# risponderebbe a una domanda diversa da quella fatta.
TOLLERANZA_IN_GIORNI = 7

GIORNI_PER_ANNO = 365.0


def _in_giorni(prima: str, dopo: str) -> int:
    """Quanti giorni fra due date ISO, senza importare nulla di pesante."""
    from datetime import date  # noqa: PLC0415

    return (date.fromisoformat(dopo[:10]) - date.fromisoformat(prima[:10])).days


def dividi(barre: list[dict], quando: str) -> tuple[list[dict], list[dict]]:
    """Le sedute fino a quella data, e quelle dopo. Il confine e' incluso a sinistra.

    `barre` sono dizionari con almeno `data` e `close`, in ordine di data.
    """
    prima = [b for b in barre if str(b["data"])[:10] <= quando]
    dopo = [b for b in barre if str(b["data"])[:10] > quando]
    return prima, dopo


def _seduta_piu_vicina(dopo: list[dict], partenza: str, giorni: int) -> dict | None:
    """La seduta piu' vicina a `partenza + giorni`, se cade nella tolleranza."""
    candidate = [(abs(_in_giorni(partenza, str(b["data"])) - giorni), b) for b in dopo]
    if not candidate:
        return None
    distanza, barra = min(candidate, key=lambda coppia: coppia[0])
    return barra if distanza <= TOLLERANZA_IN_GIORNI else None


def cosa_e_successo(prezzo_di_partenza: float, dopo: list[dict],
                    quando: str) -> dict:
    """Come e' andata dopo quella data: rendimenti, minimo, massimo.

    Un orizzonte che non e' ancora maturato vale `None` e non zero: "non si sa
    ancora" e "non si e' mosso" sono letture opposte.
    """
    if not prezzo_di_partenza or not dopo:
        return {"sedute_dopo": len(dopo), "rendimenti": {},
                "discesa_massima": None, "salita_massima": None,
                "motivo": "nessuna seduta dopo la data scelta: il confronto non "
                          "e' ancora possibile"}

    rendimenti = {}
    for giorni in ORIZZONTI_IN_GIORNI:
        barra = _seduta_piu_vicina(dopo, quando, giorni)
        rendimenti[f"{giorni}g"] = None if barra is None else round(
            barra["close"] / prezzo_di_partenza - 1, 4)

    chiusure = [b["close"] for b in dopo]
    return {
        "sedute_dopo": len(dopo),
        "ultima_data": str(dopo[-1]["data"])[:10],
        "rendimenti": rendimenti,
        "rendimento_a_oggi": round(chiusure[-1] / prezzo_di_partenza - 1, 4),
        "discesa_massima": round(min(chiusure) / prezzo_di_partenza - 1, 4),
        "salita_massima": round(max(chiusure) / prezzo_di_partenza - 1, 4),
        "motivo": None,
    }


def orizzonti_maturati(quando: str, ultima_data: str) -> list[str]:
    """Quali orizzonti hanno avuto il tempo di maturare, e quali no.

    Serve a distinguere un rendimento che manca perche' il mercato era chiuso da
    uno che manca perche' quel giorno non e' ancora arrivato: il primo e' un
    buco, il secondo e' il futuro.

    **Con la stessa tolleranza con cui si cerca la seduta**, e non e' un
    dettaglio: visto dal vivo su NVDA al 2025-08-29, l'ultimo prezzo distava 364
    giorni — il rendimento a un anno veniva calcolato (la seduta cadeva nella
    tolleranza) ma l'orizzonte risultava non maturato. Due campi della stessa
    risposta che si contraddicono sono peggio di entrambe le letture.
    """
    passati = _in_giorni(quando, ultima_data)
    return [f"{giorni}g" for giorni in ORIZZONTI_IN_GIORNI
            if giorni - TOLLERANZA_IN_GIORNI <= passati]
