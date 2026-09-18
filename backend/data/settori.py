"""
settori.py — come e' andato un settore, per poterci confrontare un titolo.
# feat: il riferimento della forza relativa, letto una volta per scansione.

Un +30% in un anno non vuol dire la stessa cosa dappertutto. Se l'energia nel
suo complesso ha fatto +45%, quel +30% e' un titolo che perde terreno mentre
sale. Per dirlo serve un termine di paragone, e questo modulo lo produce: per
ogni settore, la mediana della variazione a un anno dei suoi titoli
**investibili**.

## Due ancore, e si sa sempre quale si e' usata

| quando | da dove | precisione |
|---|---|---|
| adesso | `universe_mercato` | **sedute**, come lo scanner |
| una data passata | `universe_prezzi_mensili` | mesi |

La prima e' quella che conta, perche' e' quella su cui si decide. Viene dalle
colonne `last_close` e `close_1a_fa`, che il lavoro giornaliero porta a casa
nella stessa passata sul parquet dei prezzi: 252 sedute esatte, cioe' la
finestra identica a quella su cui lo scanner calcola la variazione del singolo
titolo. Numeratore e riferimento misurano lo stesso periodo.

La seconda serve solo a chi scandaglia una data del passato. Li' il giornaliero
di tutti non esiste — conserviamo *un* prezzo per titolo, non la sua storia — e
l'unica storia di tutti che abbiamo e' mensile. Il paragone resta corretto
perche' il titolo e i suoi pari prendono gli STESSI due capi, ma e' una misura
piu' grossolana, e chi legge lo vede dichiarato in `base`.

**Prima questa distinzione non c'era e si usava il mensile sempre**, anche per
«adesso». Era una rinuncia inutile: il ragionamento era «undicimila letture
giornaliere sono ore», ed e' vero per le letture una per titolo — ma quel
parquet si aggrega in una query sola, che il lavoro giornaliero gia' paga.

## Il filtro investibile

La mediana si fa sui soli titoli abbastanza grandi e abbastanza scambiati — le
stesse soglie del rigioco. Prenderla su tutto l'universo ci metterebbe dentro
migliaia di societa' minuscole che nessuno comprerebbe, e il paragone sarebbe
con una popolazione da cui non si pesca.

## Il settore non ha storia

L'anagrafica tiene il settore di ADESSO. Qui non e' un problema — si guarda il
presente — ma nel rigioco si'; sta scritto in `rigioco.nota_settori()`.
"""
import logging

import config
from core.db import db_read
from domain import scansione

logger = logging.getLogger(__name__)

# Quanti mesi indietro guarda la variazione, sul ripiego mensile.
MESI_INDIETRO = 12

# Come si chiama, nel risultato, l'ancora che si e' potuta usare.
BASE_SEDUTE = "sedute"
BASE_MESI = "mesi"


def _mese_meno(mese: str, quanti: int) -> str:
    """Il mese di `quanti` mesi prima, in forma `AAAA-MM`."""
    anno, numero = int(mese[:4]), int(mese[5:7])
    totale = (anno * 12 + numero - 1) - quanti
    return f"{totale // 12:04d}-{totale % 12 + 1:02d}"


def mappa() -> dict[str, str]:
    """Il settore di ogni titolo che ne ha uno dichiarato."""
    with db_read() as conn:
        righe = conn.execute(
            "SELECT symbol, sector FROM universe_anagrafica "
            "WHERE sector IS NOT NULL AND sector != ''"
        ).fetchall()
    return {r["symbol"]: r["sector"] for r in righe}


