/**
 * sessione.svelte.js — chi sei, e cosa hai deciso sui cookie.
 * feat (Blocco 10): uno stato solo, chiesto una volta all'avvio.
 *
 * Non fa da solo nient'altro che una lettura all'apertura: sapere se sei dentro
 * o fuori e' la domanda che decide cosa mostrare, e senza risposta non si puo'
 * disegnare niente. Tutto il resto parte da un pulsante (regola 2).
 */
import { api } from "./api.js";
import { impostaConsenso } from "./preferenze.js";

class Sessione {
    connesso = $state(false);
    utente = $state(null);
    /** `null` finche' non si e' chiesto al server: non e' «no», e' «non lo so». */
    consenso = $state(null);
    /** Cosa il backend dichiara di salvare. L'elenco lo compone lui. */
    cosaSiSalva = $state(null);
    /** C'e' un utente configurato sul server? Se no, nessuno puo' entrare. */
    configurato = $state(true);
    pronta = $state(false);
    errore = $state(null);

    /** Chiede al server come stanno le cose. Si invoca una volta, all'avvio. */
    async carica() {
        try {
            const dati = await api.authStato();
            this._applica(dati);
        } catch (problema) {
            this.errore = problema.message;
        } finally {
            this.pronta = true;
        }
    }

    _applica(dati) {
        this.connesso = dati.connesso;
        this.utente = dati.utente;
        this.configurato = dati.configurato;
        this.cosaSiSalva = dati.cosa_si_salva ?? this.cosaSiSalva;
        this.consenso = dati.consenso;
        // Il modulo delle preferenze deve sapere cosa gli e' permesso PRIMA che
        // qualcuno provi a scrivere: e' il server a tenere la decisione, e
        // questo e' il momento in cui arriva.
        impostaConsenso(dati.consenso ? dati.consenso.preferenze : null);
    }

    async entra(nome, password) {
        const dati = await api.login(nome, password);
        this.connesso = true;
        this.utente = dati.utente;
        this.consenso = dati.consenso;
        impostaConsenso(dati.consenso ? dati.consenso.preferenze : null);
    }

    async esci() {
        await api.logout();
        this.connesso = false;
        this.utente = null;
    }

    /** Registra la scelta del banner. Il server e' la memoria, non il browser. */
    async decidi(preferenze) {
        this.consenso = await api.consenso(preferenze);
        impostaConsenso(preferenze);
    }
}

export const sessione = new Sessione();
