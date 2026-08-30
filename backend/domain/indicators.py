"""
indicators.py — indicatori tecnici su barre OHLCV, con un modello a nodi.
# feat (Blocco 6): copiato dal vecchio tradash, dove funzionava.

La configurazione e' una lista piatta di nodi collegati ad albero dal campo
`source`. Le radici implicite sono le serie base "price" (OHLC) e "volume".
Ogni nodo produce una serie primaria (chiave = id del nodo) ed eventuali serie
secondarie (chiave = "id:suffix": macd produce anche "id:signal" e "id:hist").

Il pezzo che vale la pena aver copiato e' il topo-sort: i nodi si calcolano
nell'ordine delle dipendenze, e una configurazione con un ciclo — un nodo che
si dice figlio di se stesso, magari dopo una modifica a mano — viene rifiutata
invece di girare a vuoto.

Matematica pura: pandas e basta. Nessuna rete, nessun database, nessun registro
da attraversare, perche' qui non si prende niente da nessuna parte.
"""
import math

import pandas as pd

# ---- Constants ----

# Sorgenti base implicite (non sono nodi): radici dell'albero.
BASE_PRICE = "price"
BASE_VOLUME = "volume"
BASE_SOURCES = frozenset({BASE_PRICE, BASE_VOLUME})

# Profondità massima dell'albero dei source (anti-loop / sanity).
MAX_NODE_DEPTH = 6

# Id del nodo volume nei default/migrazione: NON deve coincidere col nome della
# sorgente base "volume", altrimenti il nodo risulterebbe figlio di sé stesso.
VOLUME_NODE_ID = "vol_main"

# Trasformazioni che accettano una serie sorgente qualsiasi (price/volume/nodo).
SERIES_TRANSFORM_KINDS = frozenset({"ema", "sma", "roc"})

# Kind che richiedono OHLC → ammessi solo con source="price".
PRICE_ONLY_KINDS = frozenset({"bb", "rsi", "macd", "adx", "stoch", "cci", "obv", "atr"})

# Tutti i kind validi (incluso "volume", la radice volumi con source="volume").
VALID_KINDS = SERIES_TRANSFORM_KINDS | PRICE_ONLY_KINDS | frozenset({"volume"})

# Configurazione di default (usata quando non ci sono settings salvati):
# EMA50 + SMA200 come overlay sul prezzo, volume attivo.
DEFAULT_CONFIG: dict = {
    "nodes": [
        {"id": "ema50",  "kind": "ema", "source": BASE_PRICE, "enabled": True,
         "params": {"period": 50},  "style": {"color": "#3b82f6", "strokeWidth": 1.5}},
        {"id": "sma200", "kind": "sma", "source": BASE_PRICE, "enabled": True,
         "params": {"period": 200}, "style": {"color": "#8b5cf6", "strokeWidth": 1.5}},
        {"id": VOLUME_NODE_ID, "kind": "volume", "source": BASE_VOLUME, "enabled": True,
         "params": {}, "style": {"colorUp": "#10b981", "colorDown": "#f43f5e"}},
    ],
}


class IndicatorConfigError(ValueError):
    """Configurazione indicatori non valida (source mancante, ciclo, kind errato)."""


def _to_tv(ts, value: float | None) -> dict:
    """Converte timestamp + valore in dict {t, v} per il frontend."""
    vuoto = value is None or (isinstance(value, float) and math.isnan(value))
    v = None if vuoto else round(value, 4)
    return {"t": int(ts.timestamp() * 1000), "v": v}


# ---- Legacy migration (dict a chiavi fisse → lista di nodi) ----

