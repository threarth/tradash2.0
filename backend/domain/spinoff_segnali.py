"""
spinoff_segnali.py — i sei segnali di uno spin-off, e cosa dicono insieme.
# feat: matematica pura, nessuna lettura. Si prova senza rete e senza database.

Il modello causale viene dal vecchio tradash — spin-off, sottovalutazione,
inflessione fondamentale, rerating del multiplo — ma i pesi no: quelli sono
stati ricavati dal caso di riferimento, misurando **quando** ogni segnale e'
diventato visibile su SanDisk.

Il risultato di quella misura, che ribalta il modulo originale:

* il **volume** e' stato l'unico ad accendersi prima del prezzo (settembre 2025,
  +170% sui tre mesi, con ancora 13 volte il capitale davanti). Nel vecchio
  pesava il 5%, il minimo di tutti. Qui pesa 25;
* il **margine lordo** e' la descrizione piu' pulita di cosa e' successo
  (22,5% -> 78,4% in quattro trimestri) e nel vecchio non c'era affatto;
* l'accelerazione dei ricavi e dell'EPS — 30% dei pesi vecchi — e' diventata
  pubblica quando il titolo aveva gia' fatto cinque volte. Restano, perche' la
  conferma vale, ma non sono i segnali precoci che si credeva;
* la **media a 200 sedute non c'e'**: per uno spin-off di sei mesi non esiste, e
  un peso strutturalmente assente falsa tutto il resto. Al suo posto la media a
  50 e quella a 126, che a due e a sei mesi esistono.

**I pesi vengono da un caso solo, ed e' un rischio dichiarato**: un modello
tarato su SanDisk che descrive benissimo SanDisk e' sovradattamento. L'antidoto
— rigiocare il punteggio a ogni fine mese su tutti gli spin-off e guardare cosa
e' successo dopo — e' scritto nel backlog e non e' stato ancora fatto.

## Le tre guardie, trovate facendo girare il calcolo

1. **I mesi si contano dalla data dello spin, non dalla prima seduta.** Contati
   dai prezzi, NVRI dava 381 mesi e ANGI 178: quei ticker non sono nuovi, hanno
   ereditato la storia della madre. Quando la storia comincia molto PRIMA della
   separazione lo si dichiara, perche' «quotato da poco» li' non vale.
2. **I trimestri che finiscono prima della separazione non si guardano.** MFP
   dava un EPS che passava da 270,80 a 0,26: cifre per azione di una societa'
   che ancora non esisteva.
3. **Un titolo che non e' piu' scambiato non si giudica.** TWNPQ segnava zero
   ovunque e -100% su tutto: la Q finale e' il suffisso delle bancarotte, e un
   punteggio li' sopra e' un numero su un titolo che non c'e' piu'.
"""
from datetime import date, timedelta

# Quanto pesa ogni segnale. La somma fa 100, ma il punteggio si calcola sui
# soli pesi CALCOLABILI: un segnale che non si puo' misurare esce dal
# denominatore invece di valere zero. «Non lo so» e «va male» non sono lo stesso.
PESI = {"volume": 25, "margine": 20, "ricavi": 20, "eps": 15, "forza": 10, "media50": 10}

# Le soglie: pieno, mezzo, niente. Ognuna e' calibrata sul caso di riferimento.
VOLUME_PIENO, VOLUME_MEZZO = 0.50, 0.0
RICAVI_PIENO, RICAVI_MEZZO = 0.15, 0.05
MARGINE_PIENO = 0.03
FORZA_PIENO, FORZA_MEZZO = 0.10, 0.0
MEDIA50_PIENO, MEDIA50_MEZZO = 0.05, -0.05

# Le finestre, in sedute. La 126 e' mezzo anno di borsa; la 50 sono due mesi e
# mezzo, ed e' la piu' corta che dica ancora qualcosa sulla direzione.
SEDUTE_FORZA = 126
SEDUTE_MEDIA = 50

# Quanti mesi servono al confronto del volume: l'ultimo contro i tre prima.
MESI_VOLUME = 4

