"""
filing_locali.py — i documenti SEC che scarichi tu, e che il sistema riconosce.
# feat (Blocco 8): l'analisi qualitativa ha bisogno del TESTO, che Defeatbeta non ha.

Defeatbeta porta l'INDICE dei depositi — tipo, date, URL, numero di protocollo —
ma non il contenuto. L'analisi qualitativa ha come fonte primaria proprio quel
contenuto, e senza non produce un'analisi povera: non ne produce nessuna.

Il giro previsto: il sistema dice **quali** documenti servono e **con che nome**
salvarli, tu apri l'URL e li salvi in una cartella, il sistema li riconosce.

## Il nome, che e' la parte delicata

    NVDA_10-Q_2026-07-26_0001045810-26-000075.html
    ^^^^ ^^^^ ^^^^^^^^^^ ^^^^^^^^^^^^^^^^^^^^
      |    |      |        il numero di protocollo: LA CHIAVE
      |    |      fine del periodo, per ordinarli a occhio
      |    che documento e'
      il titolo, cosi' un file spostato resta riconoscibile

**Il riconoscimento avviene sul numero di protocollo, non sul resto.** E' la
chiave univoca di EDGAR e compare gia' nell'URL che apri: se salvi il file con
un nome diverso ma quel numero c'e' dentro, il sistema lo trova lo stesso. Il
resto del nome serve ai tuoi occhi quando guardi la cartella.

**E se il numero non c'e' affatto**, si riconosce anche il nome che il browser
propone da solo — `nvda-20260125.html`, cioe' simbolo e fine periodo. Non era
previsto, ed e' successo al primo tentativo vero: il sistema chiede un nome, ma
premere Ctrl+S ne produce un altro, e chiedere a chi salva di rinominare tre
file e' chiedere una cosa che si dimentica. Il protocollo resta la chiave
prima; questa e' la seconda, e vale solo se combacia anche la fine periodo.

Il protocollo si confronta anche senza trattini, perche' nell'URL sta cosi':
`0001045810-26-000075` nel documento, `000104581026000075` nel percorso.
"""
import logging
import platform
import re
from html.parser import HTMLParser
from pathlib import Path

import config
from core.tipi import python_puro
from data import defeatbeta

logger = logging.getLogger(__name__)

FORMA_ANNUALE = "10-K"
FORMA_TRIMESTRALE = "10-Q"

BYTE_PER_MB = 1024 * 1024

# I tag il cui contenuto non e' testo del documento: se finisse nel prompt,
# sarebbero migliaia di token di fogli di stile e script.
TAG_DA_SALTARE = frozenset({"script", "style", "head"})

# Spazi ripetuti e righe vuote: un filing HTML ne produce a valanghe, e ognuno
# e' un token pagato.
SPAZI_RIPETUTI = re.compile(r"[ \t\xa0]+")
RIGHE_VUOTE = re.compile(r"\n{3,}")

# La codifica dichiarata nell'intestazione del documento. I filing di EDGAR
# arrivano in **windows-1252**, non in UTF-8, e leggerli come UTF-8 con
# `errors="replace"` non fallisce: peggio, riesce e corrompe. Misurato sul 10-Q
# vero di NVDA, il byte 0x92 — l'apostrofo tipografico — diventava un carattere
# di sostituzione, e «Management's Discussion» arrivava al modello spezzato.
#
# Conta doppio qui: le citazioni si verificano confrontando le frasi con il
# testo. Se il testo e' corrotto, o il modello ci restituisce la frase corretta
# e la verifica fallisce, oppure la ricopia corrotta e finisce nel referto.
CHARSET_DICHIARATO = re.compile(rb"charset=[\"']?([\w-]+)", re.IGNORECASE)

# Quanto in testa al file si cerca la dichiarazione. La `<meta>` sta nel `<head>`,
# ma un filing ha righe lunghissime: qualche migliaio di byte le copre tutte.
BYTE_DI_INTESTAZIONE = 4096

# L'ultima spiaggia. `cp1252` non fallisce mai su nessun byte, quindi e' un
# ripiego che non lascia mai il documento illeggibile — e per i filing di EDGAR
# e' anche quello giusto quasi sempre.
CODIFICA_DI_RIPIEGO = "cp1252"


