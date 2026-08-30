/**
 * indicators.ts — metadati degli indicatori e helper sull'albero dei nodi.
 * feat (Blocco 6): copiato dal vecchio tradash, dove era TypeScript senza React.
 *
 * Per ogni `kind` dice: etichetta, come si disegna (sovrapposto al prezzo /
 * pannello dedicato / barre di volume), quali serie produce, quali parametri
 * accetta, su quale sorgente puo' attaccarsi e con quali valori di partenza.
 * Lo usano il pannello delle impostazioni e il disegno del grafico, e il fatto
 * che sia UNO solo e' cio' che impedisce ai due di divergere.
 *
 * I tipi vivevano in `api-client.ts`, che qui non esiste: sono dichiarati sotto.
 */

// I tipi di indicatore, gli stessi che il backend accetta in `VALID_KINDS`.
export type IndicatorKind =
    | "ema" | "sma" | "roc"
    | "bb" | "rsi" | "macd" | "adx" | "stoch" | "cci" | "obv" | "atr"
    | "volume";

export interface IndicatorStyle {
    color?: string;
    strokeWidth?: number;
    colorUp?: string;     // volume: colore delle barre nei giorni positivi
    colorDown?: string;   // volume: colore delle barre nei giorni negativi
}

/**
 * Un nodo dell'albero. `source` e' "price", "volume", oppure l'id di un altro
 * nodo: e' cosi' che una media mobile puo' stare sopra il volume o sopra l'ATR.
 */
export interface IndicatorNode {
    id: string;
    kind: IndicatorKind;
    source: string;
    params: Record<string, number>;
    style: IndicatorStyle;
    enabled: boolean;
}

export interface ChartConfig {
    nodes: IndicatorNode[];
}

// Sorgenti base implicite (radici dell'albero), allineate al backend.
export const BASE_PRICE = "price";
export const BASE_VOLUME = "volume";

export type ValueFormat = "price" | "int" | "pct" | "vol" | "dec1" | "dec2";

export interface ParamDef {
    key: string;
    label: string;
    min: number;
    max: number;
    step?: number;
}

// Una serie prodotta da un nodo. suffix "" = serie primaria (chiave = id nodo);
// le secondarie hanno chiave "id:suffix". `color` fissa il colore delle
// secondarie (la primaria usa node.style.color). `chart` distingue linea/barra.
export interface SeriesDef {
    suffix: string;
    label: string;
    color?: string;
    dash?: boolean;
    chart?: "line" | "bar";
}

export interface ReferenceLineDef {
    y: number;
    tone?: "loss" | "profit" | "muted";
}

export interface PanelDef {
    height: number;
    yDomain?: [number | "auto", number | "auto"];
    yTicks?: number[];
    refLines?: ReferenceLineDef[];
    valueFormat: ValueFormat;
}

export interface KindMeta {
    label: string;
    render: "overlay" | "panel" | "volume";
    series: SeriesDef[];
    params: ParamDef[];
    sourceConstraint: "price" | "volume" | "any";
    defaultColor: string;
    defaultParams: Record<string, number>;
    panel?: PanelDef;
    hasStyle: boolean;
}

const PERIOD: ParamDef = { key: "period", label: "Periodo", min: 2, max: 500 };

