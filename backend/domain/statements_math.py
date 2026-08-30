"""
_statements_math.py — aritmetica pura sui DataFrame dei bilanci (leaf condiviso).
# feat: ITEM 2 piano post-blocco 10 — home unica degli accessor su stock_statement.

Opera sui DataFrame wide prodotti da FundamentalsService (index=report_date
crescente, colonne=item_name, valori numerici). Nessuna dipendenza dai servizi:
e' un modulo foglia importato sia da fundamentals_service (blocco 3) sia da
fundamental_quality/_context (blocco 5), cosi' la stessa aritmetica TTM/YoY non
viene duplicata e il layering resta corretto (entrambi importano verso il basso).
"""
import pandas as pd

# Numero di trimestri in un anno fiscale (per TTM e confronti YoY).
QUARTERS_PER_YEAR = 4


def series(df: pd.DataFrame, item: str) -> pd.Series:
    """Serie temporale di una voce (colonna), crescente per data. Vuota se assente."""
    if df is None or df.empty or item not in df.columns:
        return pd.Series(dtype=float)
    return df[item].dropna()


def latest(df: pd.DataFrame, item: str) -> float | None:
    """Valore piu' recente di una voce, o None."""
    s = series(df, item)
    return float(s.iloc[-1]) if len(s) else None


def quarter_series(df: pd.DataFrame, item: str, n: int) -> list[float]:
    """Ultimi n valori trimestrali di una voce (dal piu' vecchio al piu' recente)."""
    s = series(df, item)
    return [float(v) for v in s.iloc[-n:]] if len(s) else []


def ttm_sum(df: pd.DataFrame, item: str) -> float | None:
    """Somma TTM (ultimi 4 trimestri) di una voce di flusso. None se < 4 trimestri."""
    s = series(df, item)
    if len(s) < QUARTERS_PER_YEAR:
        return None
    return float(s.iloc[-QUARTERS_PER_YEAR:].sum())


def yoy_change(df: pd.DataFrame, item: str) -> float | None:
    """
    Variazione frazionaria YoY del trimestre piu' recente vs 4 trimestri prima.
    None se non ci sono almeno 5 trimestri o il denominatore e' zero.
    """
    s = series(df, item)
    if len(s) < QUARTERS_PER_YEAR + 1:
        return None
    recent = float(s.iloc[-1])
    year_ago = float(s.iloc[-1 - QUARTERS_PER_YEAR])
    if year_ago == 0:
        return None
    return (recent - year_ago) / abs(year_ago)


def positive_quarters(df: pd.DataFrame, item: str, n: int = QUARTERS_PER_YEAR) -> tuple[int, int]:
    """(numero di trimestri positivi, trimestri considerati) sugli ultimi n."""
    vals = quarter_series(df, item, n)
    return sum(1 for v in vals if v > 0), len(vals)
