/**
 * sezioni.svelte.js — l'elenco delle sezioni di una pagina, tenuto in un posto solo.
 * feat: il navigatore laterale e le sezioni richiudibili leggono da qui.
 *
 * Il difetto che questo modulo esiste per impedire: un elenco di voci nel
 * navigatore e un elenco di sezioni nella pagina sono **due elenchi che devono
 * combaciare**, e prima o poi non combaciano piu' — si aggiunge una sezione e il
 * navigatore non la nomina, oppure la nomina e il collegamento non porta da
 * nessuna parte.
 *
 * Qui l'elenco e' uno: ogni sezione si registra quando compare e si toglie
 * quando sparisce, e il navigatore mostra quello che c'e' davvero.
 *
 * L'ordine e' quello di registrazione, cioe' l'ordine in cui le sezioni stanno
 * nel documento: e' l'ordine in cui si scorre la pagina, ed e' l'unico che ha
 * senso in un indice.
 */

/** Le sezioni presenti nella pagina, e quale si sta guardando. */
class Sezioni {
    elenco = $state([]);
    attiva = $state(null);

    /** Una sezione entra nella pagina. Ritorna la funzione che la toglie. */
    registra(id, titolo) {
        this.elenco = [...this.elenco.filter((s) => s.id !== id), { id, titolo }];
        return () => {
            this.elenco = this.elenco.filter((s) => s.id !== id);
            if (this.attiva === id) this.attiva = null;
        };
    }

    /** Quale sezione e' sotto gli occhi adesso. */
    guarda(id) {
        this.attiva = id;
    }

    /** Porta la pagina su una sezione, senza saltarci di colpo. */
    vaiA(id) {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    /** Svuota l'elenco: si chiama cambiando pagina. */
    azzera() {
        this.elenco = [];
        this.attiva = null;
    }
}

export const sezioni = new Sezioni();