export const KIND_META: Record<IndicatorKind, KindMeta> = {
    ema: {
        label: "EMA", render: "overlay", hasStyle: true,
        series: [{ suffix: "", label: "EMA" }],
        params: [{ ...PERIOD, max: 200 }], sourceConstraint: "any",
        defaultColor: "#3b82f6", defaultParams: { period: 50 },
    },
    sma: {
        label: "SMA", render: "overlay", hasStyle: true,
        series: [{ suffix: "", label: "SMA" }],
        params: [{ ...PERIOD }], sourceConstraint: "any",
        defaultColor: "#8b5cf6", defaultParams: { period: 200 },
    },
    bb: {
        label: "Bollinger Bands", render: "overlay", hasStyle: true,
        series: [
            { suffix: "", label: "BB mid" },
            { suffix: "upper", label: "BB upper", dash: true },
            { suffix: "lower", label: "BB lower", dash: true },
        ],
        params: [
            { key: "period", label: "Periodo", min: 5, max: 50 },
            { key: "stddev", label: "Dev. std", min: 0.5, max: 4, step: 0.1 },
        ],
        sourceConstraint: "price",
        defaultColor: "#06b6d4", defaultParams: { period: 20, stddev: 2.0 },
    },
    rsi: {
        label: "RSI", render: "panel", hasStyle: true,
        series: [{ suffix: "", label: "RSI" }],
        params: [{ ...PERIOD, max: 50 }], sourceConstraint: "price",
        defaultColor: "#10b981", defaultParams: { period: 14 },
        panel: {
            height: 100, yDomain: [0, 100], yTicks: [30, 50, 70], valueFormat: "dec1",
            refLines: [{ y: 70, tone: "loss" }, { y: 30, tone: "profit" }],
        },
    },
    macd: {
        label: "MACD", render: "panel", hasStyle: true,
        series: [
            { suffix: "", label: "MACD" },
            { suffix: "signal", label: "Signal", color: "#f97316" },
            { suffix: "hist", label: "Histogram", chart: "bar" },
        ],
        params: [
            { key: "fast", label: "EMA veloce", min: 2, max: 50 },
            { key: "slow", label: "EMA lenta", min: 5, max: 100 },
            { key: "signal", label: "Signal", min: 2, max: 30 },
        ],
        sourceConstraint: "price",
        defaultColor: "#3b82f6", defaultParams: { fast: 12, slow: 26, signal: 9 },
        panel: { height: 120, refLines: [{ y: 0, tone: "muted" }], valueFormat: "dec2" },
    },
    adx: {
        label: "ADX", render: "panel", hasStyle: true,
        series: [
            { suffix: "", label: "ADX" },
            { suffix: "plus_di", label: "+DI", color: "#22c55e" },
            { suffix: "minus_di", label: "-DI", color: "#ef4444" },
        ],
        params: [{ ...PERIOD, min: 5, max: 50 }], sourceConstraint: "price",
        defaultColor: "#f97316", defaultParams: { period: 14 },
        panel: {
            height: 100, yDomain: [0, 100], yTicks: [20, 40, 60, 80], valueFormat: "dec1",
            refLines: [{ y: 25, tone: "muted" }],
        },
    },
    stoch: {
        label: "Stochastic", render: "panel", hasStyle: true,
        series: [
            { suffix: "", label: "%K" },
            { suffix: "d", label: "%D", color: "#e879f9", dash: true },
        ],
        params: [
            { key: "k_period", label: "Periodo %K", min: 2, max: 50 },
            { key: "d_period", label: "Smoothing %D", min: 1, max: 10 },
        ],
        sourceConstraint: "price",
        defaultColor: "#a855f7", defaultParams: { k_period: 14, d_period: 3 },
        panel: {
            height: 100, yDomain: [0, 100], yTicks: [20, 50, 80], valueFormat: "dec1",
            refLines: [{ y: 80, tone: "loss" }, { y: 20, tone: "profit" }],
        },
    },
    cci: {
        label: "CCI", render: "panel", hasStyle: true,
        series: [{ suffix: "", label: "CCI" }],
        params: [{ ...PERIOD, min: 5, max: 50 }], sourceConstraint: "price",
        defaultColor: "#14b8a6", defaultParams: { period: 20 },
        panel: {
            height: 100, valueFormat: "dec1",
            refLines: [{ y: 100, tone: "loss" }, { y: 0, tone: "muted" }, { y: -100, tone: "profit" }],
        },
    },
    roc: {
        label: "ROC", render: "panel", hasStyle: true,
        series: [{ suffix: "", label: "ROC" }],
        params: [{ ...PERIOD, min: 1, max: 50 }], sourceConstraint: "any",
        defaultColor: "#f43f5e", defaultParams: { period: 12 },
        panel: { height: 90, valueFormat: "pct", refLines: [{ y: 0, tone: "muted" }] },
    },
    obv: {
        label: "OBV", render: "panel", hasStyle: true,
        series: [{ suffix: "", label: "OBV" }],
        params: [], sourceConstraint: "price",
        defaultColor: "#ec4899", defaultParams: {},
        panel: { height: 85, valueFormat: "vol" },
    },
    atr: {
        label: "ATR", render: "panel", hasStyle: true,
        series: [{ suffix: "", label: "ATR" }],
        params: [{ ...PERIOD, max: 100 }], sourceConstraint: "price",
        defaultColor: "#eab308", defaultParams: { period: 14 },
        panel: { height: 100, valueFormat: "dec1" },
    },
    volume: {
        label: "Volume", render: "volume", hasStyle: false,
        series: [{ suffix: "", label: "Volume", chart: "bar" }],
        params: [], sourceConstraint: "volume",
        defaultColor: "#94a3b8", defaultParams: {},
        panel: { height: 85, valueFormat: "vol" },
    },
};

export const ALL_KINDS = Object.keys(KIND_META) as IndicatorKind[];

// Ordine di apparizione dei sub-panel sotto al grafico prezzo.
const PANEL_KIND_ORDER: IndicatorKind[] =
    ["volume", "rsi", "adx", "stoch", "cci", "roc", "obv", "macd", "atr"];


