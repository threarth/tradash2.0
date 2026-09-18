"""
rigioco.py — un criterio rigiocato all'indietro, contro cio' che avrebbe fatto
             non usarlo affatto.
# feat: la domanda «questo criterio ha mai funzionato?» prima di accenderlo.

## Perche' esiste

I sei pesi del rilevatore spin-off sono nati da un caso — SanDisk — e quando
sono stati rigiocati hanno detto di no: tolto quel caso, la fascia alta rendeva
meno delle altre. Quella verifica e' arrivata **dopo** che il punteggio era gia'
in pagina. Questo modulo la mette prima, e la rende possibile per qualunque
criterio dello scanner.

## Il pezzo che al rigioco degli spin-off mancava: il paragone

Confrontare fra loro le fasce di punteggio dice solo che una fascia va meglio di
un'altra. Non dice la cosa che conta: **meglio di non filtrare affatto?** Un
criterio che trova titoli col +12% in sei mesi sembra bravo, finche' non si
scopre che in quei sei mesi tutto il mercato ha fatto +15%.

Qui ogni mese porta due numeri: la mediana di chi il criterio ha trovato, e la
mediana di tutti gli altri. La differenza e' l'unica misura onesta di cosa
aggiunge il criterio.

## Il paragone e' INVESTIBILE, ed e' costato una colonna in piu'

Prima il paragone era «tutti i titoli che a quella data avevano un prezzo»:
dentro c'erano migliaia di societa' minuscole e poco scambiate su cui nessuno
comprerebbe, e un criterio che le evitava risultava perdente anche quando stava
solo evitando il fondo del barile. Tutte le misure fatte prima del 15/09/2026
poggiavano su quel paragone.

Adesso entrambe le popolazioni si filtrano per capitalizzazione e controvalore
scambiato — soglie in `config.py`, dichiarate nel resoconto — e si filtrano
**coi valori di quel mese**. Usare la capitalizzazione di oggi sarebbe stato
peggio del difetto che correggeva: le societa' grandi oggi sono i sopravvissuti
e i vincitori, quindi il metro del 2019 sarebbe stato costruito con la risposta
del 2026.

## Tre orizzonti, non uno

Sei mesi soli non distinguono un criterio LENTO da uno SBAGLIATO. A tre, sei e
dodici mesi la differenza si vede: chi perde a tre e vince a dodici sta
anticipando troppo, chi perde a tutti e tre sta solo sbagliando.

## Cosa NON e'

Non e' un backtest di strategia: non si compra e non si vende, non ci sono costi
ne' pesi di portafoglio. E' la domanda «cosa avresti trovato quel mese, e come
sarebbe andata» ripetuta su tutti i mesi che i dati coprono.

E resta point-in-time davvero: i bilanci di un mese sono quelli che a quella
data erano gia' DEPOSITATI, con le date vere dell'indice dei filing dove ci
sono. Un rigioco che guarda i bilanci per fine periodo invece che per data di
deposito si racconta meglio di com'e' andato, di circa quaranta giorni.
"""
import logging
import queue
import threading
from datetime import date

import config
from core import registry
from core.db import db_read
from data import raffica
from data import fondamentali
from domain import publication_dates, scansione

logger = logging.getLogger(__name__)

# Gli orizzonti su cui si misura il rendimento successivo, e quello che resta
# il predefinito quando qualcuno ne chiede uno solo.
ORIZZONTI_MESI = config.RIGIOCO_ORIZZONTI_MESI
ORIZZONTE_MESI = 6

# Quanti titoli servono, **in CIASCUNA delle due popolazioni**, perche' la
# mediana di quel mese significhi qualcosa. Sotto questa soglia il mese si conta
# ma non entra nel riepilogo: la mediana di due titoli e' un aneddoto con l'aria
# di una misura.
#
# «Ciascuna» e' stato aggiunto il 17/09/2026, e la ragione e' misurata: la
# soglia valeva solo per i TROVATI, quindi un criterio larghissimo — che
# lasciava passare quasi tutti — si confrontava con un resto di due o tre titoli
# e vinceva di oltre il 50%. Non perche' fosse buono: perche' l'avversario non
# esisteva. E' lo stesso difetto della voce 1 del backlog, dall'altro lato.
TROVATI_MINIMI = 5


def _mesi_disponibili() -> list[str]:
    with db_read() as conn:
        righe = conn.execute(
            "SELECT DISTINCT mese FROM universe_prezzi_mensili ORDER BY mese"
        ).fetchall()
    return [r["mese"] for r in righe]


