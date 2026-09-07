"""
spinoff_rigioco.py — il punteggio rigiocato all'indietro, mese per mese.
# feat: la verifica che i pesi non siano un aneddoto.

I sei pesi del rilevatore vengono da un caso solo, SanDisk, guardando quale
segnale si e' acceso per primo. Un modello tarato su un caso che descrive
benissimo quel caso non ha dimostrato niente: si chiama sovradattamento, ed e'
scritto nel backlog da quando i pesi sono nati.

Questo modulo risponde all'unica domanda che conta: **il punteggio anticipa
qualcosa, o descrive solo cio' che e' gia' successo?**

## Come

Per ogni spin-off dell'elenco, a ogni fine mese dal terzo mese dopo la
separazione in poi, si ricalcola il punteggio **con i soli dati pubblici a
quella data** — i prezzi fino a quel giorno, i trimestri gia' depositati
secondo le date VERE dell'indice dei filing — e gli si mette accanto il
rendimento dei mesi successivi.

Poi si guarda una cosa sola: le fasce di punteggio alte hanno avuto rendimenti
migliori delle basse?

## Cosa NON e'

Non e' statistica. Sono ventisette titoli, e i punti dello stesso titolo in mesi
vicini non sono osservazioni indipendenti: se un titolo corre per sei mesi, tutti
i suoi punti di quel periodo dicono la stessa cosa. Per questo il resoconto
riporta sempre **quanti titoli distinti** ci sono in ogni fascia, che e' il
numero onesto: una fascia con cento punti e due titoli e' due casi, non cento.
"""
import logging
from datetime import date

import config
from data import defeatbeta, depositi, spinoff_elenco
from domain import publication_dates, spinoff_segnali

logger = logging.getLogger(__name__)

# Quanti mesi si aspetta dopo la separazione prima di cominciare a giudicare:
# sotto i tre non c'e' nemmeno un trimestre depositato, e il punteggio direbbe
# solo «troppo presto».
MESI_MINIMI = 3

# Su quanti mesi si misura il rendimento successivo. Sei mesi e' la finestra in
# cui il rerating di uno spin-off, quando arriva, si vede.
ORIZZONTE_MESI = 6

# Le fasce in cui si raggruppano i punteggi, per punti PRESI (non per la loro
# quota: un candidato con due segnali calcolabili entrambi pieni non e' come uno
# con sei segnali su sei).
FASCE = ((0, 25), (25, 50), (50, 75), (75, 101))

GIORNI_PER_MESE = 30.44


def _mesi_dopo(quando: date, mesi: int) -> date:
    """La stessa data, tanti mesi piu' in la'. Approssimata: qui basta."""
    return date.fromordinal(quando.toordinal() + round(mesi * GIORNI_PER_MESE))


def _fini_mese(dal: date, al: date) -> list[date]:
    """Gli ultimi giorni di ogni mese nell'intervallo."""
    giorni = []
    anno, mese = dal.year, dal.month
    while date(anno, mese, 1) <= al:
        prossimo = date(anno + (mese == 12), mese % 12 + 1, 1)
        fine = date.fromordinal(prossimo.toordinal() - 1)
        if dal <= fine <= al:
            giorni.append(fine)
        anno, mese = prossimo.year, prossimo.month
    return giorni


def _prezzo_al(barre: list[dict], quando: date) -> float | None:
    """L'ultima chiusura non successiva a quella data."""
    iso = quando.isoformat()
    precedenti = [b["chiusura"] for b in barre if b["data"] <= iso]
    return precedenti[-1] if precedenti else None


