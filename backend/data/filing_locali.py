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

Il protocollo si confronta anche senza trattini, perche' nell'URL sta cosi':
`0001045810-26-000075` nel documento, `000104581026000075` nel percorso.
"""
import logging
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


def cartella(simbolo: str) -> Path:
    """Dove vanno i documenti di un titolo. Una cartella per titolo, e basta."""
    return config.FILING_DIR / simbolo.strip().upper()


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

    presenti = _per_protocollo(ambito)
    return [
        {**voce,
         "nome_atteso": nome_atteso(ambito, voce),
         "presente": _protocollo_nudo(voce["accession_number"]) in presenti,
         "file": str(presenti.get(_protocollo_nudo(voce["accession_number"]), "")) or None}
        for voce in sorted(scelti, key=lambda v: v["filing_date"], reverse=True)
    ]


def _per_protocollo(simbolo: str) -> dict[str, Path]:
    """I file gia' salvati, indicizzati per numero di protocollo trovato nel nome.

    Si guarda DENTRO il nome invece di pretenderlo esatto: se hai salvato con un
    nome tuo ma il protocollo c'e', il documento e' quello e non c'e' motivo di
    non riconoscerlo.
    """
    dove = cartella(simbolo)
    if not dove.is_dir():
        return {}

    trovati: dict[str, Path] = {}
    for file in dove.iterdir():
        if not file.is_file() or file.suffix.lower() not in config.FILING_ESTENSIONI:
            continue
        nudo = _protocollo_nudo(file.stem)
        for pezzo in re.findall(r"\d{18}", nudo):
            trovati.setdefault(pezzo, file)
    return trovati


def testo(simbolo: str, accession_number: str) -> tuple[str | None, str | None]:
    """Il testo di un documento salvato. Ritorna `(testo, errore)`, mai un None muto."""
    file = _per_protocollo(simbolo).get(_protocollo_nudo(accession_number))
    if file is None:
        return None, (f"il documento {accession_number} non e' in "
                      f"{cartella(simbolo)}: salvalo li'")

    dimensione = file.stat().st_size / BYTE_PER_MB
    if dimensione > config.FILING_DIMENSIONE_MASSIMA_MB:
        return None, (f"{file.name} pesa {dimensione:.0f} MB, oltre il limite di "
                      f"{config.FILING_DIMENSIONE_MASSIMA_MB}: non sembra un filing")

    try:
        grezzo = file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"{file.name} non e' leggibile: {exc}"

    if file.suffix.lower() == ".txt":
        return _ripulisci(grezzo), None

    estrattore = _EstrattoreTesto()
    estrattore.feed(grezzo)
    return _ripulisci("\n".join(estrattore.pezzi)), None


def _ripulisci(testo_grezzo: str) -> str:
    """Toglie spazi e righe a vuoto: ognuno di quelli e' un token pagato."""
    return RIGHE_VUOTE.sub("\n\n", SPAZI_RIPETUTI.sub(" ", testo_grezzo)).strip()


def stato(simbolo: str, run_id: str | None = None) -> dict:
    """Cosa serve, cosa c'e', e dove metterlo. Tutto quello che serve per capire."""
    ambito = simbolo.strip().upper()
    voci = richiesti(ambito, run_id)
    mancanti = [v for v in voci if not v["presente"]]

    return {
        "symbol": ambito,
        "cartella": str(cartella(ambito)),
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