def _fine_mese(mese: str) -> str:
    """L'ultimo giorno del mese, in ISO: e' la data a cui si taglia il passato."""
    anno, numero = int(mese[:4]), int(mese[5:7])
    prossimo = date(anno + (numero == 12), numero % 12 + 1, 1)
    return date.fromordinal(prossimo.toordinal() - 1).isoformat()


def _mese_piu(mese: str, quanti: int) -> str:
    anno, numero = int(mese[:4]), int(mese[5:7])
    totale = (anno * 12 + numero - 1) + quanti
    return f"{totale // 12:04d}-{totale % 12 + 1:02d}"


def _settori() -> dict[str, str]:
    """Il settore di ogni titolo, letto una volta sola.

    **Questo dato non ha storia, e va detto.** L'anagrafica tiene il settore di
    ADESSO: non esiste una tabella che dica in che settore stava un titolo nel
    2019. Il rigioco quindi applica al 2019 la classificazione di oggi, e dove
    una societa' e' stata riclassificata la confronta con i pari sbagliati.

    E' un look-ahead vero, ma piccolo e di un tipo suo: non anticipa un
    RISULTATO — il settore non dice come e' andato il titolo — anticipa
    un'etichetta. Il rimedio sarebbe uno storico delle riclassificazioni, che
    Defeatbeta non pubblica. Sta scritto nel resoconto, accanto alle soglie.
    """
    with db_read() as conn:
        righe = conn.execute(
            "SELECT symbol, sector FROM universe_anagrafica "
            "WHERE sector IS NOT NULL AND sector != ''"
        ).fetchall()
    return {r["symbol"]: r["sector"] for r in righe}


def _bilanci_di_tutti() -> dict[str, tuple[dict, dict]]:
    """Voci e depositi di ogni titolo, letti una volta sola.

    Una lettura per titolo dentro al giro dei mesi sarebbe la stessa query
    ripetuta ottanta volte a testa: qui si prende tutto una volta e il rigioco
    diventa aritmetica.
    """
    with db_read() as conn:
        righe = conn.execute(
            "SELECT symbol, report_date, voce, valore, filing_date "
            "FROM universe_fondamentali WHERE valore IS NOT NULL"
        ).fetchall()

    per_simbolo: dict[str, tuple[dict, dict]] = {}
    for riga in righe:
        voci, depositi = per_simbolo.setdefault(riga["symbol"], ({}, {}))
        voci.setdefault(riga["voce"], {})[riga["report_date"]] = riga["valore"]
        if riga["filing_date"]:
            depositi[riga["report_date"]] = (riga["filing_date"], "filing_index")
    return per_simbolo


def _rendimento(mercato: dict, mese: str, orizzonte: int) -> float | None:
    """Quanto ha reso dal fine mese a `orizzonte` mesi dopo. `None` se manca un capo."""
    adesso = (mercato.get(mese) or {}).get("chiusura")
    dopo = (mercato.get(_mese_piu(mese, orizzonte)) or {}).get("chiusura")
    if not adesso or not dopo:
        return None
    return dopo / adesso - 1


def _investibile(riga: dict | None) -> bool:
    """Quel titolo, QUEL mese, era abbastanza grande e abbastanza scambiato?

    Un dato che manca non passa, come ovunque: una capitalizzazione non
    derivabile — mancano le azioni — non e' una capitalizzazione piccola, ma
    nemmeno una che si possa dichiarare sopra la soglia.
    """
    if not riga:
        return False
    cap = riga.get("capitalizzazione")
    volume = riga.get("volume_medio")
    chiusura = riga.get("chiusura")
    if cap is None or volume is None or chiusura is None:
        return False
    return (cap >= config.RIGIOCO_CAP_MINIMA_USD
            and chiusura * volume >= config.RIGIOCO_SCAMBIATO_MINIMO_USD)


def soglie() -> dict:
    """Le soglie del paragone, per dichiararle nel resoconto invece di nasconderle."""
    return {
        "capitalizzazione_minima": config.RIGIOCO_CAP_MINIMA_USD,
        "scambiato_minimo_al_giorno": config.RIGIOCO_SCAMBIATO_MINIMO_USD,
        "nota": ("misurate sui valori DI QUEL MESE, non di oggi: filtrare il "
                 "passato con la capitalizzazione di adesso selezionerebbe i "
                 "sopravvissuti"),
    }