# Mappa chiave legacy → (kind, source, parametri numerici da preservare).
_LEGACY_MAP: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "ema20":  ("ema",    BASE_PRICE,  ("period",)),
    "ema50":  ("ema",    BASE_PRICE,  ("period",)),
    "sma200": ("sma",    BASE_PRICE,  ("period",)),
    "bb20":   ("bb",     BASE_PRICE,  ("period", "stddev")),
    "rsi14":  ("rsi",    BASE_PRICE,  ("period",)),
    "macd":   ("macd",   BASE_PRICE,  ("fast", "slow", "signal")),
    "adx14":  ("adx",    BASE_PRICE,  ("period",)),
    "obv":    ("obv",    BASE_PRICE,  ()),
    "stoch":  ("stoch",  BASE_PRICE,  ("k_period", "d_period")),
    "cci20":  ("cci",    BASE_PRICE,  ("period",)),
    "roc12":  ("roc",    BASE_PRICE,  ("period",)),
    "atr14":  ("atr",    BASE_PRICE,  ("period",)),
    "volume": ("volume", BASE_VOLUME, ()),
}

_STYLE_KEYS = ("color", "strokeWidth", "colorUp", "colorDown")


def _legacy_node(node_id: str, kind: str, source: str, cfg: dict, param_keys) -> dict:
    """Costruisce un nodo dal vecchio formato preservando params e stile."""
    params = {k: cfg[k] for k in param_keys if k in cfg}
    style  = {k: cfg[k] for k in _STYLE_KEYS if k in cfg}
    return {
        "id": node_id, "kind": kind, "source": source,
        "enabled": bool(cfg.get("enabled", False)),
        "params": params, "style": style,
    }


def _normalize_node_ids(config: dict) -> dict:
    """
    Auto-heal di config già a nodi salvate prima del fix: rinomina un eventuale
    nodo volume con id == "volume" (collidente con la sorgente base) in
    VOLUME_NODE_ID, ripuntando i figli che lo referenziavano.
    """
    nodes = config.get("nodes", [])
    rename = {n["id"]: VOLUME_NODE_ID
              for n in nodes if n.get("kind") == "volume" and n.get("id") == BASE_VOLUME}
    if not rename:
        return config

    out = []
    for n in nodes:
        m = dict(n)
        is_vol = m.get("kind") == "volume" and m.get("id") == BASE_VOLUME
        if m.get("id") in rename:
            m["id"] = rename[m["id"]]
        # I figli che puntavano al vecchio id vengono ripuntati; il nodo volume
        # mantiene invece la sua sorgente base ("volume").
        if not is_vol and m.get("source") in rename:
            m["source"] = rename[m["source"]]
        out.append(m)
    return {"nodes": out}


def migrate_config(raw: dict | None) -> dict:
    """
    Converte una config legacy (dict a chiavi fisse) nel nuovo formato a nodi.
    Se `raw` è già nel nuovo formato ({"nodes": [...]}) viene normalizzato (id volume).
    """
    if raw is None:
        return {"nodes": []}
    if "nodes" in raw:
        return _normalize_node_ids(raw)

    nodes: list[dict] = []
    for key, (kind, source, param_keys) in _LEGACY_MAP.items():
        if key in raw:
            node_id = VOLUME_NODE_ID if key == "volume" else key
            nodes.append(_legacy_node(node_id, kind, source, raw[key], param_keys))

    # Medie mobili sovrapposte: figlie del nodo padre (volume → vol_main, atr → atr14).
    # Aggiunte solo se il nodo padre esiste nella config legacy.
    ma_parents = {"volume_ma": ("volume", VOLUME_NODE_ID), "atr_ma": ("atr14", "atr14")}
    for key, (parent_key, parent_id) in ma_parents.items():
        cfg = raw.get(key)
        if cfg and parent_key in raw:
            kind = "ema" if str(cfg.get("type", "sma")).lower() == "ema" else "sma"
            nodes.append(_legacy_node(key, kind, parent_id, cfg, ("period",)))

    return {"nodes": nodes}


def _normalized_config(config: dict | None) -> dict:
    """Garantisce una config nel nuovo formato a nodi (migra il legacy on-read)."""
    if not config:
        return {"nodes": []}
    if "nodes" in config:
        return config
    return migrate_config(config)


# ---- Overlay indicators (close only) ----

