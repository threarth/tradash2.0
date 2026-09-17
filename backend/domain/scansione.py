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

# Le stesse finestre quando i punti sono MESI invece che sedute, per il rigioco:
# li' la storia si legge da `universe_prezzi_mensili`, un punto per mese, perche'
# rileggere i prezzi giornalieri di dodicimila titoli per ogni mese sarebbe un
# lavoro da ore invece che da secondi.
#
# I 200 e i 50 giorni diventano 10 e 2 mesi (~21 sedute per mese). NON sono lo
# stesso numero della versione giornaliera, ed e' scritto: una media a 200
# sedute calcolata su dieci chiusure di fine mese e' una media diversa, non una
# sua approssimazione. Chi legge un rigioco lo deve sapere.
FINESTRE_MENSILI = {"breve": 1, "media": 3, "lunga": 12, "media_50": 2, "media_200": 10}


def finestre_in_sedute() -> dict:
    """Le finestre della scansione dal vivo, dove un punto e' una seduta."""
    return {"breve": FINESTRA_BREVE, "media": FINESTRA_MEDIA, "lunga": FINESTRA_LUNGA,
            "media_50": 50, "media_200": 200}

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


def misure(chiusure: list[float], volumi: list[float] | None = None,
           finestre: dict | None = None) -> dict:
    """Tutto quello che si puo' dire di un titolo guardando solo i suoi prezzi.

    Le misure che non si possono calcolare valgono `None` e non zero: un titolo
    quotato da tre mesi non ha una variazione a un anno pari a zero, non ce
    l'ha affatto.

    `finestre` esiste perche' questa stessa matematica serve su due serie
    diverse: le sedute, per lo scanner dal vivo, e i mesi, per il rigioco. Due
    implementazioni della stessa media sarebbero due posti dove sbagliarla.
    """
    finestre = finestre or finestre_in_sedute()
    lunga, corta = finestre["media_200"], finestre["media_50"]
    return {
        "ultimo_prezzo": chiusure[-1] if chiusure else None,
        "sedute": len(chiusure),
        "variazione_1m": _variazione(chiusure, finestre["breve"]),
        "variazione_3m": _variazione(chiusure, finestre["media"]),
        "variazione_1a": _variazione(chiusure, finestre["lunga"]),
        "media_50": _media(chiusure[-corta:]) if len(chiusure) >= corta else None,
        "media_200": _media(chiusure[-lunga:]) if len(chiusure) >= lunga else None,
        "volume_medio": _media(volumi[-finestre["breve"]:]) if volumi else None,
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
    vuote = {"ricavi_qoq": None, "ricavi_yoy": None, "ricavi_accelerazione": None,
             "margine": None, "margine_variazione": None, "eps": None,
             "trimestri": len(utili)}
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

    misurate["ricavi_accelerazione"] = _accelerazione(ricavi, utili)
    return misurate


def _accelerazione(ricavi: dict, utili: list[str]) -> float | None:
    """La crescita anno su anno di ADESSO meno quella del trimestre prima.

    E' la derivata seconda: non «quanto cresce» ma «sta crescendo di piu' o di
    meno di prima». Un titolo che passa dal +10% al +25% accelera; uno che passa
    dal +40% al +30% cresce tanto e sta decelerando, e i due si assomigliano
    guardando solo l'ultimo numero.

    Servono SEI trimestri pubblici: l'anno su anno di adesso ne vuole cinque, e
    quello del trimestre prima ne vuole uno in piu' indietro. E' molto — sotto
    quella soglia la misura vale `None`, che non e' zero.

    Entrambi i confronti sono anno su anno, cioe' fra trimestri omologhi: farne
    uno trimestre su trimestre mescolerebbe l'accelerazione con la stagionalita',
    che e' l'errore gia' misurato sul segnale dei ricavi.
    """
    if len(utili) < TRIMESTRI_PER_ANNO + 2:
        return None

    ora, prima = utili[-1], utili[-2]
    anno_fa_ora = utili[-(TRIMESTRI_PER_ANNO + 1)]
    anno_fa_prima = utili[-(TRIMESTRI_PER_ANNO + 2)]

    if not (ricavi.get(anno_fa_ora) and ricavi.get(anno_fa_prima)):
        return None
    if ora not in ricavi or prima not in ricavi:
        return None

    adesso = ricavi[ora] / ricavi[anno_fa_ora] - 1
    allora = ricavi[prima] / ricavi[anno_fa_prima] - 1
    return adesso - allora


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
    # La derivata seconda dei ricavi: sta accelerando o decelerando? Un titolo
    # che passa dal +10% al +25% e uno che passa dal +40% al +30% hanno
    # entrambi una crescita alta, e sono due storie opposte.
    "ricavi_accelerazione_minima": (
        lambda m: m["fondamentali"]["ricavi_accelerazione"], True,
        "crescita dei ricavi in accelerazione di almeno {soglia:.0%} rispetto al "
        "trimestre prima (adesso {valore:+.1%})",
    ),
    # Le azioni che CALANO: un buyback in corso. La soglia e' un MASSIMO, quindi
    # `azioni_variazione_massima: -0.02` chiede almeno il 2% di riacquisto in un
    # anno; a zero chiede soltanto che non stiano diluendo.
    "azioni_variazione_massima": (
        lambda m: m["azioni"]["variazione_1a"] if m.get("azioni") else None, False,
        "azioni in circolazione variate non piu' di {soglia:+.1%} in un anno "
        "(adesso {valore:+.1%})",
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


# --- I preset: combinazioni a cui e' gia' stata fatta la domanda ------------
#
# Qui c'e' solo la DEFINIZIONE: come si chiama, quali criteri, qual e' l'idea, e
# cosa quella misura non potra' comunque dire. Il verdetto — chi vince, di
# quanto, su quanti mesi — **non sta qui**: lo produce `manage.py preset`
# rigiocandoli, e vive in `data/preset_verdetti.json`.
#
# La separazione non e' pignoleria. La prima versione aveva i numeri scritti a
# mano accanto ai criteri, e sarebbero diventati falsi in silenzio al primo
# cambio di soglia o al primo mese di dati in piu'. Un verdetto misurato deve
# poter dire QUANDO e' stato misurato, e con cosa.
#
# `cautela` invece resta scritta a mano, ed e' giusto: non e' un risultato, e'
# cio' che quel risultato non potra' mai dire. Non cambia rigiocando.
PRESET = {
    "forza_confermata": {
        "etichetta": "Forza confermata",
        "criteri": {"sopra_media_200": 0.05, "variazione_1a_minima": 0.20},
        "idea": "sale da un anno ed e' ancora sopra la sua media lunga",
        # Il rigioco calcola la «media a 200 sedute» su dieci chiusure mensili:
        # e' un numero diverso da quello che lo scanner applica dal vivo, e
        # questo preset e' l'unico in cui la differenza tocca un criterio.
        "cautela": "nel rigioco la media a 200 sedute e' una media di dieci mesi, "
                   "quindi il verdetto misura una cosa simile ma non identica a "
                   "quella che il criterio applica dal vivo",
    },
    "crescita_con_utili": {
        "etichetta": "Cresce e guadagna",
        "criteri": {"ricavi_yoy_minimo": 0.15, "eps_minimo": 0.0},
        "idea": "ricavi in crescita sull'anno prima, e l'ultimo trimestre in utile",
        "cautela": "i ricavi anno su anno vogliono cinque trimestri gia' depositati, "
                   "quindi questo preset non vede i titoli quotati da poco — ed e' "
                   "il motivo per cui ha meno mesi giudicabili degli altri",
    },
    "buon_drawdown": {
        "etichetta": "Buon drawdown",
        "criteri": {"drawdown_minimo": 0.30, "recupero_minimo": 0.15},
        "idea": "sceso molto e gia' ripartito dal fondo",
        "cautela": "e' l'idea del vecchio «Good Drawdown Monitor». Sul rigioco il "
                   "drawdown si misura fra chiusure di fine mese, quindi sottostima "
                   "i crolli rientrati dentro al mese",
    },
    "crollo_e_ripresa": {
        "etichetta": "Crollo e ripresa",
        "criteri": {"drawdown_minimo": 0.50, "recupero_minimo": 0.20},
        "idea": "come il precedente ma piu' estremo: dimezzato e in risalita",
        "cautela": "un titolo che si dimezza puo' scendere sotto la soglia di "
                   "capitalizzazione e uscire dalla popolazione investibile proprio "
                   "nel mese in cui questo preset lo cercherebbe",
    },
    "numeri_che_girano": {
        "etichetta": "Numeri che girano",
        "criteri": {"ricavi_yoy_minimo": 0.20, "margine_crescita_minima": 0.02},
        "idea": "ricavi in accelerazione E margine in miglioramento insieme",
        "cautela": "due criteri di bilancio insieme restringono molto la "
                   "popolazione: guarda i mesi giudicabili prima del vantaggio",
    },
}


def preset_validi() -> list[str]:
    """I preset i cui criteri esistono tutti. Serve al test che li sorveglia."""
    return [nome for nome, dati in PRESET.items()
            if all(c in CRITERI for c in dati["criteri"])]


# Quanti mesi indietro si guarda per la variazione delle azioni. Dodici, cioe'
# lo stesso trimestre dell'anno prima: le azioni in circolazione si muovono a
# scatti — un'emissione, un buyback annunciato — e su tre mesi il rumore delle
# assegnazioni ai dipendenti coprirebbe il segnale.
MESI_PER_AZIONI = 12


def azioni(serie: dict, mese: str) -> dict:
    """Come sono cambiate le azioni in circolazione nell'ultimo anno.

    Negativa vuol dire **buyback**: la societa' sta ricomprando, e ogni azione
    rimasta vale una fetta piu' grande della stessa impresa. Positiva vuol dire
    diluizione, che per chi gia' possiede e' il contrario.

    `serie` e' `{mese: {azioni: ...}}` e arriva dallo storico mensile, dove il
    numero di azioni e' quello **gia' pubblico** a quella data: e' la stessa
    prudenza dei bilanci, e senza la misura guarderebbe un deposito futuro.

    Vale `None` dove il dato manca — 21% delle righe — e li' non e' zero: di
    quelle societa' Defeatbeta non pubblica le azioni affatto.
    """
    vuota = {"variazione_1a": None, "adesso": None, "un_anno_fa": None}
    adesso = (serie.get(mese) or {}).get("azioni")
    if not adesso:
        return vuota

    anno, numero = int(mese[:4]), int(mese[5:7])
    totale = anno * 12 + numero - 1 - MESI_PER_AZIONI
    prima_mese = f"{totale // 12:04d}-{totale % 12 + 1:02d}"
    prima = (serie.get(prima_mese) or {}).get("azioni")
    if not prima:
        return vuota

    return {"variazione_1a": adesso / prima - 1, "adesso": adesso, "un_anno_fa": prima}


def misurabile(misurato: dict, criteri: dict) -> bool:
    """Di questo titolo si puo' DIRE qualcosa, con questi criteri?

    Serve a distinguere «non passa» da «non si sa», che nel confronto sono due
    cose opposte. Un titolo senza cinque trimestri depositati non e' un titolo
    che cresce poco: e' un titolo su cui il criterio non ha niente da dire.

    Il difetto che questa funzione chiude, misurato il 17/09/2026: il rigioco
    confrontava chi PASSA con tutto il resto, e fra il resto finivano anche
    quelli di cui mancava il dato. Ma avere il dato non e' neutro — chi ha
    cinque trimestri di storia e le azioni in circolazione di un anno fa e' una
    societa' piu' vecchia, meglio coperta e ancora viva.

    Quanto pesava: far passare **chiunque avesse la misura**, senza nessuna
    soglia, dava gia' +2,0% a sei mesi sui ricavi anno su anno e +15,2% a dodici
    sulle azioni. Piu' del criterio vero. Il metro misurava se stesso.
    """
    for nome in criteri:
        definizione = CRITERI.get(nome)
        if definizione is None:
            continue
        misura, _, _ = definizione
        if misura(misurato) is None:
            return False
    return True


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