class _EstrattoreTesto(HTMLParser):
    """Tira fuori il testo da un documento HTML, con la libreria standard.

    Niente dipendenza nuova: `html.parser` fa esattamente questo, e un filing
    non ha bisogno di un parser tollerante agli errori piu' di quanto lo sia lui.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pezzi: list[str] = []
        self._salta = 0

    def handle_starttag(self, tag, attrs):
        if tag in TAG_DA_SALTARE:
            self._salta += 1

    def handle_endtag(self, tag):
        if tag in TAG_DA_SALTARE and self._salta:
            self._salta -= 1

    def handle_data(self, data):
        if not self._salta and data.strip():
            self.pezzi.append(data.strip())


def _protocollo_nudo(protocollo: str) -> str:
    """Il numero di protocollo senza trattini: cosi' compare dentro l'URL."""
    return protocollo.replace("-", "")


def nome_atteso(simbolo: str, voce: dict, estensione: str = ".html") -> str:
    """Come chiamare il file. Il numero di protocollo e' la parte che conta."""
    return (f"{simbolo}_{voce['form_type']}_{voce['report_date']}"
            f"_{voce['accession_number']}{estensione}")


# Che forma ha un simbolo accettabile. E' la stessa regola che usa il punto di
# lettura di Defeatbeta, e qui serve a una cosa in piu': **impedire di uscire
# dalla cartella dei documenti.**
#
# Trovato durante una ricognizione: `cartella("../../../etc")` costruiva un
# percorso FUORI da `data/filings`. Non era raggiungibile dalle rotte — Werkzeug
# normalizza il percorso e la rotta non combacia piu' — ma quella e' una
# proprieta' di un'altra libreria, e una difesa che dipende dal comportamento di
# un pezzo che non controlliamo non e' una difesa. Adesso il rifiuto e' qui.
SIMBOLO_AMMESSO = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")


# Siamo dentro WSL? Il kernel lo dice nel proprio nome, e lo dice una volta
# sola: e' una proprieta' della macchina, non della richiesta.
SU_WSL = "microsoft" in platform.release().lower()

# Il separatore dei percorsi di Windows. Scritto una volta perche' dentro a una
# f-string una barra rovesciata raddoppiata si legge male e si sbaglia.
SEPARATORE_WINDOWS = "\\"


class FilingError(ValueError):
    """Il simbolo non ha la forma di un simbolo: non si va a cercare niente."""


def cartella(simbolo: str) -> Path:
    """Dove vanno i documenti di un titolo. Una cartella per titolo, e basta.

    Solleva se il simbolo non ha la forma di un simbolo: un nome con dentro
    `..` o una barra non e' un titolo, e trattarlo come tale vorrebbe dire
    leggere file che non c'entrano niente — e, per l'analisi qualitativa,
    MANDARLI a un modello.
    """
    ambito = (simbolo or "").strip().upper()
    if not SIMBOLO_AMMESSO.match(ambito):
        raise FilingError(
            f"{simbolo!r} non ha la forma di un simbolo: la cartella dei "
            f"documenti si apre solo per un titolo"
        )

    dove = config.FILING_DIR / ambito
    # La cintura oltre alle bretelle: che il percorso RISOLTO stia dentro il
    # perimetro non dipende da quanto e' scritta bene l'espressione qui sopra.
    # Se un giorno quella si allarga per far passare un simbolo nuovo, questo
    # controllo regge lo stesso.
    if not dove.resolve().is_relative_to(config.FILING_DIR.resolve()):
        raise FilingError(f"{simbolo!r} porterebbe fuori da {config.FILING_DIR}")
    return dove


def _periodici(simbolo: str, run_id: str | None) -> list[dict]:
    """L'indice dei depositi periodici, dal piu' recente."""
    lettura = defeatbeta.sec_filings(simbolo, run_id=run_id)
    if not lettura.available:
        return []

    voci = []
    for _, riga in lettura.frame.iterrows():
        forma = python_puro(riga.get("form_type"))
        if forma not in (FORMA_ANNUALE, FORMA_TRIMESTRALE):
            continue
        protocollo = python_puro(riga.get("accession_number"))
        if not protocollo:
            continue
        voci.append({
            "form_type": forma,
            "report_date": str(python_puro(riga.get("report_date")) or "")[:10],
            "filing_date": str(python_puro(riga.get("filing_date")) or "")[:10],
            "accession_number": protocollo,
            "cik": python_puro(riga.get("cik")),
            "filing_url": python_puro(riga.get("filing_url")),
        })

    return sorted(voci, key=lambda v: v["filing_date"], reverse=True)


