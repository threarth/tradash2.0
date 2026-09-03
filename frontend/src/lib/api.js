/**
 * api.js — l'unico punto da cui il frontend parla col backend.
 * feat (Blocco 4): un solo inviluppo da scartare, un solo errore da gestire.
 *
 * Ogni risposta del backend ha la forma `{success, data, error}`. Scartarla in
 * venti posti diversi significa venti modi diversi di sbagliare: qui si scarta
 * una volta, e chi chiama riceve `data` oppure un'eccezione con dentro il
 * motivo che il backend ha scritto.
 *
 * Nessuna chiamata parte da sola: le funzioni si invocano quando qualcuno
 * chiede qualcosa (regola 2).
 */

// Prefisso di tutte le API. Relativo apposta: in sviluppo lo gira il proxy di
// Vite, in uso reale Flask serve anche il frontend e i due coincidono.
const BASE_API = "/api";

/** Errore che arriva dal backend, col messaggio che ha scritto lui. */
export class ErroreApi extends Error {
    constructor(messaggio, stato) {
        super(messaggio);
        this.name = "ErroreApi";
        this.stato = stato;
    }
}

/**
 * Esegue una chiamata e ritorna il solo `data`.
 * Solleva `ErroreApi` se il backend dice di no o se la rete non risponde.
 */
async function chiama(percorso, opzioni = {}) {
    let risposta;
    try {
        risposta = await fetch(`${BASE_API}${percorso}`, {
            headers: { "Content-Type": "application/json" },
            ...opzioni
        });
    } catch (errore) {
        // Il backend spento e' il caso piu' frequente in sviluppo: dirlo con
        // parole sue vale piu' che ripetere "Failed to fetch".
        throw new ErroreApi(`il backend non risponde (${errore.message})`, 0);
    }

    let corpo;
    try {
        corpo = await risposta.json();
    } catch {
        throw new ErroreApi(
            `risposta non leggibile da ${percorso} (HTTP ${risposta.status})`,
            risposta.status
        );
    }

    if (!corpo.success) {
        throw new ErroreApi(corpo.error || `richiesta rifiutata (HTTP ${risposta.status})`,
            risposta.status);
    }
    return corpo.data;
}

/** Compone una query string, saltando i parametri non valorizzati. */
function query(parametri) {
    const pieni = Object.entries(parametri ?? {}).filter(
        ([, valore]) => valore !== undefined && valore !== null && valore !== ""
    );
    return pieni.length ? `?${new URLSearchParams(pieni)}` : "";
}

const corpoJson = (metodo, dati) => ({ method: metodo, body: JSON.stringify(dati) });

export const api = {
    // --- universo ---
    universo: (filtri) => chiama(`/universe${query(filtri)}`),
    universoStato: () => chiama("/universe/stato"),
    universoCostruisci: (forzato) => chiama(`/universe/build${query({ force: forzato ? 1 : "" })}`,
        { method: "POST" }),

    // --- watchlist ---
    watchlist: (filtri) => chiama(`/watchlist${query(filtri)}`),
    watchlistAggiungi: (testo, tag) => chiama("/watchlist", corpoJson("POST", { testo, tag })),
    watchlistRimuovi: (simboli) => chiama("/watchlist", corpoJson("DELETE", { simboli })),
    watchlistModifica: (dati) => chiama("/watchlist", corpoJson("PATCH", dati)),
    watchlistAttributi: (simbolo, attributi) =>
        chiama(`/watchlist/${encodeURIComponent(simbolo)}`, corpoJson("PATCH", attributi)),
    esporta: () => chiama("/watchlist/esporta"),
    importa: (dati) => chiama("/watchlist/importa", corpoJson("POST", dati)),
    prompt: (simboli) => chiama(`/watchlist/prompt${query({ simboli })}`),
    promptScoperta: (temi) => chiama(`/watchlist/prompt/scoperta${query({ temi })}`),
    promptRevisione: () => chiama("/watchlist/prompt/revisione"),
    tagElenco: () => chiama("/watchlist/tag"),
    tagCrea: (etichetta, padre) => chiama("/watchlist/tag", corpoJson("POST", { etichetta, padre })),
    tagElimina: (nome, cascata) =>
        chiama(`/watchlist/tag/${encodeURIComponent(nome)}${query({ cascata: cascata ? 1 : "" })}`,
            { method: "DELETE" }),
    categorieFreschezza: () => chiama("/watchlist/da-aggiornare"),
    daAggiornare: (categoria) =>
        chiama(`/watchlist/da-aggiornare/${encodeURIComponent(categoria)}`),
    storico: (limit) => chiama(`/watchlist/storico${query({ limit })}`),

    // --- scheda di un titolo ---
    titolo: (simbolo) => chiama(`/titolo/${encodeURIComponent(simbolo)}`),
    titoloPrezzi: (simbolo, intervallo) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/prezzi${query({ intervallo })}`),
    fondamentali: (simbolo, asOf, periodicita) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/fondamentali${query({ as_of: asOf, periodicita })}`),
    filings: (simbolo, asOf) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/filings${query({ as_of: asOf })}`),
    news: (simbolo, asOf) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/news${query({ as_of: asOf })}`),
    filingDaSalvare: (simbolo) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/filing-da-salvare`),
    catalogoMetriche: (simbolo) => chiama(`/titolo/${encodeURIComponent(simbolo)}/metriche`),
    metrica: (simbolo, nome) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/metriche/${encodeURIComponent(nome)}`),
    segnali: (simbolo, asOf) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/segnali${query({ as_of: asOf })}`),
    ricostruzione: (simbolo, asOf) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/ricostruzione${query({ as_of: asOf })}`),
    rischio: (simbolo) => chiama(`/titolo/${encodeURIComponent(simbolo)}/rischio`),
    salute: (simbolo, asOf) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/salute${query({ as_of: asOf })}`),
    simulatore: (simbolo, da, capitale, base) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/simulatore${query({ da, capitale, base })}`),
    titoloGrafico: (simbolo) => chiama(`/titolo/${encodeURIComponent(simbolo)}/grafico`),
    titoloSalvaGrafico: (simbolo, configurazione) =>
        chiama(`/titolo/${encodeURIComponent(simbolo)}/grafico`,
            corpoJson("PUT", configurazione)),

    // --- analisi ---
    metodiAnalisi: () => chiama("/analisi"),
    eseguiAnalisi: (metodo, simbolo) =>
        chiama(`/analisi/${encodeURIComponent(metodo)}/${encodeURIComponent(simbolo)}`,
            { method: "POST" }),
    referti: (simbolo, metodo) => chiama(`/analisi/referti${query({ symbol: simbolo, metodo })}`),

    // --- scanner ---
    scannerCriteri: () => chiama("/scanner/criteri"),
    scannerAvvia: (richiesta) => chiama("/scanner", corpoJson("POST", richiesta)),
    scannerEsito: (runId) => chiama(`/scanner/${encodeURIComponent(runId)}`),

    // --- glossario ---
    glossario: () => chiama("/glossario"),

    // --- lavori e chiamate: la regola 1 vista dal frontend ---
    lavoriAttivi: () => chiama("/ops/active"),
    processo: () => chiama("/ops/processo"),
    lavoriStorici: () => chiama("/ops/history"),
    fermaLavoro: (runId) => chiama(`/ops/stop/${encodeURIComponent(runId)}`, { method: "POST" }),
    chiamate: (filtri) => chiama(`/calls${query(filtri)}`),
    chiamateRiepilogo: () => chiama("/calls/summary")
};
