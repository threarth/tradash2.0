"""
forward.py — il DCF, e cio' che dovrebbe essere vero perche' il prezzo abbia senso.
# feat (Blocco 9): la forward analysis, ricostruita invece che riportata.

Nel vecchio tradash la forward analysis erano 3.295 righe che non sono mai
girate: zero istantanee prodotte, zero chiamate al modello. Riportarle qui
avrebbe voluto dire riportare codice mai visto funzionare, e chiamarlo una
funzionalita'.

Qui la fonte e' il DCF che Defeatbeta calcola gia' — WACC col CAPM, crescita
dagli utili, tasso terminale dal rendimento del Tesoro a cinque anni — e il
lavoro nostro e' un altro: **rendere leggibile un numero che sembra una misura
e invece e' un'opinione sui propri ingressi.**

Per NVDA, misurato: prezzo equo 52,59 contro 217,55 di mercato. Detto cosi'
significa "sopravvalutata del 300%", che non e' informazione. Detto per intero:
quel 52,59 esce da una crescita futura fissata al 20% — il tetto che la
libreria applica — mentre i ricavi degli ultimi tre anni sono cresciuti
dell'88% all'anno; e perche' il prezzo di mercato torni servirebbe una crescita
del **55,6%** annuo per cinque anni, allo stesso tasso di sconto. Quella e' una
domanda a cui si puo' rispondere leggendo l'azienda.

## Cosa NON si propaga

La libreria mette nel risultato un campo `recommendation` con scritto "Buy" o
"Sell". Non entra nei nostri referti: e' un giudizio di una riga costruito su
un confronto fra due numeri, e messo accanto a un'analisi la fa sembrare la
sua conclusione.
"""
import json
import logging

from core import llm
from core.tipi import python_puro
from data import defeatbeta, materiale
from data.materiale import AnalisiError
from domain import dcf

logger = logging.getLogger(__name__)

# Le crescite future su cui si rifa' il conto. Partono dal tasso terminale — la
# crescita di un'economia matura — e arrivano al tetto che la libreria applica.
CRESCITE_DI_PROVA = (0.05, 0.10, 0.15, 0.20, 0.30, 0.50)

# Di quanto si muove il tasso di sconto attorno al WACC. Cinque punti: quanto
# basta a cambiare un beta discutibile.
SCARTI_DI_SCONTO = (-0.05, 0.0, 0.05)

# Quanto possono divergere il nostro conto e quello della libreria prima che sia
# un problema da dichiarare. E' un centesimo di dollaro per azione: sotto,
# e' arrotondamento; sopra, una delle due formule e' cambiata.
TOLLERANZA_PREZZO = 0.01


def _ipotesi(calcolo: dict) -> dict | None:
    """Gli ingressi del DCF, estratti dal risultato della libreria.

    **Nessun ingresso mancante diventa zero.** Prima cassa e debito ripiegavano
    su 0,0: un debito assente sarebbe stato letto come «azienda senza debiti», e
    il prezzo equo ne sarebbe uscito piu' alto senza che niente lo segnalasse.
    Su F il debito vale 163 miliardi — sbagliarlo non e' un dettaglio.

    Sui titoli provati la libreria li fornisce sempre; ma un ripiego che non si
    vede aspetta solo il caso in cui non li fornisce.
    """
    modello = calcolo.get("dcf_template") or {}
    valore = calcolo.get("dcf_value") or {}

    ingressi = {
        "base_fcf": modello.get("base_fcf"),
        "crescita_vicina": modello.get("growth_rate_1_5y"),
        "crescita_terminale": modello.get("growth_rate_terminal"),
        "sconto": modello.get("discount_rate"),
        "cassa": valore.get("cash"),
        "debito": valore.get("total_debt"),
        "azioni": valore.get("shares_outstanding"),
    }
    manca = [nome for nome, dato in ingressi.items() if dato is None]
    return None if manca else ingressi


def _controllo(nostro: float, della_libreria) -> dict:
    """Il nostro conto contro il suo: se divergono, si dice.

    Non e' zelo: la griglia di sensibilita' e la crescita implicita le
    calcoliamo noi, e valgono solo se la formula e' la stessa. Il giorno che la
    libreria cambia formula, questo campo lo dice invece di lasciarci pubblicare
    una griglia che non descrive piu' il numero accanto a cui sta.
    """
    if della_libreria is None:
        return {"concorde": None, "nota": "la libreria non ha dato un prezzo equo"}

    scarto = abs(nostro - della_libreria)
    return {
        "concorde": scarto <= TOLLERANZA_PREZZO,
        "prezzo_equo_libreria": round(della_libreria, 4),
        "nota": None if scarto <= TOLLERANZA_PREZZO else
                (f"il nostro DCF da' {nostro:.2f} e quello della libreria "
                 f"{della_libreria:.2f}: la formula e' cambiata, e la griglia "
                 f"qui sotto potrebbe non descrivere piu' quel numero"),
    }


def _storia(calcolo: dict) -> dict:
    """Come e' cresciuta davvero l'azienda: il metro per giudicare le ipotesi."""
    stime = calcolo.get("growth_estimates") or {}
    ricavi = stime.get("revenue") or {}
    utili = stime.get("eps") or {}
    return {
        "ricavi_cagr_3a": python_puro(ricavi.get("cagr_3y")),
        "ricavi_per_anno": [python_puro(v) for v in (ricavi.get("details") or [])],
        "utile_per_azione_cagr_10a": python_puro(utili.get("cagr_10y")),
        "tasso_terminale_da_tesoro_5a": python_puro(
            (stime.get("treasury") or {}).get("avg_5y")),
    }


