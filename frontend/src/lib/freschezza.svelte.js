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
    /** Quali aggiornamenti sono stati appena chiesti, per non chiederli due volte. */
    inCorso = $state(new Set());
    errore = $state(null);

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

    /**
     * Fa partire l'aggiornamento di una riga. Non decide da sola quale: prende
     * l'indirizzo che il backend ha dichiarato accanto a quella riga.
     *
     * `force=1` perche' premere un pulsante E' la decisione: senza, il guard di
     * freschezza potrebbe rispondere «gia' fresco, salto» proprio mentre tu hai
     * chiesto di rifarlo.
     */
    async avvia(riga) {
        if (!riga.endpoint || this.inCorso.has(riga.categoria)) return;

        this.inCorso.add(riga.categoria);
        this.inCorso = new Set(this.inCorso);
        this.errore = null;
        try {
            await api.avviaAggiornamento(riga.endpoint);
            // Il lavoro gira nel registro: la pastiglia dei lavori lo mostra, e
            // la freschezza si rilegge da sola quando finisce (vedi Layout).
        } catch (problema) {
            this.errore = `${riga.etichetta}: ${problema.message}`;
        } finally {
            this.inCorso.delete(riga.categoria);
            this.inCorso = new Set(this.inCorso);
        }
    }
}

export const freschezza = new Freschezza();