def nota_settori() -> str:
    """Il limite del criterio di settore. Si dichiara sempre, anche se non e' usato.

    Regola 5: cio' che manca si dichiara col suo motivo. Qui non manca un dato,
    manca la sua STORIA — ed e' un'assenza che non si vede guardando i numeri,
    perche' il rigioco produce un settore per ogni titolo di ogni mese senza
    battere ciglio.
    """
    return (
        "il settore di un titolo e' quello di ADESSO: l'anagrafica non tiene lo "
        "storico delle riclassificazioni, e Defeatbeta non lo pubblica. Un titolo "
        "riclassificato nel 2023 viene quindi confrontato, anche nel 2019, coi "
        "pari di oggi. E' un look-ahead su un'ETICHETTA, non su un risultato: il "
        "settore non dice come e' andato quel titolo, dice con chi lo si paragona."
    )


def nota_prezzi() -> str:
    """Come sono calcolate, nel rigioco, le misure di prezzo. Va detto sempre.

    Lo scanner dal vivo legge le SEDUTE; il rigioco legge un punto per mese,
    perche' rileggere i prezzi giornalieri di dodicimila titoli per ognuno dei
    quarantun mesi sarebbe un lavoro da ore. Le due serie non danno gli stessi
    numeri, e il piu' diverso e' il drawdown: su chiusure di fine mese un crollo
    rientrato dentro il mese non si vede affatto.
    """
    return (
        "Nel rigioco le misure di prezzo si calcolano su un punto per MESE, non "
        "sulle sedute: la variazione a un anno e' fra due chiusure di fine mese, "
        "la «media a 200 sedute» e' la media di dieci chiusure mensili, e il "
        "drawdown non vede i minimi toccati dentro al mese — quindi lo "
        "sottostima. Sono numeri confrontabili fra loro nel tempo, non con "
        "quelli che vedi nello scanner dal vivo."
    )


def _storia_fino_a(mesi: dict, mese: str) -> tuple[list[float], list[float]]:
    """Chiusure e volumi fino a quel mese COMPRESO, in ordine. Niente futuro.

    E' l'equivalente mensile della serie di sedute che lo scanner dal vivo
    riceve: la stessa matematica ci gira sopra, con le finestre in mesi.
    """
    fino = sorted(m for m in mesi if m <= mese)
    chiusure = [mesi[m]["chiusura"] for m in fino]
    volumi = [mesi[m]["volume_medio"] for m in fino if mesi[m]["volume_medio"] is not None]
    return chiusure, volumi


def _candidati_del_mese(mese: str, mercato: dict, bilanci: dict, depositi_8k: dict,
                        orizzonti: tuple[int, ...]) -> list[dict]:
    """Ogni investibile di quel mese, gia' misurato. Prima passata.

    Si ferma PRIMA di giudicare, ed e' il cambiamento che ha reso necessarie
    due passate: la forza relativa al settore non si puo' calcolare finche' non
    si sa come e' andato tutto il settore, e per saperlo bisogna aver misurato
    tutti. Le misure restano in memoria e la seconda passata non rilegge niente:
    la parte cara — leggere i prezzi e i bilanci — si fa una volta sola.
    """
    quando = _fine_mese(mese)
    candidati = []

    for simbolo, mesi in mercato.items():
        if not _investibile(mesi.get(mese)):
            continue

        # Le misure di prezzo si calcolano sulla storia fino a QUEL mese, con la
        # stessa funzione dello scanner dal vivo e le finestre in mesi. Prima
        # qui c'era il solo dizionario dei fondamentali, e un criterio di
        # prezzo faceva saltare tutto il rigioco con un KeyError.
        chiusure, volumi = _storia_fino_a(mesi, mese)
        misurato = scansione.misure(chiusure, volumi, scansione.FINESTRE_MENSILI)
        # Le azioni in circolazione di ALLORA: stanno nello stesso storico
        # mensile, gia' filtrate su cio' che era pubblico a quella data.
        misurato["azioni"] = scansione.azioni(mesi, mese)
        # I depositi 8-K di ALLORA. Qui il point-in-time viene gratis: la
        # tabella e' indicizzata sulla data di DEPOSITO, quindi contare i mesi
        # fino a questo e' esattamente cio' che si sapeva allora.
        #
        # Si chiama `depositi_8k` e non `depositi` perche' dieci righe piu' in
        # basso c'e' gia' un `depositi`, che e' un'altra cosa: le date in cui i
        # BILANCI sono stati depositati. Con lo stesso nome il secondo
        # sovrascriveva il primo dalla seconda iterazione in poi, e la raffica
        # risultava non calcolabile per quasi tutti — un rigioco che diceva
        # «nessun mese giudicabile» senza nessun errore.
        misurato["depositi"] = scansione.depositi(depositi_8k.get(simbolo, {}), mese)

        voci, depositi = bilanci.get(simbolo, ({}, {}))
        if voci:
            periodi = sorted(voci.get("total_revenue", {}))
            pubblici = [p for p in periodi
                        if publication_dates.was_public(depositi, p, quando)]
            misurato["fondamentali"] = scansione.fondamentali(voci, pubblici)

        candidati.append({
            "symbol": simbolo,
            "misurato": misurato,
            "rese": {o: _rendimento(mesi, mese, o) for o in orizzonti},
        })

    return candidati


