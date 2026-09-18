"""
scansione.py — decidere se un titolo soddisfa dei criteri, guardando i prezzi.
# feat (Blocco 9): la parte che decide, senza sapere da dove vengono i prezzi.

Ogni criterio e' una funzione che riceve le misure gia' calcolate e ritorna
`(soddisfatto, spiegazione)`. La spiegazione non e' un lusso: uno scanner che
dice solo "sette titoli" costringe a fidarsi, e "basato su cosa?" e' la domanda
che nel vecchio sistema non aveva risposta.

Matematica pura: entrano prezzi e soglie, escono verdetti.
"""
import config
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

# Le finestre della raffica di depositi: tre mesi contro due anni. Stanno in
# `config` perche' le usa anche chi costruisce la tabella derivata, e qui si
# rileggono da li' invece di riscriverle.
FINESTRA_DEPOSITI = config.DEPOSITI_FINESTRA_MESI
ABITUDINE_DEPOSITI = config.DEPOSITI_ABITUDINE_MESI

# Quanti trimestri fanno un anno. Serve al confronto anno su anno, che e' l'unico
# modo di guardare i ricavi senza guardare il calendario.
TRIMESTRI_PER_ANNO = 4


def _media(valori: list[float]) -> float | None:
    return sum(valori) / len(valori) if valori else None


