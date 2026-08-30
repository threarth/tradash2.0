/**
 * rilevatore.js — riconoscere i termini del glossario dentro un testo.
 * feat (Blocco 5): il meccanismo del vecchio tradash, e nient'altro.
 *
 * Qui non c'e' stato, non ci sono chiamate, non c'e' Svelte: solo funzioni che
 * da un elenco di termini e una stringa ricavano i pezzi da sottolineare. E'
 * la stessa separazione che nel backend tiene `domain/` senza I/O — cosi' si
 * puo' testare senza montare niente.
 *
 * Da ogni termine si ricavano TRE forme, tutte verso lo stesso id:
 *
 *   "Relative Strength (RS)"  ->  "relative strength (rs)", "relative strength", "rs"
 *
 * cosi' il testo viene riconosciuto sia per esteso sia con la sigla.
 */

// Sotto le due lettere una "parola" e' rumore: aggancerebbe mezzo testo.
export const LUNGHEZZA_MINIMA = 2;

/** Rende letterale un testo dentro un'espressione regolare. */
function letterale(testo) {
    return testo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * La mappa parola → id del termine.
 * Chi arriva prima vince: un termine successivo non ruba una parola gia' presa.
 */
export function costruisciIndice(termini) {
    const indice = new Map();

    const aggiungi = (parola, id) => {
        if (!parola || parola.length < LUNGHEZZA_MINIMA) return;
        const normalizzata = parola.toLowerCase();
        if (!indice.has(normalizzata)) indice.set(normalizzata, id);
    };

    for (const termine of termini) {
        const etichetta = termine.label ?? "";
        aggiungi(etichetta, termine.id);

        const apertura = etichetta.indexOf(" (");
        if (apertura <= 0) continue;

        aggiungi(etichetta.slice(0, apertura).trim(), termine.id);

        const chiusura = etichetta.indexOf(")", apertura);
        if (chiusura <= 0) continue;

        // Solo le sigle: EPS, MACD, FCF, RS. Dentro le parentesi ci puo' stare
        // anche una traduzione — "Volume Anomaly (Anomalia di Volume)" — e
        // quella aggancerebbe testo italiano corrente.
        const dentro = etichetta.slice(apertura + 2, chiusura).trim();
        if (/^[A-Z][A-Z0-9]+$/.test(dentro)) aggiungi(dentro, termine.id);
    }

    return indice;
}

/**
 * L'espressione che riconosce una qualunque parola dell'indice, intera.
 * Le piu' lunghe per prime: senza, "Free Cash Flow" verrebbe spezzato in
 * "Cash" e "Flow", che sono termini anche loro.
 */
export function costruisciSchema(parole) {
    if (parole.length === 0) return null;
    const ordinate = [...parole].sort((a, b) => b.length - a.length).map(letterale);
    return new RegExp(`(?<![\\p{L}\\p{N}_])(${ordinate.join("|")})(?![\\p{L}\\p{N}_])`, "giu");
}

/**
 * Spezza un testo in pezzi; quelli riconosciuti portano l'id del termine.
 * Ritorna `null` quando non c'e' niente da riconoscere, cosi' chi chiama puo'
 * stampare il testo com'e' invece di montare un componente per pezzo.
 */
export function segmenta(testo, indice, schema) {
    if (!testo || !schema || indice.size === 0) return null;

    // Copia dell'espressione: `lastIndex` e' stato mutabile, e condividerlo
    // fra due chiamate fa saltare pezzi di testo in modo non riproducibile.
    const ricerca = new RegExp(schema.source, schema.flags);
    const pezzi = [];
    let ultimo = 0;
    let trovato;

    while ((trovato = ricerca.exec(testo)) !== null) {
        if (trovato.index > ultimo) pezzi.push({ testo: testo.slice(ultimo, trovato.index) });
        pezzi.push({ testo: trovato[0], id: indice.get(trovato[0].toLowerCase()) });
        ultimo = trovato.index + trovato[0].length;
    }

    if (pezzi.length === 0) return null;
    if (ultimo < testo.length) pezzi.push({ testo: testo.slice(ultimo) });
    return pezzi;
}