def _un_titolo(riga: dict, orizzonte: int) -> list[dict]:
    """I punti (punteggio, rendimento dopo) di un candidato, uno per fine mese."""
    simbolo = riga["symbol"]
    prezzi = defeatbeta.prices(simbolo)
    if not prezzi.available:
        return []

    barre = spinoff_elenco.barre(prezzi.frame)
    if spinoff_segnali.fermo(barre):
        return []

    bilanci = defeatbeta.statements(simbolo)
    voci = spinoff_elenco._conto_economico(bilanci.frame) if bilanci.available else {}
    periodi = list(voci.get("total_revenue", {}))
    mappa = depositi.mappa(simbolo)

    spin = date.fromisoformat(riga["data"])
    primo = _mesi_dopo(spin, MESI_MINIMI)
    ultimo = _mesi_dopo(date.today(), -orizzonte)

    punti = []
    for fine in _fini_mese(primo, ultimo):
        allora = [b for b in barre if b["data"] <= fine.isoformat()]
        dopo = _prezzo_al(barre, _mesi_dopo(fine, orizzonte))
        adesso = _prezzo_al(barre, fine)
        if not allora or not adesso or not dopo:
            continue

        pubblici = [p for p in periodi
                    if publication_dates.was_public(mappa, p, fine.isoformat())]
        esito = spinoff_segnali.segnali(allora, voci, riga["data"],
                                        oggi=fine, pubblici=pubblici)
        conto = spinoff_segnali.punteggio(esito)
        punti.append({
            "symbol": simbolo,
            "quando": fine.isoformat(),
            "presi": conto["presi"],
            "disponibili": conto["disponibili"],
            "calcolabili": conto["calcolabili"],
            "stato": spinoff_segnali.stato(esito),
            "rendimento": round(dopo / adesso - 1, 4),
        })
    return punti


def _mediana(valori: list[float]) -> float | None:
    if not valori:
        return None
    ordinati = sorted(valori)
    meta = len(ordinati) // 2
    if len(ordinati) % 2:
        return ordinati[meta]
    return (ordinati[meta - 1] + ordinati[meta]) / 2


def per_fasce(punti: list[dict]) -> list[dict]:
    """I punti raggruppati per fascia di punteggio, con quanti TITOLI ci sono.

    Il numero di titoli distinti conta piu' del numero di punti: se un titolo
    corre per sei mesi, tutti i suoi punti di quel periodo dicono la stessa
    cosa, e contarli come sei osservazioni sarebbe contare sei volte un caso.
    """
    fasce = []
    for basso, alto in FASCE:
        dentro = [p for p in punti if basso <= p["presi"] < alto]
        rendimenti = [p["rendimento"] for p in dentro]
        fasce.append({
            "da": basso, "a": alto,
            "punti": len(dentro),
            "titoli": len({p["symbol"] for p in dentro}),
            "mediana": _mediana(rendimenti),
            "media": round(sum(rendimenti) / len(rendimenti), 4) if rendimenti else None,
            "quanti_in_guadagno": sum(1 for r in rendimenti if r > 0),
        })
    return fasce


def rigioca(orizzonte: int = ORIZZONTE_MESI) -> dict:
    """Rigioca il punteggio su tutto l'elenco e ritorna i punti e le fasce."""
    righe = spinoff_elenco.elenco()["righe"]
    if not righe:
        raise spinoff_elenco.SpinoffError(
            "non c'e' nessun elenco da rigiocare: scaricalo prima"
        )

    punti: list[dict] = []
    saltati = []
    for riga in righe:
        try:
            trovati = _un_titolo(riga, orizzonte)
        except Exception as problema:
            logger.warning("[RIGIOCO] %s saltato: %s", riga["symbol"], problema)
            saltati.append({"symbol": riga["symbol"], "motivo": str(problema)[:60]})
            continue
        if not trovati:
            saltati.append({"symbol": riga["symbol"],
                            "motivo": "niente da rigiocare: troppo giovane o senza prezzi"})
        punti.extend(trovati)

    return {"orizzonte_mesi": orizzonte, "punti": punti, "saltati": saltati,
            "fasce": per_fasce(punti),
            "titoli": len({p["symbol"] for p in punti}),
            "pesi": dict(spinoff_segnali.PESI),
            "versione_file": config.SPINOFF_FILE_VERSION}