/** Crea un nuovo nodo con id univoco e default del kind. */
export function makeNode(kind: IndicatorKind, source: string): IndicatorNode {
    const meta = KIND_META[kind];
    const style: IndicatorNode["style"] = meta.hasStyle
        ? { color: meta.defaultColor, strokeWidth: 1.5 }
        : {};
    if (kind === "volume") {
        style.colorUp = "#10b981";
        style.colorDown = "#f43f5e";
    }
    return {
        id: crypto.randomUUID(),
        kind,
        source,
        params: { ...meta.defaultParams },
        style,
        enabled: true,
    };
}

export function nodesById(config: ChartConfig): Record<string, IndicatorNode> {
    const map: Record<string, IndicatorNode> = {};
    for (const n of config.nodes) map[n.id] = n;
    return map;
}

/** Risale la catena dei source fino alla radice e ne restituisce il panel id. */
function resolveRootPanel(node: IndicatorNode, byId: Record<string, IndicatorNode>): string {
    const src = node.source;
    const parent = byId[src];
    if (parent) {
        const meta = KIND_META[parent.kind];
        if (meta.render === "panel" || meta.render === "volume") return parent.id;
        return resolveRootPanel(parent, byId);
    }
    if (src === BASE_VOLUME) {
        const vol = Object.values(byId).find((n) => n.kind === "volume");
        return vol ? vol.id : "price";
    }
    return "price";
}

/**
 * Panel in cui va disegnato il nodo: "price" (overlay sul grafico prezzo) oppure
 * l'id del nodo che possiede il sub-panel (volume, rsi, atr, …).
 */
export function panelIdOf(node: IndicatorNode, byId: Record<string, IndicatorNode>): string {
    const meta = KIND_META[node.kind];
    if (meta.render === "panel" || meta.render === "volume") return node.id;
    return resolveRootPanel(node, byId);
}

export interface ResolvedPanel {
    id: string;
    owner: IndicatorNode;        // nodo che possiede il panel (volume/rsi/…)
    children: IndicatorNode[];   // nodi overlay agganciati a questo panel (es. MA)
}

/**
 * Calcola i sub-panel da renderizzare, in ordine stabile, con i rispettivi figli.
 * Esclude gli overlay sul prezzo (quelli vanno nel grafico principale).
 */
export function resolvePanels(config: ChartConfig): ResolvedPanel[] {
    const byId = nodesById(config);
    const enabled = config.nodes.filter((n) => n.enabled);
    const owners = enabled.filter((n) => KIND_META[n.kind].render !== "overlay");

    const sorted = [...owners].sort((a, b) =>
        PANEL_KIND_ORDER.indexOf(a.kind) - PANEL_KIND_ORDER.indexOf(b.kind));

    return sorted.map((owner) => ({
        id: owner.id,
        owner,
        children: enabled.filter(
            (n) => KIND_META[n.kind].render === "overlay" && panelIdOf(n, byId) === owner.id,
        ),
    }));
}

/** Nodi overlay che vanno disegnati sul grafico prezzo. */
export function priceOverlays(config: ChartConfig): IndicatorNode[] {
    const byId = nodesById(config);
    return config.nodes.filter(
        (n) => n.enabled && KIND_META[n.kind].render === "overlay" && panelIdOf(n, byId) === "price",
    );
}

/** Chiavi delle serie prodotte da un nodo (id primaria, "id:suffix" secondarie). */
export function seriesKeys(node: IndicatorNode): { key: string; def: SeriesDef }[] {
    return KIND_META[node.kind].series.map((def) => ({
        key: def.suffix === "" ? node.id : `${node.id}:${def.suffix}`,
        def,
    }));
}

/** Etichetta leggibile di un nodo (kind + parametro principale). */
export function nodeLabel(node: IndicatorNode): string {
    const meta = KIND_META[node.kind];
    const p = node.params;
    if (node.kind === "macd") return `MACD ${p.fast}/${p.slow}/${p.signal}`;
    if (node.kind === "stoch") return `Stoch ${p.k_period}/${p.d_period}`;
    if (node.kind === "bb") return `BB ${p.period}/${p.stddev}`;
    if (typeof p.period === "number") return `${meta.label} ${p.period}`;
    return meta.label;
}

/** Opzioni sorgente valide per un kind, dati i nodi esistenti. */
export function sourceOptions(
    kind: IndicatorKind,
    config: ChartConfig,
    excludeId?: string,
): { value: string; label: string }[] {
    const meta = KIND_META[kind];
    if (meta.sourceConstraint === "price") return [{ value: BASE_PRICE, label: "Prezzo" }];
    if (meta.sourceConstraint === "volume") return [{ value: BASE_VOLUME, label: "Volume" }];

    // "any": prezzo, volume e tutte le serie dei nodi esistenti (no se stesso).
    const opts = [
        { value: BASE_PRICE, label: "Prezzo" },
        { value: BASE_VOLUME, label: "Volume" },
    ];
    for (const n of config.nodes) {
        if (n.id !== excludeId) opts.push({ value: n.id, label: nodeLabel(n) });
    }
    return opts;
}