# Quanti trimestri servono per misurare un'accelerazione. Due, perche' con uno
# non c'e' niente da confrontare — e non e' un titolo che va male, e' un titolo
# su cui non si puo' ancora dire niente.
TRIMESTRI_MINIMI = 2

# Il ritardo con cui un trimestre si considera depositato, quando non si hanno
# le date vere. E' il ripiego: chi ha le date di deposito passi i periodi gia'
# filtrati, che e' il taglio buono.
RITARDO_DEPOSITO_GIORNI = 45

# Di quanto la storia dei prezzi puo' cominciare PRIMA della separazione senza
# che il ticker sia "vecchio": qualche giorno di scambi when-issued e' normale —
# su SNDK sono undici. Molto di piu' vuol dire che il ticker esisteva gia'.
GIORNI_STORIA_TOLLERATI = 45

# Da quante sedute senza un prezzo nuovo un titolo si considera fermo.
SEDUTE_PRIMA_DI_DIRLO_FERMO = 10

# Sotto un centesimo non si scambia davvero: il centesimo e' il passo minimo di
# quotazione sui listini americani, e un prezzo che sta sotto vive fuori dal
# mercato aperto. TWNPQ segna 0,0001 con volume zero o trecento pezzi: e' una
# bancarotta, e non e' un candidato con un punteggio basso — non e' un candidato.
PREZZO_MINIMO = 0.01

GIORNI_PER_MESE = 30.44

# Gli stati in cui puo' trovarsi un candidato. Non sono voti: dicono quali
# segnali sono accesi, ed e' la lettura che il punteggio da solo non da'.
TROPPO_PRESTO = "troppo presto"
IN_MOVIMENTO = "in movimento"
NUMERI_GIRATI = "numeri girati"
IN_RAFFREDDAMENTO = "in raffreddamento"
NIENTE_ANCORA = "niente ancora"
NON_SCAMBIATO = "non piu' scambiato"

# Quanto devono essere accesi i segnali di un gruppo perche' conti come acceso.
QUOTA_FONDAMENTALI = 0.75
QUOTA_MERCATO = 0.66


def _livello(valore, pieno, mezzo, testo):
    """Un valore contro due soglie: pieno, mezzo o niente, con la nota gia' scritta."""
    quota = 1.0 if valore >= pieno else 0.5 if valore >= mezzo else 0.0
    return {"quota": quota, "valore": round(valore, 4), "nota": testo}


def _assente(motivo):
    """Un segnale che non si puo' calcolare. Esce dal denominatore, non vale zero."""
    return {"quota": None, "valore": None, "nota": motivo}


def mesi_dallo_spin(spin: str, oggi: date | None = None) -> float:
    """Quanti mesi dalla separazione. Si conta da li', non dalla prima seduta."""
    return ((oggi or date.today()) - date.fromisoformat(spin)).days / GIORNI_PER_MESE


def storia_precedente(prima_seduta: str | None, spin: str) -> bool:
    """Il ticker aveva gia' una storia prima della separazione: non e' nuovo.

    Succede alle ridenominazioni e a chi eredita la storia della madre. Non e'
    un errore da correggere: e' un fatto da dichiarare, perche' su quel titolo
    il ragionamento «quotato da poco» non vale.
    """
    if not prima_seduta:
        return False
    scarto = date.fromisoformat(spin) - date.fromisoformat(prima_seduta)
    return scarto > timedelta(days=GIORNI_STORIA_TOLLERATI)


def _volume(barre: list[dict]) -> dict:
    """L'ultimo mese di scambi contro i tre precedenti."""
    per_mese: dict[str, list[float]] = {}
    for barra in barre:
        per_mese.setdefault(barra["data"][:7], []).append(barra.get("volume") or 0.0)

    mesi = sorted(per_mese)
    if len(mesi) < MESI_VOLUME:
        return _assente(f"meno di {MESI_VOLUME} mesi di scambi")

    medie = {m: sum(per_mese[m]) / len(per_mese[m]) for m in mesi}
    base = sum(medie[m] for m in mesi[-MESI_VOLUME:-1]) / (MESI_VOLUME - 1)
    if not base:
        return _assente("nessuno scambio nei mesi di confronto")

    variazione = medie[mesi[-1]] / base - 1
    return _livello(variazione, VOLUME_PIENO, VOLUME_MEZZO, f"{variazione:+.0%} sui 3 mesi")


