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
 *
 * ## Perche' `untrack` sta qui e non e' un dettaglio
 *
 * Registrarsi vuol dire **leggere l'elenco e riscriverlo**. La registrazione
 * avviene dentro un effetto del componente, quindi senza precauzioni quella
 * lettura diventa una dipendenza: si scrive, l'effetto riparte, si riscrive.
 * Con dieci sezioni il risultato e' stato `effect_update_depth_exceeded`, cioe'
 * Svelte che si arrende dopo aver bruciato CPU a vuoto — e la pagina lentissima
 * mentre ci prova.
 *
 * L'elenco si legge senza tracciarlo. Chi lo mostra — il navigatore — lo legge
 * normalmente e si aggiorna come deve.
 */
import { untrack } from "svelte";

/** Le sezioni presenti nella pagina, e quale si sta guardando. */
class Sezioni {
    elenco = $state([]);
    attiva = $state(null);

    // Le richieste di apertura e chiusura che arrivano da FUORI la sezione — dal
    // menu laterale, o dai due comandi complessivi. Ogni sezione la legge e si
    // regola; il numero cambia a ogni comando cosi' anche «chiudi tutto» due
    // volte di fila arriva due volte.
    comando = $state(null);

    /** Una sezione entra nella pagina. Ritorna la funzione che la toglie. */
    registra(id, titolo, apri) {
        const senzaDiMe = () => untrack(() => this.elenco.filter((s) => s.id !== id));

        this.elenco = [...senzaDiMe(), { id, titolo, apri, aperta: false }];
        return () => {
            this.elenco = senzaDiMe();
            if (untrack(() => this.attiva) === id) this.attiva = null;
        };
    }

    /** Una sezione dice se in questo momento e' aperta o chiusa. */
    segnalaStato(id, aperta) {
        this.elenco = untrack(() => this.elenco.map(
            (s) => (s.id === id && s.aperta !== aperta ? { ...s, aperta } : s)
        ));
    }

    /** Apre o chiude una sezione da fuori: dal menu laterale. */
    cambia(id) {
        const sezione = untrack(() => this.elenco.find((s) => s.id === id));
        sezione?.apri?.(!sezione.aperta);
    }

    /** Apre o chiude tutte quante. */
    tutte(aperte) {
        for (const sezione of untrack(() => this.elenco)) sezione.apri?.(aperte);
    }

    /** Quante sono aperte adesso: serve ai due comandi per sapere cosa offrire. */
    get aperte() {
        return this.elenco.filter((s) => s.aperta).length;
    }

    /** Quale sezione e' sotto gli occhi adesso. */
    guarda(id) {
        if (untrack(() => this.attiva) !== id) this.attiva = id;
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
