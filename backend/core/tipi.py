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


def python_puro(valore):
    """Un valore di pandas/numpy reso in un tipo che Python, SQLite e JSON accettano.

    Le stringhe vuote e i `NaN` diventano `None`: un dato assente e' assente,
    e una stringa vuota che passa per «presente» falsa i conteggi di copertura.
    """
    if valore is None:
        return None

    # `math.isnan` invece del confronto con se stesso: dice la stessa cosa e la
    # dice a chi legge, senza che serva un commento per spiegarla.
    if isinstance(valore, float) and math.isnan(valore):
        return None

    if isinstance(valore, str):
        pulito = valore.strip()
        return pulito or None

    # I tipi di numpy espongono `.item()`, che ritorna l'equivalente Python.
    if hasattr(valore, "item"):
        try:
            return python_puro(valore.item())
        except (ValueError, AttributeError):
            return None

    return valore
