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
"""
import math


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
    if valore is None:
        return None

    # `math.isnan` dice la stessa cosa del confronto con se stesso, e la dice a
    # chi legge senza bisogno di un commento.
    if isinstance(valore, float) and math.isnan(valore):
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