def _nota_sulla_crescita(implicita: float | None, ingressi: dict) -> str | None:
    """Quando la crescita implicita e' il fondo della ricerca, va detto.

    La ricerca parte dalla crescita terminale: se il prezzo di mercato e' gia'
    giustificato li', il numero che torna e' il fondo della scala e non "la
    crescita che serve". Misurato su KO e su F, dove esce esattamente il tasso
    terminale — leggerlo come una previsione sarebbe leggere il punto di
    partenza dell'algoritmo.
    """
    if implicita is None:
        return ("nemmeno la crescita massima provata giustifica il prezzo di "
                "mercato: non si spiega con la sola crescita")
    # Arrotondata alle stesse quattro cifre con cui torna dalla ricerca: senza
    # questo il confronto falliva per sei milionesimi, e la nota non usciva mai.
    if implicita <= round(ingressi["crescita_terminale"], 4):
        return ("e' il minimo provato: il mercato sta sotto il prezzo equo anche "
                "assumendo la sola crescita terminale")
    return None


def misure(simbolo: str, run_id: str | None) -> dict:
    """Il DCF rifatto in proprio, con la griglia e la crescita implicita.

    Tutto deterministico: qui non c'e' nessun modello. E' la parte che si puo'
    verificare, e infatti un test la verifica sulle cifre vere di NVDA.
    """
    lettura = defeatbeta.dcf(simbolo, run_id=run_id)
    if not lettura.available:
        raise AnalisiError(f"nessun DCF per {simbolo}: {lettura.reason}")

    ingressi = _ipotesi(lettura.dato)
    if ingressi is None:
        modello = lettura.dato.get("dcf_template") or {}
        valore = lettura.dato.get("dcf_value") or {}
        assenti = [nome for nome, dove in (
            ("flusso di cassa base", modello.get("base_fcf")),
            ("crescita vicina", modello.get("growth_rate_1_5y")),
            ("crescita terminale", modello.get("growth_rate_terminal")),
            ("tasso di sconto", modello.get("discount_rate")),
            ("cassa", valore.get("cash")),
            ("debito totale", valore.get("total_debt")),
            ("azioni in circolazione", valore.get("shares_outstanding")),
        ) if dove is None]
        raise AnalisiError(
            f"il DCF di {simbolo} e' incompleto: manca {', '.join(assenti)}. "
            f"Un prezzo equo calcolato a pezzi non e' un prezzo equo, e un "
            f"ingresso dato per zero varrebbe meno di niente"
        )

    nostro = dcf.prezzo_equo(ingressi)
    if nostro is None:
        raise AnalisiError(
            f"il DCF di {simbolo} non ha soluzione: il tasso di sconto "
            f"({ingressi['sconto']:.1%}) non supera la crescita terminale "
            f"({ingressi['crescita_terminale']:.1%})"
        )

    valore = lettura.dato.get("dcf_value") or {}
    mercato = valore.get("current_price")
    sconto = ingressi["sconto"]
    implicita = None if not mercato else dcf.crescita_implicita(ingressi, mercato)

    return {
        "ipotesi": {nome: round(dato, 6) if isinstance(dato, float) else dato
                    for nome, dato in ingressi.items()},
        "prezzo_equo": round(nostro["prezzo_equo"], 2),
        "prezzo_di_mercato": python_puro(mercato),
        "scostamento_dal_mercato": (
            None if not mercato else round(dcf.scostamento(nostro["prezzo_equo"], mercato), 4)),
        "peso_del_valore_terminale": round(nostro["peso_del_valore_terminale"], 4),
        "crescita_implicita_nel_prezzo": implicita,
        "nota_sulla_crescita_implicita": _nota_sulla_crescita(implicita, ingressi),
        "sensibilita": dcf.sensibilita(
            ingressi, CRESCITE_DI_PROVA,
            tuple(sconto + scarto for scarto in SCARTI_DI_SCONTO)),
        "controllo_sulla_libreria": _controllo(nostro["prezzo_equo"],
                                               valore.get("fair_price")),
        "storia_della_crescita": _storia(lettura.dato),
        "come_e_stato_ottenuto": lettura.reason,
    }


def esegui(simbolo: str, lavoro) -> dict:
    """Calcola, poi fa leggere le ipotesi. Il numero non e' la conclusione."""
    run_id = lavoro.run_id
    conto = misure(simbolo, run_id)

    sistema = materiale.prompt("analisi_forward",
                               contesto=materiale.contesto(simbolo, run_id),
                               misure=json.dumps(conto, indent=2, ensure_ascii=False))

    risposta = llm.chiedi(fase="analisi_forward", sistema=sistema,
                          messaggio=f"Leggi il DCF di {simbolo} e le sue ipotesi.",
                          scope=simbolo, run_id=run_id)
    if risposta["rifiutata"]:
        raise AnalisiError("il modello ha rifiutato di rispondere")

    return {"contenuto": {**materiale.leggi_json(risposta["testo"]), "dcf": conto,
                          "prompt": materiale.impronta_prompt("analisi_forward")},
            "modello": risposta["modello"], "costo_usd": risposta["costo_usd"]}