def _misura_mese(mese: str, criteri: dict, mercato: dict, bilanci: dict,
                 settori: dict, depositi_8k: dict,
                 orizzonti: tuple[int, ...]) -> dict:
    """Un mese: chi era investibile, chi il criterio trovava, e come sono andati.

    I rendimenti si raccolgono per tutti gli orizzonti nella stessa passata: i
    titoli sono gli stessi e la scansione dei criteri e' la parte cara.
    """
    candidati = _candidati_del_mese(mese, mercato, bilanci, depositi_8k, orizzonti)
    trovati = {o: [] for o in orizzonti}
    resto = {o: [] for o in orizzonti}
    non_giudicabili = 0

    # Come e' andato ogni settore QUEL mese, dai soli investibili di quel mese:
    # e' il paragone giusto, perche' e' la popolazione da cui il criterio
    # pescherebbe. Prenderla da tutto l'universo ci metterebbe dentro titoli
    # che quel mese non erano nemmeno comprabili.
    riferimenti = scansione.mediane_di_settore(
        {c["symbol"]: c["misurato"]["variazione_1a"] for c in candidati}, settori)

    for candidato in candidati:
        misurato = candidato["misurato"]
        settore = settori.get(candidato["symbol"])
        misurato["settore"] = scansione.forza_settore(
            misurato["variazione_1a"], riferimenti.get(settore))

        # **Chi non e' giudicabile non entra in nessuna delle due popolazioni.**
        # Metterlo fra "il resto" farebbe vincere il criterio per il solo fatto
        # che chi ha il dato e' una societa' piu' vecchia e meglio coperta —
        # misurato, e pesava piu' del criterio stesso.
        if not scansione.misurabile(misurato, criteri):
            non_giudicabili += 1
            continue

        dove = trovati if scansione.valuta(misurato, criteri)[0] else resto

        for orizzonte, resa in candidato["rese"].items():
            if resa is not None:
                dove[orizzonte].append(resa)

    investibili = len(candidati)
    return {
        "mese": mese,
        "investibili": investibili,
        # Quanti investibili sono stati esclusi perche' il criterio su di loro
        # non si puo' calcolare. Si dichiara: e' la misura di quanto il paragone
        # e' ristretto, e un numero alto vuol dire che si sta guardando una
        # fetta piccola e particolare dell'universo.
        "non_giudicabili": non_giudicabili,
        "trovati": max((len(v) for v in trovati.values()), default=0),
        "orizzonti": {
            str(o): {
                "trovati": len(trovati[o]),
                "resto": len(resto[o]),
                "mediana_trovati": scansione.mediana(trovati[o]),
                "mediana_resto": scansione.mediana(resto[o]),
            }
            for o in orizzonti
        },
    }


def rigioca(criteri: dict, orizzonti: tuple[int, ...] | None = None) -> dict:
    """Rigioca un insieme di criteri su tutti i mesi che i dati coprono.

    Ritorna, per ogni mese e per ogni orizzonte: quanti titoli il criterio
    avrebbe trovato fra quelli investibili, come sono andati, e come e' andato
    **il resto degli investibili** nello stesso periodo.
    """
    sconosciuti = sorted(set(criteri) - set(scansione.CRITERI))
    if sconosciuti:
        raise ValueError(f"criteri sconosciuti: {', '.join(sconosciuti)}")

    orizzonti = tuple(orizzonti or ORIZZONTI_MESI)
    mercato = fondamentali.mercato_mensile()
    if not mercato:
        raise ValueError("lo storico mensile non e' stato derivato: "
                         "senza, non c'e' niente da rigiocare")

    bilanci = _bilanci_di_tutti()
    mesi = _mesi_disponibili()
    # Un mese entra se almeno l'orizzonte piu' corto ha un futuro da misurare;
    # quelli lunghi lo escluderanno da soli nel riepilogo.
    misurabili = [m for m in mesi if _mese_piu(m, min(orizzonti)) <= mesi[-1]]

    settori = _settori()
    depositi_8k = raffica.per_mese()
    per_mese = [_misura_mese(m, criteri, mercato, bilanci, settori, depositi_8k, orizzonti)
                for m in misurabili]

    return {
        "criteri": criteri,
        "orizzonti_mesi": list(orizzonti),
        "soglie": soglie(),
        "nota_prezzi": nota_prezzi(),
        "nota_settori": nota_settori(),
        "mesi": per_mese,
        "riepilogo": {str(o): riepiloga(per_mese, o) for o in orizzonti},
    }


