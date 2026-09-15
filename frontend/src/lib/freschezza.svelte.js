/**
 * freschezza.svelte.js — cosa e' invecchiato, chiesto una volta.
 * feat: l'allarme al posto dello scheduler.
 *
 * ## Perche' NON e' un battito
 *
 * I lavori in corso si chiedono ogni due secondi, perche' cambiano ogni due
 * secondi. La freschezza no: cambia una volta al giorno, e interrogarla di
 * continuo sarebbe traffico per una risposta che si sa gia'.
 *
 * Si chiede all'apertura, e si richiede quando qualcosa puo' averla cambiata —
 * cioe' quando un lavoro finisce. La decisione di ricostruire resta tua: questo
 * modulo mostra un numero, non preme niente.
 */
import { api } from "./api.js";

class Freschezza {
    /** Quante cose sono vecchie adesso. Zero e' un'informazione anche lui. */
    quanti = $state(0);
    vecchi = $state([]);
    tutti = $state([]);
    nota = $state("");
    aperto = $state(false);
    letta = $state(false);

    /** Chiede al backend cosa e' vecchio. Legge SQLite e un file: non costa. */
    async carica() {
        try {
            const dati = await api.freschezza();
            this.quanti = dati.quanti;
            this.vecchi = dati.vecchi;
            this.tutti = dati.tutti;
            this.nota = dati.nota;
            this.letta = true;
        } catch {
            // Il backend spento o la sessione scaduta: l'allarme resta muto
            // invece di diventare un secondo errore sopra al primo.
            this.letta = false;
        }
    }

    alterna() {
        this.aperto = !this.aperto;
    }
}

export const freschezza = new Freschezza();
