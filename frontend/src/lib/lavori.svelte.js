/**
 * lavori.svelte.js — cosa sta girando adesso, chiesto UNA volta per tutti.
 * feat: un battito solo, tre consumatori.
 *
 * La barra in alto mostra quanti lavori ci sono, il pannello mostra a che punto
 * sono, la scheda di un titolo mostra il proprio. Sono tre domande allo stesso
 * endpoint: se ognuno se la facesse per conto suo, un'analisi in corso
 * significherebbe tre richieste ogni due secondi per lo stesso elenco.
 *
 * **Due ritmi, non uno.** Svelto mentre qualcosa gira, lento quando non gira
 * niente: con un ritmo solo una scheda dimenticata continuerebbe a chiedere per
 * giorni, e «il costo di una pagina non dipende da quanto resta aperta» e' la
 * regola 2 alla lettera. Il vecchio sistema e' morto proprio cosi'.
 *
 * **Un lavoro finito non sparisce subito.** Resta qualche secondo col suo
 * esito: un pannello che si svuota nell'istante in cui finisce non lascia il
 * tempo di leggere com'e' andata, ed e' la fine il momento in cui si guarda.
 */
import { api } from "./api.js";

const RITMO_ATTIVO_MS = 2000;
const RITMO_FERMO_MS = 30000;

// Quanto resta a video un lavoro dopo che e' sparito dai vivi.
const CODA_MS = 8000;

/** I lavori in corso, condivisi da tutta l'applicazione. */
class Lavori {
    attivi = $state([]);
    conclusi = $state([]);

    #vivo = false;
    #prossimo = null;
    #lettori = 0;

    /** Quanti lavori stanno girando davvero adesso. */
    get quanti() {
        return this.attivi.length;
    }

    /** Tutto quello che vale la pena mostrare: i vivi, e i finiti da poco. */
    get visibili() {
        return [...this.attivi, ...this.conclusi];
    }

    /** Il lavoro che riguarda un titolo, se ce n'e' uno. */
    per(ambito) {
        return this.visibili.find((l) => l.ambito === ambito) ?? null;
    }

    /**
     * Comincia a guardare. Ritorna la funzione per smettere.
     *
     * Si contano i lettori: il battito parte col primo e si ferma con l'ultimo,
     * cosi' montare due componenti non raddoppia le richieste e smontarne uno
     * non lascia l'altro senza aggiornamenti.
     */
    guarda() {
        this.#lettori += 1;
        if (this.#lettori === 1) this.#avvia();

        return () => {
            this.#lettori -= 1;
            if (this.#lettori === 0) this.#ferma();
        };
    }

    #avvia() {
        this.#vivo = true;
        this.#giro();
    }

    #ferma() {
        this.#vivo = false;
        clearTimeout(this.#prossimo);
        this.#prossimo = null;
    }

    async #giro() {
        try {
            const arrivati = await api.lavoriAttivi();
            if (this.#vivo) this.#aggiorna(arrivati);
        } catch {
            // Il backend spento non deve far lampeggiare un errore nella barra:
            // se ne accorge la pagina che sta chiedendo davvero qualcosa.
            if (this.#vivo) this.attivi = [];
        }

        if (this.#vivo) {
            this.#prossimo = setTimeout(() => this.#giro(),
                                        this.quanti > 0 ? RITMO_ATTIVO_MS : RITMO_FERMO_MS);
        }
    }

    /** Chi non c'e' piu' fra i vivi passa fra i conclusi, e li' sfuma. */
    #aggiorna(arrivati) {
        const vivi = new Set(arrivati.map((l) => l.run_id));
        for (const prima of this.attivi) {
            if (!vivi.has(prima.run_id)) this.#trattieni(prima);
        }
        this.attivi = arrivati;
    }

    #trattieni(lavoro) {
        // L'ultimo stato che abbiamo visto era «running»: quello vero — done,
        // stopped, failed — sta nella cronologia, e qui non lo sappiamo. Si
        // dice cio' che si sa: che e' finito.
        this.conclusi = [...this.conclusi, { ...lavoro, status: "concluso" }];
        setTimeout(() => {
            this.conclusi = this.conclusi.filter((l) => l.run_id !== lavoro.run_id);
        }, CODA_MS);
    }
}

export const lavori = new Lavori();