def _media(barre: list[dict], sedute: int, pieno: float, mezzo: float, nome: str) -> dict:
    """Il prezzo di adesso contro la sua media su quelle sedute."""
    chiuse = [b["chiusura"] for b in barre]
    if len(chiuse) < sedute:
        return _assente(f"meno di {sedute} sedute")

    media = sum(chiuse[-sedute:]) / sedute
    if not media:
        return _assente("media a zero")

    scarto = chiuse[-1] / media - 1
    return _livello(scarto, pieno, mezzo, f"{scarto:+.0%} sulla media {nome}")


def trimestri_utili(periodi: list[str], spin: str, oggi: date | None = None) -> list[str]:
    """I trimestri che si possono guardare: dopo la separazione, e gia' depositati.

    Il primo filtro e' la guardia numero due: un trimestre che finisce PRIMA
    della separazione descrive una societa' che non esisteva ancora, e le sue
    cifre per azione sono quelle della madre.

    Il secondo e' il ripiego sul ritardo di deposito: chi ha le date vere passi
    qui i periodi gia' filtrati, che e' il taglio giusto — quello stimato e
    quello reale non sono confrontabili.
    """
    quando = oggi or date.today()
    giorno_spin = date.fromisoformat(spin)
    return [
        p for p in sorted(periodi)
        if date.fromisoformat(p) > giorno_spin
        and date.fromisoformat(p) + timedelta(days=RITARDO_DEPOSITO_GIORNI) <= quando
    ]


def _fondamentali(voci: dict, utili: list[str]) -> dict:
    """Margine, ricavi ed EPS sugli ultimi due trimestri utili."""
    if len(utili) < TRIMESTRI_MINIMI:
        manca = _assente(f"{len(utili)} trimestri dopo lo spin, ne servono "
                         f"{TRIMESTRI_MINIMI}")
        return {"margine": manca, "ricavi": dict(manca), "eps": dict(manca)}

    ora, prima = utili[-1], utili[-2]
    ricavi = voci.get("total_revenue", {})
    lordo = voci.get("gross_profit", {})
    eps = voci.get("diluted_eps", {})
    esito = {}

    misurabile = all(ricavi.get(p) for p in (ora, prima)) and all(p in lordo for p in (ora, prima))
    if misurabile:
        adesso, allora = lordo[ora] / ricavi[ora], lordo[prima] / ricavi[prima]
        esito["margine"] = _livello(adesso - allora, MARGINE_PIENO, 0.0,
                                    f"{allora:.0%} -> {adesso:.0%}")
    else:
        esito["margine"] = _assente("margine non ricavabile")

    if ora in ricavi and prima in ricavi and ricavi[prima]:
        crescita = ricavi[ora] / ricavi[prima] - 1
        esito["ricavi"] = _livello(crescita, RICAVI_PIENO, RICAVI_MEZZO, f"{crescita:+.0%} QoQ")
    else:
        esito["ricavi"] = _assente("ricavi non confrontabili")

    adesso, allora = eps.get(ora), eps.get(prima)
    if adesso is None or allora is None:
        esito["eps"] = _assente("EPS non riportato")
    else:
        # Positivo e in crescita e' pieno; positivo e basta e' mezzo. Il segno
        # conta piu' della variazione: da una perdita a una perdita minore non
        # e' un'inflessione, e' una perdita.
        quota = 1.0 if adesso > 0 and adesso > allora else 0.5 if adesso > 0 else 0.0
        esito["eps"] = {"quota": quota, "valore": round(adesso, 4),
                        "nota": f"{allora:.2f} -> {adesso:.2f}"}
    return esito