def richiesti(simbolo: str, run_id: str | None = None) -> list[dict]:
    """Quali documenti servono all'analisi qualitativa, e con che nome salvarli.

    L'ultimo annuale piu' gli ultimi trimestrali: coprono l'esercizio completo
    e l'anno in corso. Chiedere tutto lo storico costerebbe token per un
    contesto che l'analisi non usa.
    """
    ambito = simbolo.strip().upper()
    tutti = _periodici(ambito, run_id)

    scelti = (
        [v for v in tutti if v["form_type"] == FORMA_ANNUALE]
        [:config.FILING_QUALITATIVA_ANNUALI]
        + [v for v in tutti if v["form_type"] == FORMA_TRIMESTRALE]
        [:config.FILING_QUALITATIVA_TRIMESTRALI]
    )

    voci = []
    for voce in sorted(scelti, key=lambda v: v["filing_date"], reverse=True):
        file = _trova(ambito, voce)
        voci.append({**voce,
                     "nome_atteso": nome_atteso(ambito, voce),
                     "presente": file is not None,
                     "file": str(file) if file is not None else None,
                     **_collegamenti(ambito, voce)})
    return voci


def _collegamenti(simbolo: str, voce: dict) -> dict:
    """I due indirizzi: quello che punta al documento, e quello della cartella.

    **Il primo e' costruito per convenzione, non letto da nessuna parte.** Dal
    2019 la gran parte degli emittenti nomina il documento principale
    `{simbolo}-{fine periodo}.htm` — per NVDA, `nvda-20260125.htm`. Non e' una
    regola della SEC: e' un'abitudine, e per chi non la segue quell'indirizzo
    da' un 404.

    Per questo la cartella resta accanto, e la pagina dice quale dei due e'
    sicuro. Sapere il nome vero richiederebbe di chiedere a sec.gov, e a
    sec.gov questo sistema non chiede niente.
    """
    cartella_url = voce.get("filing_url")
    periodo = voce.get("report_date", "").replace("-", "")
    if not cartella_url or not periodo:
        return {"url": cartella_url, "url_cartella": cartella_url, "per_convenzione": False}

    return {
        "url": f"{cartella_url}/{simbolo.lower()}-{periodo}.htm",
        "url_cartella": cartella_url,
        "per_convenzione": True,
    }


def _file_salvati(simbolo: str) -> list[Path]:
    """I documenti nella cartella del titolo, esclusi gli scarti del salvataggio."""
    dove = cartella(simbolo)
    if not dove.is_dir():
        return []
    return [f for f in sorted(dove.iterdir())
            if f.is_file() and f.suffix.lower() in config.FILING_ESTENSIONI]


def _per_protocollo(simbolo: str) -> dict[str, Path]:
    """I file gia' salvati, indicizzati per numero di protocollo trovato nel nome.

    Si guarda DENTRO il nome invece di pretenderlo esatto: se hai salvato con un
    nome tuo ma il protocollo c'e', il documento e' quello e non c'e' motivo di
    non riconoscerlo.
    """
    trovati: dict[str, Path] = {}
    for file in _file_salvati(simbolo):
        nudo = _protocollo_nudo(file.stem)
        for pezzo in re.findall(r"\d{18}", nudo):
            trovati.setdefault(pezzo, file)
    return trovati


def _per_convenzione(simbolo: str, voce: dict) -> Path | None:
    """Il file salvato col nome che il browser propone: `nvda-20260125.html`.

    E' il nome del documento su EDGAR — la stessa convenzione con cui questo
    modulo costruisce il collegamento diretto. Si accetta solo se combacia
    ANCHE la fine periodo: `nvda-20260125` e `nvda-20260726` sono due documenti
    diversi, e confonderli metterebbe il trimestrale al posto dell'annuale.
    """
    periodo = str(voce.get("report_date") or "").replace("-", "")
    if not periodo:
        return None

    atteso = f"{simbolo.lower()}-{periodo}"
    for file in _file_salvati(simbolo):
        if file.stem.lower() == atteso:
            return file
    return None


def _trova(simbolo: str, voce: dict) -> Path | None:
    """Il file di un documento, cercato prima per protocollo e poi per convenzione."""
    per_protocollo = _per_protocollo(simbolo)
    trovato = per_protocollo.get(_protocollo_nudo(voce["accession_number"]))
    return trovato if trovato is not None else _per_convenzione(simbolo, voce)


