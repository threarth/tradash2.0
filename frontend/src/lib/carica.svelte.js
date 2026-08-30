/**
 * carica.svelte.js — chiedere un dato al backend, con i tre stati che ne seguono.
 * feat (Blocco 4): il ciclo caricamento/errore/dato scritto una volta sola.
 *
 * Tre pagine che ripetono lo stesso `try/catch` sono tre modi diversi di
 * dimenticarsi un caso. Qui il caso non si dimentica: finche' non arriva il
 * dato lo stato dice "sto caricando", e se arriva un errore lo conserva col
 * messaggio che il backend ha scritto.
 */

/**
 * Costruisce una richiesta ricaricabile.
 * `richiesta` e' una funzione asincrona che ritorna il dato.
 */
export function richiedi(richiesta) {
    let dato = $state(null);
    let errore = $state(null);
    let inCorso = $state(false);

    async function ricarica() {
        inCorso = true;
        errore = null;
        try {
            dato = await richiesta();
        } catch (problema) {
            errore = problema;
        } finally {
            inCorso = false;
        }
    }

    return {
        get dato() { return dato; },
        get errore() { return errore; },
        get inCorso() { return inCorso; },
        /** Vero solo mentre si aspetta il PRIMO dato: un ricarica non svuota la pagina. */
        get primoCaricamento() { return inCorso && dato === null; },
        ricarica
    };
}
