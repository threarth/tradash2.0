/**
 * glossario.svelte.js — lo stato del glossario, condiviso da tutta l'applicazione.
 * feat (Blocco 5): i termini, l'indice, l'interruttore e il pannello aperto.
 *
 * Il riconoscimento vero e proprio sta in `rilevatore.js`, che non ha stato e
 * si testa da solo. Qui c'e' cio' che deve essere uno per tutta l'applicazione:
 * l'indice si costruisce una volta, non a ogni frase.
 */
import { api } from "./api.js";
import { costruisciIndice, costruisciSchema, segmenta } from "./rilevatore.js";

// Dove si ricorda se la sottolineatura e' accesa.
const CHIAVE_ATTIVO = "tradash-glossario";

function leggiPreferenza() {
    try {
        return localStorage.getItem(CHIAVE_ATTIVO) !== "0";
    } catch {
        return true;
    }
}

/** Lo stato del glossario, condiviso da tutta l'applicazione. */
class Glossario {
    termini = $state([]);
    caricato = $state(false);
    errore = $state(null);
    attivo = $state(leggiPreferenza());
    apertoSu = $state(null);

    #indice = new Map();
    #schema = null;
    #inCorso = null;

    /** Carica i termini una volta sola, anche se lo chiedono dieci componenti. */
    async carica() {
        if (this.caricato || this.#inCorso) return this.#inCorso;
        this.#inCorso = (async () => {
            try {
                this.termini = await api.glossario();
                this.#indice = costruisciIndice(this.termini);
                this.#schema = costruisciSchema([...this.#indice.keys()]);
                this.caricato = true;
            } catch (problema) {
                // Un glossario che non arriva non deve impedire di leggere la
                // pagina: il testo resta, senza sottolineature.
                this.errore = problema;
            } finally {
                this.#inCorso = null;
            }
        })();
        return this.#inCorso;
    }

    termine(id) {
        return this.termini.find((t) => t.id === id) ?? null;
    }

    /**
     * Spezza un testo in pezzi: quelli riconosciuti portano l'id del termine.
     * Torna `null` quando non c'e' niente da riconoscere, cosi' chi chiama puo'
     * stampare il testo cosi' com'e' senza montare un componente per pezzo.
     */
    segmenta(testo) {
        if (!this.attivo || !this.caricato) return null;
        return segmenta(testo, this.#indice, this.#schema);
    }

    apri(id) {
        this.apertoSu = id;
    }

    chiudi() {
        this.apertoSu = null;
    }

    alterna() {
        this.attivo = !this.attivo;
        try {
            localStorage.setItem(CHIAVE_ATTIVO, this.attivo ? "1" : "0");
        } catch {
            // Preferenza non ricordata: la sottolineatura funziona comunque.
        }
    }
}

export const glossario = new Glossario();