def riepiloga(per_mese: list[dict], orizzonte: int) -> dict:
    """Il conto finale di UN orizzonte: in quanti mesi il criterio ha battuto il resto.

    Si contano i MESI vinti e non la media delle differenze: una media si fa
    dominare da un mese solo, e la domanda «funziona?» e' «funziona spesso?».
    """
    chiave = str(orizzonte)
    validi = [m["orizzonti"][chiave] for m in per_mese
              if m["orizzonti"].get(chiave)
              and m["orizzonti"][chiave]["trovati"] >= TROVATI_MINIMI
              and m["orizzonti"][chiave]["resto"] >= TROVATI_MINIMI
              and m["orizzonti"][chiave]["mediana_trovati"] is not None
              and m["orizzonti"][chiave]["mediana_resto"] is not None]
    if not validi:
        return {"mesi_utili": 0, "vinti": 0, "quota_vinti": None,
                "vantaggio_mediano": None,
                "reason": f"nessun mese con almeno {TROVATI_MINIMI} titoli da una "
                          f"parte E dall'altra: a {orizzonte} mesi il criterio e' "
                          f"troppo stretto, o troppo largo, per essere giudicato"}

    differenze = [m["mediana_trovati"] - m["mediana_resto"] for m in validi]
    vinti = sum(1 for d in differenze if d > 0)
    return {
        "mesi_utili": len(validi),
        "vinti": vinti,
        "quota_vinti": round(vinti / len(validi), 3),
        "vantaggio_mediano": round(scansione.mediana(differenze), 4),
        "trovati_per_mese": round(sum(m["trovati"] for m in validi) / len(validi), 1),
        "reason": None,
    }


# --- il giro in un thread, per il pulsante ----------------------------------

JOB_KIND = "rigioco"

# Quanto si aspetta che il thread consegni il proprio run_id.
ATTESA_AVVIO_S = 5.0

_esiti: dict[str, dict] = {}
_lucchetto = threading.Lock()


def _esegui(criteri: dict, orizzonti: tuple[int, ...], consegna: queue.Queue) -> dict:
    """Un rigioco dentro il registro dei lavori: si vede e si ferma."""
    mesi = "/".join(str(o) for o in orizzonti)
    etichetta = f"rigioco di {len(criteri)} criteri su {mesi} mesi"
    with registry.job(JOB_KIND, etichetta, total=1) as lavoro:
        consegna.put(lavoro.run_id)
        esito = rigioca(criteri, orizzonti)
        esito["run_id"] = lavoro.run_id
        giudicabili = ", ".join(
            f"{o}m: {esito['riepilogo'][str(o)]['mesi_utili']}" for o in orizzonti)
        lavoro.advance(detail=f"mesi giudicabili — {giudicabili}")

    with _lucchetto:
        _esiti[lavoro.run_id] = esito
    return esito


def avvia(criteri: dict, orizzonti: tuple[int, ...] | None = None) -> str:
    """Avvia un rigioco in un thread e ritorna il run_id con cui seguirlo.

    I criteri si controllano PRIMA di partire: un errore sollevato dentro al
    thread non tornerebbe a chi ha premuto, che resterebbe ad aspettare un
    run_id che non arriva mai.
    """
    sconosciuti = sorted(set(criteri) - set(scansione.CRITERI))
    if sconosciuti:
        raise ValueError(f"criteri sconosciuti: {', '.join(sconosciuti)}")
    if not _mesi_disponibili():
        raise ValueError("lo storico mensile non e' stato derivato: senza, non "
                         "c'e' niente da rigiocare")

    consegna: queue.Queue = queue.Queue(maxsize=1)
    threading.Thread(target=_esegui,
                     args=(criteri, tuple(orizzonti or ORIZZONTI_MESI), consegna),
                     name="rigioco", daemon=True).start()
    return consegna.get(timeout=ATTESA_AVVIO_S)


def esito(run_id: str) -> dict | None:
    """Il risultato di un rigioco finito, o None se non c'e' (ancora)."""
    with _lucchetto:
        return _esiti.get(run_id)
