/**
 * preferenze.js — l'unico punto da cui si scrive nel browser.
 * feat (Blocco 10): il «Rifiuta» del banner deve rifiutare qualcosa di vero.
 *
 * Prima ogni preferenza scriveva da sola in `localStorage`: quattro punti nel
 * codice, quattro `try/catch` uguali, e nessun posto da cui poterle spegnere
 * tutte. Con un banner che offre «Rifiuta» quello sarebbe diventato un pulsante
 * finto — e dichiarare una scelta che non esiste e' peggio che non offrirla.
 *
 * Adesso passano tutte di qui, e qui c'e' l'interruttore.
 *
 * ## Cosa succede se rifiuti
 *
 * Le preferenze continuano a funzionare **per la durata della pagina**: il tema
 * si cambia, le sezioni si aprono e si chiudono. Semplicemente non sopravvivono
 * alla chiusura della scheda, perche' vivono in memoria invece che su disco. E
 * quello che c'era gia' viene cancellato subito.
 *
 * ## Cosa NON si puo' rifiutare
 *
 * Il cookie di sessione. Non passa di qui perche' non e' nostro da scrivere: lo
 * mette il server, e senza non si resta connessi. Il banner lo dice.
 */

/** Le chiavi che questo modulo gestisce. L'elenco serve a poterle cancellare
 *  tutte quando il consenso viene negato — e a tenerlo allineato con quello che
 *  il backend dichiara nell'informativa. */
export const CHIAVI = {
    TEMA: "tradash-tema",
    GLOSSARIO: "tradash-glossario",
    PANNELLI: "tradash-pannelli",
    SEZIONI: "tradash-sezioni"
};

// `null` finche' l'utente non ha deciso. Prima della decisione ci si comporta
// come se avesse rifiutato: chiedere il permesso e intanto scrivere sarebbe
// chiederlo per finta.
let consentito = null;

// Il ripiego: le preferenze della sessione in corso, che muoiono con la pagina.
const volatili = new Map();

/** Il consenso e' stato dato? `null` significa «non ha ancora deciso». */
export function consenso() {
    return consentito;
}

/**
 * Registra la decisione. Con `false` cancella subito cio' che era stato salvato:
 * un rifiuto che lascia sul posto quello di ieri non e' un rifiuto.
 */
export function impostaConsenso(valore) {
    consentito = valore;
    if (valore === false) dimentica();
    return consentito;
}

/** Cancella dal browser tutte le chiavi che questo modulo gestisce. */
export function dimentica() {
    for (const chiave of Object.values(CHIAVI)) {
        try {
            localStorage.removeItem(chiave);
        } catch {
            // Niente da cancellare, o accesso negato: in entrambi i casi il
            // risultato che ci interessa — niente su disco — e' gia' vero.
        }
    }
}

/** Legge una preferenza. `predefinito` quando non c'e', o non e' leggibile. */
export function leggi(chiave, predefinito = null) {
    if (consentito !== true) {
        return volatili.has(chiave) ? volatili.get(chiave) : predefinito;
    }
    try {
        const grezzo = localStorage.getItem(chiave);
        return grezzo === null ? predefinito : grezzo;
    } catch {
        // Finestra privata o permessi negati: si continua senza ricordare.
        return predefinito;
    }
}

/** Scrive una preferenza, dove il consenso permette di scriverla. */
export function scrivi(chiave, valore) {
    if (consentito !== true) {
        volatili.set(chiave, valore);
        return;
    }
    try {
        localStorage.setItem(chiave, valore);
    } catch {
        // Un browser che non lascia scrivere non deve rompere la pagina: si
        // perde il ricordo, non la preferenza.
        volatili.set(chiave, valore);
    }
}

/** Come `leggi`, per le preferenze che sono oggetti. */
export function leggiJson(chiave, predefinito) {
    const grezzo = leggi(chiave, null);
    if (grezzo === null) return predefinito;
    try {
        return JSON.parse(grezzo);
    } catch {
        // Un valore corrotto — scritto a mano, o da una versione vecchia — non
        // deve impedire alla pagina di aprirsi.
        return predefinito;
    }
}

/** Come `scrivi`, per le preferenze che sono oggetti. */
export function scriviJson(chiave, valore) {
    scrivi(chiave, JSON.stringify(valore));
}