def mediana(valori: list[float]) -> float | None:
    """La mediana, o `None` se non c'e' niente da mediare.

    Sta qui e non nel rigioco perche' adesso la usano in due: il riepilogo dei
    rendimenti e la forza relativa al settore. Due mediane scritte in due
    moduli sono due posti dove sbagliare lo stesso arrotondamento.
    """
    if not valori:
        return None
    ordinati = sorted(valori)
    meta = len(ordinati) // 2
    if len(ordinati) % 2:
        return ordinati[meta]
    return (ordinati[meta - 1] + ordinati[meta]) / 2


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
    # La variazione del NUMERO DI AZIONI, non la causa che l'ha prodotta. La
    # soglia e' un MASSIMO: a -0,02 chiede che le azioni siano calate almeno del
    # 2% in un anno, a zero soltanto che non siano aumentate.
    "azioni_variazione_massima": (
        lambda m: m["azioni"]["variazione_1a"] if m.get("azioni") else None, False,
        "numero di azioni variato non piu' di {soglia:+.1%} in un anno "
        "(adesso {valore:+.1%})",
    ),
    # La forza relativa al settore. E' l'unico criterio TRASVERSALE: tutti gli
    # altri guardano il titolo e basta, questo ha bisogno di sapere come sono
    # andati gli altri titoli del suo settore nello stesso periodo. Per questo
    # la casella `settore` la riempie chi chiama, come per `azioni`.
    "forza_settore_minima": (
        lambda m: (m.get("settore") or {}).get("forza"), True,
        "ha battuto la mediana del suo settore di almeno {soglia:.0%} in un anno "
        "(adesso {valore:+.1%})",
    ),
    # La raffica di 8-K. **La soglia e' un MASSIMO**: passa chi NON sta
    # depositando molto piu' del solito. E' l'unico criterio nato al contrario
    # di come era stato chiesto — doveva avvertire di una crescita e avverte di
    # un guaio — ed e' rimasto perche' misura, non perche' risponde.
    "depositi_raffica_massima": (
        lambda m: (m.get("depositi") or {}).get("raffica"), False,
        "non sta depositando 8-K piu' di {soglia:.1f} volte il suo solito "
        "(adesso {valore:.1f}x)",
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
    "batte_i_suoi_pari": {
        "etichetta": "Batte i suoi pari",
        "criteri": {"forza_settore_minima": 0.0},
        "idea": "ha fatto meglio della MEDIANA del suo settore nell'ultimo anno",
        "cautela": "non e' un avviso di crescita in arrivo: e' il contrario, "
                   "dice chi sta gia' correndo. E il merito e' tutto alla soglia "
                   "zero — alzandola il vantaggio si assottiglia e poi si "
                   "rovescia, quindi non cercare i piu' forti, cerca chi sta "
                   "sopra la meta'. Inoltre il settore di un titolo e' quello di "
                   "ADESSO anche nei mesi del 2019: l'anagrafica non ne tiene lo storico",
    },
    "evita_i_guai": {
        "etichetta": "Evita i guai",
        "criteri": {"azioni_variazione_massima": 0.0, "depositi_raffica_massima": 3.0},
        "idea": "non emette azioni e non sta depositando 8-K a raffica",
        # E' il primo preset fatto di sole ESCLUSIONI, e nasce da un'ammissione:
        # dei quattro indicatori chiesti per anticipare una crescita, i due che
        # misurano meglio dicono entrambi chi EVITARE. Metterli insieme e'
        # l'unico modo onesto di usarli.
        "cautela": "non trova niente, toglie soltanto: e' un filtro da "
                   "combinare con un criterio che cerca, non un preset da "
                   "premere da solo. La soglia 3x sulla raffica e' la migliore "
                   "di quattro provate, e quel «migliore di quattro» va tenuto "
                   "presente: l'effetto e' solido a 1,5x, 2x e 3x, ma il fatto "
                   "che il massimo cada proprio a 3 e' anche un po' fortuna",
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


# Quanti mesi indietro si guarda per la variazione del numero di azioni. Dodici,
# cioe' lo stesso trimestre dell'anno prima: il numero di azioni si muove a
# scatti, e su tre mesi il rumore delle assegnazioni ai dipendenti coprirebbe
# tutto il resto.
MESI_PER_AZIONI = 12


def azioni(serie: dict, mese: str) -> dict:
    """Di quanto e' cambiato il NUMERO di azioni in circolazione in un anno.

    ## Cosa misura, e cosa non misura

    Misura un conteggio, non una causa. Negativa vuol dire che le azioni sono
    **diminuite** — puo' venire da un riacquisto, da un annullamento, da altro —
    e positiva che sono **aumentate**, il che puo' venire da un aumento di
    capitale, da compensi in azioni, da azioni emesse per pagare
    un'acquisizione o dalla conversione di un'obbligazione.

    Chiamarla «buyback» le attribuirebbe una causa che il dato non contiene. Chi
    vuole la causa deve guardare il rendiconto finanziario, dove il denaro
    uscito per riacquistare azioni e' una voce sua — ed e' quella che usa `f5`.

    ## Gli split non la sporcano, ed e' stato verificato

    Uno split 10:1 moltiplicherebbe per dieci il numero di azioni senza che
    nulla sia cambiato, e un raggruppamento farebbe il contrario. Misurato su
    NVDA, che ha fatto uno split 10:1 nel giugno 2024: nello storico risultano
    ~24,6 miliardi di azioni **sia prima sia dopo**. Defeatbeta rettifica il
    conteggio all'indietro, come fa coi prezzi.

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


# Quanti titoli servono in un settore perche' la sua mediana significhi qualcosa.
# Misurato sui dati veri il 18/09/2026: applicando i filtri del rigioco
# (capitalizzazione e scambiato minimi), la coppia (mese, settore) piu' piccola
# di tutto lo storico e' Utilities nell'agosto 2019 con **71** titoli, e nessuna
# delle 1.023 coppie scende sotto 30. La soglia quindi non morde mai nel
# rigioco: serve allo scanner dal vivo, dove il settore puo' essere magro, e
# serve a dire che sotto quel numero la misura non esiste invece di valere zero.
MEMBRI_MINIMI_SETTORE = 20


def mediane_di_settore(variazioni: dict, settori: dict) -> dict:
    """Per ogni settore, la mediana delle variazioni a un anno e quanti l'hanno fatta.

    `variazioni` e' `{simbolo: variazione_1a}` e `settori` e' `{simbolo: settore}`.
    Chi non ha settore, o non ha variazione, non entra: non e' uno zero, e'
    qualcuno di cui non si sa in che gara corre.
    """
    per_settore: dict[str, list[float]] = {}
    for simbolo, variazione in variazioni.items():
        settore = settori.get(simbolo)
        if settore and variazione is not None:
            per_settore.setdefault(settore, []).append(variazione)

    return {settore: {"mediana": mediana(valori), "membri": len(valori)}
            for settore, valori in per_settore.items()}


def forza_settore(variazione: float | None, riferimento: dict | None) -> dict:
    """Di quanto un titolo ha battuto — o mancato — la MEDIANA del suo settore.

    ## Perche' la mediana e non la media

    In un settore con dentro un titolo che ha fatto +900% la media diventa quel
    titolo. La mediana dice «il tipico membro di questo settore», che e' la
    domanda vera: questo qui sta andando meglio dei suoi pari?

    ## A cosa serve

    Un +30% in un anno non vuol dire la stessa cosa dappertutto. Se l'energia
    nel suo complesso ha fatto +45%, quel +30% e' un titolo che perde terreno
    mentre sale; se il settore ha fatto -10%, e' un titolo che sta facendo
    qualcosa di suo. Il prezzo da solo non distingue i due casi, ed e'
    esattamente il genere di confusione che un criterio sul solo rendimento
    porta dentro allo scanner.

    ## Il titolo e' dentro alla propria mediana

    Si toglierebbe volentieri, ma vorrebbe dire ricalcolare una mediana per
    ogni titolo invece che una per settore: sul rigioco sono 93 mesi per 11
    settori, e passerebbe da mille mediane a duecentomila. Col minimo di venti
    membri il proprio contributo pesa al massimo un ventesimo, e sui numeri
    veri — settore piu' magro 71 titoli — meno dell'1,5%.
    """
    membri = (riferimento or {}).get("membri", 0)
    centro = (riferimento or {}).get("mediana")
    vuota = {"forza": None, "mediana_settore": None, "membri": membri}
    if variazione is None or centro is None or membri < MEMBRI_MINIMI_SETTORE:
        return vuota
    return {"forza": variazione - centro, "mediana_settore": centro, "membri": membri}


def depositi(serie: dict, mese: str) -> dict:
    """Il titolo sta depositando 8-K molto piu' del suo solito?

    ## Cosa misura

    `raffica` e' il rapporto fra quanti 8-K ha depositato negli ultimi tre mesi
    e quanti ne deposita di solito in tre mesi, misurato sui due anni
    precedenti. A 1 sta nel suo ritmo; a 3 ne sta depositando il triplo.

    ## E' un criterio di ESCLUSIONE, ed e' misurato

    Era stato costruito per avvertire di una crescita in arrivo. Fa il
    contrario, e con costanza — rigiocato il 18/09/2026 su 81-90 mesi:

        raffica >= 2x   -1,1% / -1,7% / -2,0%   vinti 38% / 39% / 32%
        raffica >= 3x   -0,5% / -4,2% / -5,1%   vinti 44% / 31% / 30%

    Peggiora con l'orizzonte e con l'intensita': non e' lento, e' rovesciato. La
    lettura e' che le buone notizie arrivano nella trimestrale e le cattive
    arrivano in pila — ristrutturazioni, cause, dirigenti che se ne vanno,
    finanziamenti diluitivi. Quindi la soglia e' un MASSIMO: passa chi NON e'
    in raffica.

    ## Chi non ha un'abitudine non e' giudicabile

    Senza nessun deposito nei due anni precedenti non c'e' un «solito» da cui
    scostarsi: la raffica vale `None`, non zero, e il criterio non passa. E' il
    caso dei titoli quotati da poco — che sono anche quelli su cui la misura
    sarebbe piu' sbagliata.
    """
    vuota = {"raffica": None, "recenti": None, "abitudine": None}

    def meno(quanti: int) -> str:
        anno, numero = int(mese[:4]), int(mese[5:7])
        totale = (anno * 12 + numero - 1) - quanti
        return f"{totale // 12:04d}-{totale % 12 + 1:02d}"

    finestra = [meno(i) for i in range(FINESTRA_DEPOSITI)]
    base = [meno(i) for i in range(FINESTRA_DEPOSITI,
                                   FINESTRA_DEPOSITI + ABITUDINE_DEPOSITI)]

    # Nessuna riga in due anni vuol dire che il titolo li' non c'era: e' diverso
    # da «c'era e non ha depositato niente», che pero' i nostri dati non
    # distinguono. Si sceglie di non giudicare, che e' la scelta prudente.
    if not any(m in serie for m in base):
        return vuota

    recenti = sum(serie.get(m, 0) for m in finestra)
    abitudine = sum(serie.get(m, 0) for m in base) / ABITUDINE_DEPOSITI * FINESTRA_DEPOSITI
    if abitudine <= 0:
        return {"raffica": None, "recenti": recenti, "abitudine": abitudine}
    return {"raffica": recenti / abitudine, "recenti": recenti, "abitudine": abitudine}


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
