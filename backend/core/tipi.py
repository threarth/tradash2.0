"""
tipi.py — dai tipi di pandas ai tipi di Python.
# feat (Blocco 6): una conversione sola, per tutti quelli che la usano.

Chi legge da un DataFrame si ritrova in mano `numpy.int64`, `numpy.float64` e
`NaN`. Nessuno dei tre sopravvive al viaggio: SQLite rifiuta i primi due
(«unsupported type»), Flask li rifiuta in JSON («not JSON serializable») e il
terzo, `NaN`, non e' un numero mancante ma un numero che confronta falso con se
stesso — e passa i controlli scritti con `is None`.

Questo modulo esiste perche' la conversione era gia' scritta due volte, la
seconda dopo che la prima aveva smesso di bastare. La terza volta si scrive
qui, non altrove.

## I due assenti di pandas, trovati dal vivo

Oltre a `NaN` ci sono `pandas.NA` e `pandas.NaT`, e non si comportano come lui.
Sono arrivati insieme, leggendo l'elenco dei dirigenti di NVDA — dove eta',
anno di nascita e compenso mancano per sette righe su dieci:

- **`pandas.NA`** non e' un float, non ha `.item()`, non ha `.isoformat()`:
  passava indenne attraverso tutti i controlli e arrivava fino a `json.dumps`,
  che si fermava con «Object of type NAType is not JSON serializable». Ha
  fermato l'analisi qualitativa alla terza fase, **dopo** che le prime due
  erano state pagate.
- **`pandas.NaT`** e' peggio, perche' non si fermava: ha `.isoformat()`, e
  quel metodo restituisce la stringa `"NaT"`. Una data mancante diventava il
  testo «NaT» dentro un referto, dove nessuno l'avrebbe riconosciuta per cio'
  che era.

Si riconoscono dal nome del tipo invece che con `pandas.isna`, che su una lista
ritorna una lista di booleani e qui andrebbe protetto caso per caso. Un test
usa i valori veri di pandas: il giorno che li rinominano, si spacca quello.
"""
import math

# I due valori con cui pandas dice "manca", oltre a NaN.
ASSENTI_DI_PANDAS = ("NAType", "NaTType")


def manca(valore) -> bool:
    """Se questo valore e' uno dei modi in cui i dati dicono «non c'e'».

    I modi sono quattro e non si somigliano: `None`, `NaN` (che non e' un
    numero mancante ma un numero che confronta falso con se stesso), e i due
    sentinelle di pandas. Il controllo va fatto PRIMA di ogni altro, perche'
    `NaT` ha `.isoformat()` e senza questo diventava la stringa "NaT".
    """
    if valore is None:
        return True
    if type(valore).__name__ in ASSENTI_DI_PANDAS:
        return True
    # `math.isnan` dice la stessa cosa del confronto con se stesso, e la dice a
    # chi legge senza bisogno di un commento.
    return isinstance(valore, float) and math.isnan(valore)


def _da_numpy(valore):
    """L'equivalente Python di un tipo numpy, o `None` se non si lascia convertire."""
    try:
        return valore.item()
    except (ValueError, AttributeError):
        return None


def python_puro(valore):
    """Un valore di pandas/numpy reso in un tipo che Python, SQLite e JSON accettano.

    Le stringhe vuote e i `NaN` diventano `None`: un dato assente e' assente, e
    una stringa vuota che passa per «presente» falsa i conteggi di copertura.
    Le date diventano stringhe ISO, che sono leggibili, ordinabili e
    confrontabili — che e' come il resto del sistema tratta le date.
    """
    if manca(valore):
        return None

    if isinstance(valore, str):
        pulito = valore.strip()
        return pulito or None

    # Date e istanti — `pandas.Timestamp`, `datetime`, `date`: nessuno dei tre
    # arriva in JSON, e `.item()` su un Timestamp non li salva.
    if hasattr(valore, "isoformat"):
        return valore.isoformat()

    if hasattr(valore, "item"):
        convertito = _da_numpy(valore)
        return python_puro(convertito) if convertito is not None else None

    return valore