def percorso_windows(percorso: Path) -> tuple[str | None, str | None]:
    """Lo stesso posto, scritto come lo vede Windows. Ritorna `(percorso, motivo)`.

    Serve perche' il giro dei documenti SEC attraversa due sistemi: la pagina
    gira qui, ma il salvataggio lo fa il browser, che sta su Windows — e in una
    finestra di salvataggio di Windows un percorso che comincia con `/home` non
    porta da nessuna parte. Su WSL i due nomi dello stesso posto sono due, e
    finora ne mostravamo uno solo: quello sbagliato per chi deve incollarlo.

    Fuori da WSL non c'e' niente da tradurre e non c'e' niente da spiegare:
    `(None, None)`. Sotto WSL senza il nome della distribuzione c'e' un motivo,
    perche' un campo che sparisce senza dire perche' si legge come un guasto.
    """
    if not SU_WSL:
        return None, None
    if not config.WSL_DISTRO:
        return None, ("WSL non ha detto come si chiama questa distribuzione "
                      "(WSL_DISTRO_NAME): il percorso di Windows non si compone, "
                      "e indovinarlo darebbe una cartella che non esiste")

    dentro = str(percorso).replace("/", SEPARATORE_WINDOWS)
    return f"{config.WSL_PREFISSO_UNC}{SEPARATORE_WINDOWS}{config.WSL_DISTRO}{dentro}", None


def testo(simbolo: str, voce: dict) -> tuple[str | None, str | None]:
    """Il testo di un documento salvato. Ritorna `(testo, errore)`, mai un None muto.

    Riceve la VOCE dell'indice e non il solo numero di protocollo, perche' il
    file si puo' riconoscere anche dal nome che il browser propone — e quel nome
    porta la fine periodo, non il protocollo.
    """
    file = _trova(simbolo, voce)
    if file is None:
        return None, (f"il documento {voce['accession_number']} non e' in "
                      f"{cartella(simbolo)}: salvalo li'")

    dimensione = file.stat().st_size / BYTE_PER_MB
    if dimensione > config.FILING_DIMENSIONE_MASSIMA_MB:
        return None, (f"{file.name} pesa {dimensione:.0f} MB, oltre il limite di "
                      f"{config.FILING_DIMENSIONE_MASSIMA_MB}: non sembra un filing")

    try:
        byte = file.read_bytes()
    except OSError as exc:
        return None, f"{file.name} non e' leggibile: {exc}"

    grezzo, codifica = _decodifica(byte)
    logger.info("[FILING] %s letto come %s", file.name, codifica)

    if file.suffix.lower() == ".txt":
        return _ripulisci(grezzo), None

    estrattore = _EstrattoreTesto()
    estrattore.feed(grezzo)
    return _ripulisci("\n".join(estrattore.pezzi)), None


def _decodifica(byte: bytes) -> tuple[str, str]:
    """Il testo del documento, nella codifica che il documento dichiara.

    Si prova prima quella dichiarata, poi UTF-8, poi il ripiego. Ritorna anche
    il nome della codifica usata, perche' quando una citazione non si verifica
    la prima domanda utile e' "con che codifica l'abbiamo letto".
    """
    trovata = CHARSET_DICHIARATO.search(byte[:BYTE_DI_INTESTAZIONE])
    candidate = [trovata.group(1).decode("ascii", "ignore")] if trovata else []
    candidate += ["utf-8", CODIFICA_DI_RIPIEGO]

    for codifica in candidate:
        try:
            return byte.decode(codifica), codifica
        except (UnicodeDecodeError, LookupError):
            continue

    # Non ci si arriva: cp1252 accetta qualunque byte. Se cambiasse, meglio un
    # testo con qualche carattere sostituito che nessun testo.
    return byte.decode("utf-8", errors="replace"), "utf-8 con sostituzioni"


def _ripulisci(testo_grezzo: str) -> str:
    """Toglie spazi e righe a vuoto: ognuno di quelli e' un token pagato."""
    return RIGHE_VUOTE.sub("\n\n", SPAZI_RIPETUTI.sub(" ", testo_grezzo)).strip()


def stato(simbolo: str, run_id: str | None = None) -> dict:
    """Cosa serve, cosa c'e', e dove metterlo. Tutto quello che serve per capire."""
    ambito = simbolo.strip().upper()
    voci = richiesti(ambito, run_id)
    mancanti = [v for v in voci if not v["presente"]]
    dove = cartella(ambito)
    da_windows, perche_no = percorso_windows(dove)

    return {
        "symbol": ambito,
        "cartella": str(dove),
        # Lo stesso posto visto da Windows, che e' dove sta il browser che
        # salva. `None` fuori da WSL: li' i due percorsi sono lo stesso.
        "cartella_windows": da_windows,
        "cartella_windows_reason": perche_no,
        "documenti": voci,
        "pronti": len(voci) - len(mancanti),
        "richiesti": len(voci),
        "completo": bool(voci) and not mancanti,
        "reason": ("nessun documento periodico nell'indice di Defeatbeta" if not voci
                   else None if not mancanti
                   else f"mancano {len(mancanti)} documenti su {len(voci)}"),
        "action": ("apri gli URL qui sotto, salva ogni documento nella cartella "
                   "indicata col nome proposto, poi riprova") if mancanti else None,
    }