def _ema_series(close: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=period, adjust=False).mean()


def _sma_series(close: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window=period).mean()


def _bollinger_series(close: pd.Series, period: int,
                      stddev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Restituisce (upper, mid, lower) per le bande di Bollinger."""
    mid   = close.rolling(window=period).mean()
    sigma = close.rolling(window=period).std(ddof=0)
    return mid + stddev * sigma, mid, mid - stddev * sigma


def _rsi_series(close: pd.Series, period: int) -> pd.Series:
    """RSI con metodo di Wilder (smoothed moving average)."""
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))


def _macd_series(
    close: pd.Series, fast: int, slow: int, signal: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Restituisce (macd_line, signal_line, histogram)."""
    fast_ema  = close.ewm(span=fast, adjust=False).mean()
    slow_ema  = close.ewm(span=slow, adjust=False).mean()
    macd_line   = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def _roc_series(close: pd.Series, period: int) -> pd.Series:
    """Rate of Change in percentuale."""
    prev = close.shift(period).replace(0, float('nan'))
    return (close / prev - 1.0) * 100.0


# ---- Indicators requiring High + Low ----

def _adx_series(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Average Directional Index — restituisce (ADX, +DI, -DI)."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    # Wilder smoothing = EMA con alpha=1/period
    atr       = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    smooth_pd = plus_dm.ewm(alpha=1.0 / period, adjust=False).mean()
    smooth_md = minus_dm.ewm(alpha=1.0 / period, adjust=False).mean()

    plus_di  = 100.0 * smooth_pd / atr.replace(0, float('nan'))
    minus_di = 100.0 * smooth_md / atr.replace(0, float('nan'))
    di_sum   = (plus_di + minus_di).replace(0, float('nan'))
    dx  = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()

    return adx, plus_di, minus_di


def _stochastic_series(
    high: pd.Series, low: pd.Series, close: pd.Series, k_period: int, d_period: int
) -> tuple[pd.Series, pd.Series]:
    """Stochastic Oscillator — restituisce (%K, %D)."""
    lowest  = low.rolling(window=k_period).min()
    highest = high.rolling(window=k_period).max()
    denom   = (highest - lowest).replace(0, float('nan'))
    k = 100.0 * (close - lowest) / denom
    d = k.rolling(window=d_period).mean()
    return k, d


def _cci_series(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int
) -> pd.Series:
    """Commodity Channel Index."""
    typical  = (high + low + close) / 3.0
    sma_tp   = typical.rolling(window=period).mean()
    mean_dev = typical.rolling(window=period).apply(
        lambda x: float(abs(x - x.mean()).mean()), raw=True
    )
    return (typical - sma_tp) / (0.015 * mean_dev.replace(0, float('nan')))


# ---- Indicators requiring Volume ----

def _obv_series(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On Balance Volume."""
    delta  = close.diff()
    sign   = delta.apply(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
    return (volume * sign).fillna(0).cumsum()


def _atr_series(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Average True Range (smoothing di Wilder)."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# ---- Config validation + topological ordering ----

def _validate_and_order(nodes: list[dict]) -> list[dict]:
    """
    Valida i nodi e li restituisce in ordine topologico sui `source`.

    Solleva IndicatorConfigError per: id duplicato/mancante, kind sconosciuto,
    kind OHLC con source ≠ "price", source inesistente, ciclo o profondità
    eccessiva.
    """
    by_id: dict[str, dict] = {}
    for node in nodes:
        node_id = node.get("id")
        kind    = node.get("kind")
        if not node_id or node_id in by_id:
            raise IndicatorConfigError(f"id nodo mancante o duplicato: {node_id!r}")
        if kind not in VALID_KINDS:
            raise IndicatorConfigError(f"kind sconosciuto: {kind!r}")
        by_id[node_id] = node

    for node in nodes:
        kind   = node["kind"]
        source = node.get("source", BASE_PRICE)
        if kind in PRICE_ONLY_KINDS and source != BASE_PRICE:
            raise IndicatorConfigError(
                f"il kind '{kind}' richiede source='price' (trovato {source!r})"
            )
        if kind == "volume" and source != BASE_VOLUME:
            raise IndicatorConfigError(
                f"il kind 'volume' richiede source='volume' (trovato {source!r})"
            )
        if source not in BASE_SOURCES and source not in by_id:
            raise IndicatorConfigError(f"source inesistente: {source!r}")

    return _topo_sort(nodes, by_id)


def _topo_sort(nodes: list[dict], by_id: dict[str, dict]) -> list[dict]:
    """Ordina i nodi per dipendenza (Kahn). Solleva su ciclo o profondità > cap."""
    depth: dict[str, int] = {}

    def node_depth(node_id: str, seen: frozenset) -> int:
        if node_id in seen:
            raise IndicatorConfigError("ciclo rilevato nei source degli indicatori")
        if node_id in depth:
            return depth[node_id]
        source = by_id[node_id].get("source", BASE_PRICE)
        d = 0 if source in BASE_SOURCES else 1 + node_depth(source, seen | {node_id})
        if d > MAX_NODE_DEPTH:
            raise IndicatorConfigError(f"profondità albero indicatori > {MAX_NODE_DEPTH}")
        depth[node_id] = d
        return d

    for node in nodes:
        node_depth(node["id"], frozenset())

    return sorted(nodes, key=lambda n: depth[n["id"]])


# ---- Per-node computation ----

def _compute_node(node: dict, base: dict, primary: dict) -> dict:
    """
    Calcola le serie di un singolo nodo. Restituisce {suffix: pd.Series}, dove
    la chiave "" è la serie primaria. `base` ha le serie OHLCV; `primary` mappa
    id-nodo → serie primaria già calcolata (per i source = id nodo).
    """
    kind   = node["kind"]
    params = node.get("params", {})
    source = node.get("source", BASE_PRICE)

    if kind in SERIES_TRANSFORM_KINDS:
        src = _resolve_source_series(source, base, primary)
        period = int(params.get("period", 20))
        if kind == "ema":
            return {"": _ema_series(src, period)}
        if kind == "sma":
            return {"": _sma_series(src, period)}
        return {"": _roc_series(src, period)}

    return _compute_ohlc_node(kind, params, base)


def _bb_node(params: dict, base: dict) -> dict:
    """Bande di Bollinger: media mobile piu' due bande a distanza di N deviazioni."""
    upper, mid, lower = _bollinger_series(
        base["close"], int(params.get("period", 20)), float(params.get("stddev", 2.0))
    )
    return {"": mid, "upper": upper, "lower": lower}


def _macd_node(params: dict, base: dict) -> dict:
    """MACD: linea, segnale e istogramma."""
    line, signal, hist = _macd_series(
        base["close"], int(params.get("fast", 12)), int(params.get("slow", 26)),
        int(params.get("signal", 9)),
    )
    return {"": line, "signal": signal, "hist": hist}


def _adx_node(params: dict, base: dict) -> dict:
    """ADX con le due direzionali."""
    adx, piu, meno = _adx_series(
        base["high"], base["low"], base["close"], int(params.get("period", 14))
    )
    return {"": adx, "plus_di": piu, "minus_di": meno}


def _stoch_node(params: dict, base: dict) -> dict:
    """Stocastico: %K e %D."""
    k, d = _stochastic_series(
        base["high"], base["low"], base["close"],
        int(params.get("k_period", 14)), int(params.get("d_period", 3)),
    )
    return {"": k, "d": d}


# Chi calcola cosa. Una tabella invece di una catena di `if`: aggiungere un
# indicatore diventa aggiungere una riga, e nessuno puo' dimenticare un ramo.
CALCOLO_PER_KIND = {
    "bb": _bb_node,
    "macd": _macd_node,
    "adx": _adx_node,
    "stoch": _stoch_node,
    "rsi": lambda p, b: {"": _rsi_series(b["close"], int(p.get("period", 14)))},
    "cci": lambda p, b: {"": _cci_series(b["high"], b["low"], b["close"],
                                         int(p.get("period", 20)))},
    "obv": lambda p, b: {"": _obv_series(b["close"], b["volume"])},
    "atr": lambda p, b: {"": _atr_series(b["high"], b["low"], b["close"],
                                         int(p.get("period", 14)))},
    "volume": lambda p, b: {"": b["volume"]},
}


def _compute_ohlc_node(kind: str, params: dict, base: dict) -> dict:
    """Calcola i kind che lavorano sulle serie base OHLCV (source='price')."""
    calcolo = CALCOLO_PER_KIND.get(kind)
    if calcolo is None:
        raise IndicatorConfigError(f"kind senza calcolo: {kind!r}")
    return calcolo(params, base)


def _resolve_source_series(source: str, base: dict, primary: dict) -> pd.Series:
    """Serie 1-D di una sorgente: price→close, volume→volume, altrimenti nodo padre."""
    if source == BASE_PRICE:
        return base["close"]
    if source == BASE_VOLUME:
        return base["volume"]
    return primary[source]


def valida(config: dict | None) -> list[dict]:
    """Controlla una configurazione senza calcolarla, e ritorna i nodi in ordine.

    Serve a chi la deve SALVARE: `compute` su un elenco di barre vuoto esce
    subito, quindi non direbbe niente su una configurazione rotta, che
    finirebbe nel file per rompere il grafico a ogni apertura.
    """
    nodi = _normalized_config(config).get("nodes", [])
    return _validate_and_order(nodi) if nodi else []


# ---- Main entry point ----

def compute(bars: list, config: dict | None) -> dict:
    """
    Calcola gli indicatori descritti da `config` sulle barre OHLCV.

    bars   — lista di OHLCV dataclass o dict con campi
             {timestamp, open, high, low, close, volume}
    config — {"nodes": [IndicatorNode, ...]}; nodi con enabled=False sono ignorati.

    Ritorna Record<str, list[{t, v}]>: chiave = id nodo (serie primaria) o
    "id:suffix" (serie secondarie). Solleva IndicatorConfigError se la config
    non è valida.

    NB: vengono calcolati TUTTI i nodi, anche quelli con enabled=False; il flag
    `enabled` è una pura scelta di visibilità lato frontend (così attivare/
    disattivare un indicatore non richiede un nuovo /compute).
    """
    config = _normalized_config(config)
    nodes = config.get("nodes", [])
    if not bars or not nodes:
        return {}

    base, idx = _build_base_series(bars)
    ordered = _validate_and_order(nodes)

    output: dict[str, list[dict]] = {}
    primary: dict[str, pd.Series] = {}
    for node in ordered:
        series_map = _compute_node(node, base, primary)
        primary[node["id"]] = series_map[""]
        for suffix, series in series_map.items():
            key = node["id"] if suffix == "" else f"{node['id']}:{suffix}"
            output[key] = [_to_tv(ts, v) for ts, v in zip(idx, series, strict=True)]

    return output


def _build_base_series(bars: list) -> tuple[dict, pd.DatetimeIndex]:
    """Estrae le serie base OHLCV dalle barre. Ritorna (dict serie, indice)."""
    def _val(bar, key: str):
        # NB: niente `or`, altrimenti un valore legittimo 0.0 (es. volume=0)
        # verrebbe scartato come falsy.
        if isinstance(bar, dict):
            return bar.get(key)
        return getattr(bar, key, None)

    idx = pd.to_datetime([_val(b, "timestamp") for b in bars], utc=True)
    base = {
        "close":  pd.Series([_val(b, "close")  for b in bars], index=idx, dtype=float),
        "high":   pd.Series([_val(b, "high")   for b in bars], index=idx, dtype=float),
        "low":    pd.Series([_val(b, "low")    for b in bars], index=idx, dtype=float),
        "volume": pd.Series([_val(b, "volume") for b in bars], index=idx, dtype=float),
    }
    return base, idx