def fermo(barre: list[dict], oggi: date | None = None) -> str | None:
    """Il titolo non e' piu' scambiato? Ritorna il motivo, o None se e' vivo.

    Guardia numero tre: un punteggio su un titolo che non c'e' piu' e' un numero
    che sembra un giudizio. Si guardano due cose — quanto vale l'ultimo prezzo e
    da quanto non ne arriva uno nuovo — perche' una bancarotta si vede da
    entrambe, e a volte solo dalla prima: TWNPQ era ancora quotato ogni giorno,
    a 0,0001 dollari.
    """
    if not barre:
        return "nessun prezzo"
    if barre[-1]["chiusura"] < PREZZO_MINIMO:
        return f"prezzo sotto il centesimo ({barre[-1]['chiusura']})"

    quando = oggi or date.today()
    ultima = date.fromisoformat(barre[-1]["data"])
    # Le sedute non sono giorni: si converte con una settimana di cinque giorni
    # invece di contare un calendario di borsa che qui non serve.
    if (quando - ultima).days > SEDUTE_PRIMA_DI_DIRLO_FERMO * 7 / 5:
        return f"nessun prezzo dal {ultima.isoformat()}"
    return None


def segnali(barre: list[dict], voci: dict, spin: str, oggi: date | None = None) -> dict:
    """I sei segnali di un candidato. `barre` sono le sedute, `voci` il conto economico.

    Ogni segnale porta la sua quota (1, mezza, zero o **None**), il valore
    misurato e la nota gia' scritta per chi legge.
    """
    utili = trimestri_utili(list(voci.get("total_revenue", {})), spin, oggi)
    esito = {"volume": _volume(barre)}
    esito.update(_fondamentali(voci, utili))
    esito["forza"] = _media(barre, SEDUTE_FORZA, FORZA_PIENO, FORZA_MEZZO, "6 mesi")
    esito["media50"] = _media(barre, SEDUTE_MEDIA, MEDIA50_PIENO, MEDIA50_MEZZO, "50 sedute")
    return esito


def punteggio(esito: dict) -> dict:
    """Punti presi su punti disponibili. Il denominatore e' meta' della risposta."""
    presi = sum(PESI[k] * s["quota"] for k, s in esito.items() if s["quota"] is not None)
    disponibili = sum(PESI[k] for k, s in esito.items() if s["quota"] is not None)
    return {
        "presi": round(presi, 1),
        "disponibili": disponibili,
        "calcolabili": sum(1 for s in esito.values() if s["quota"] is not None),
        "totali": len(PESI),
        # La quota serve a ordinare, non a giudicare: due punteggi con
        # denominatori diversi non sono la stessa misura, e chi ordina lo fa
        # sapendolo perche' accanto c'e' scritto su quanti segnali.
        "quota": round(presi / disponibili, 3) if disponibili else None,
    }


def _acceso(esito: dict, quali: tuple, soglia: float) -> bool:
    """Un gruppo di segnali conta come acceso se le sue quote medie superano la soglia."""
    quote = [esito[k]["quota"] for k in quali if esito[k]["quota"] is not None]
    return bool(quote) and sum(quote) / len(quote) >= soglia


def stato(esito: dict) -> str:
    """A che punto e' il candidato. Non e' un voto: dice quali segnali sono accesi.

    E' la lettura che il punteggio da solo non da'. «In movimento» e «numeri
    girati» possono avere lo stesso numero e sono due momenti diversi: il primo
    e' dove stava SanDisk a settembre 2025, col grosso del rerating ancora
    davanti; il secondo e' novembre, quando i bilanci l'avevano confermato.
    """
    if esito["ricavi"]["quota"] is None:
        return TROPPO_PRESTO

    fondamentali = _acceso(esito, ("ricavi", "margine", "eps"), QUOTA_FONDAMENTALI)
    mercato = _acceso(esito, ("volume", "forza", "media50"), QUOTA_MERCATO)

    if fondamentali and esito["volume"]["quota"] == 0.0:
        return IN_RAFFREDDAMENTO
    if fondamentali:
        return NUMERI_GIRATI
    if mercato:
        return IN_MOVIMENTO
    return NIENTE_ANCORA