def variazioni_a_sedute() -> tuple[dict[str, float], str | None]:
    """`{simbolo: variazione a 252 sedute}` e la data a cui e' ancorata.

    Si prendono solo i titoli la cui ultima chiusura e' del giorno piu' recente
    che il sistema abbia: un titolo fermo da tre settimane porterebbe nella
    mediana un anno che finisce tre settimane fa. Misurato il 18/09/2026, fra
    gli investibili sono **3.366 su 3.375** ad avere la stessa data, quindi il
    filtro toglie nove titoli e rende l'ancora unica invece che frastagliata.
    """
    with db_read() as conn:
        ultima = conn.execute(
            "SELECT MAX(last_close_date) AS quando FROM universe_mercato"
        ).fetchone()["quando"]
        if not ultima:
            return {}, None

        righe = conn.execute(
            """
            SELECT m.symbol AS symbol, m.last_close AS adesso,
                   m.close_1a_fa AS allora
            FROM universe_mercato m
            JOIN universe_anagrafica a ON a.symbol = m.symbol
            WHERE m.last_close_date = ?
              AND m.close_1a_fa > 0
              AND m.last_close IS NOT NULL
              AND m.avg_volume_30d IS NOT NULL
              AND a.shares_outstanding IS NOT NULL
              AND m.last_close * a.shares_outstanding >= ?
              AND m.last_close * m.avg_volume_30d >= ?
            """,
            (ultima, config.RIGIOCO_CAP_MINIMA_USD,
             config.RIGIOCO_SCAMBIATO_MINIMO_USD),
        ).fetchall()

    return {r["symbol"]: r["adesso"] / r["allora"] - 1 for r in righe}, ultima


def variazioni_a_mesi(mese: str) -> dict[str, float]:
    """`{simbolo: variazione a dodici mesi}` per i soli investibili di quel mese.

    Il ripiego per una scansione nel passato. Investibile vuol dire le stesse due
    soglie, misurate sui valori DI QUEL MESE: filtrare col valore di oggi
    selezionerebbe i sopravvissuti.
    """
    prima = _mese_meno(mese, MESI_INDIETRO)
    with db_read() as conn:
        righe = conn.execute(
            """
            SELECT ora.symbol AS symbol, ora.chiusura AS adesso,
                   allora.chiusura AS allora
            FROM universe_prezzi_mensili ora
            JOIN universe_prezzi_mensili allora
              ON allora.symbol = ora.symbol AND allora.mese = ?
            WHERE ora.mese = ?
              AND ora.azioni IS NOT NULL
              AND ora.volume_medio IS NOT NULL
              AND ora.chiusura IS NOT NULL
              AND allora.chiusura > 0
              AND ora.chiusura * ora.azioni >= ?
              AND ora.chiusura * ora.volume_medio >= ?
            """,
            (prima, mese, config.RIGIOCO_CAP_MINIMA_USD,
             config.RIGIOCO_SCAMBIATO_MINIMO_USD),
        ).fetchall()

    return {r["symbol"]: r["adesso"] / r["allora"] - 1 for r in righe}


def riferimenti(mese: str | None = None) -> dict:
    """Tutto quello che serve a misurare la forza relativa, in una lettura sola.

    Con `mese` a `None` — la scansione di adesso — l'ancora e' a SEDUTE. Con un
    mese, cioe' una scansione nel passato, si ripiega sul mensile.

    Ritorna anche `base` e `ancora`, e non sono ornamenti: due forze calcolate su
    ancore diverse non sono confrontabili fra loro, e chi legge un risultato deve
    sapere a che data e con che passo e' stato misurato il paragone.

    Senza i dati necessari torna tutto vuoto, e il criterio di settore non passa
    per nessuno — la stessa regola dei prezzi mancanti, non un caso speciale.
    """
    settori = mappa()

    if mese is None:
        variazioni, ancora = variazioni_a_sedute()
        base = BASE_SEDUTE
    else:
        variazioni, ancora = variazioni_a_mesi(mese), mese
        base = BASE_MESI

    if not variazioni:
        logger.info("[SETTORI] nessuna variazione a un anno calcolabile "
                    "(base %s, ancora %s): la forza di settore non e' misurabile",
                    base, ancora)

    return {
        "base": base,
        "ancora": ancora,
        "settori": settori,
        "riferimenti": scansione.mediane_di_settore(variazioni, settori),
        "variazioni": variazioni,
    }
