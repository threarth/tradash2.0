<!--
    NavigatoreSezioni.svelte — l'indice della pagina, che segue dove sei e apre.
    feat: la scheda titolo e' lunga, e senza indice si scorre a memoria.

    Non ha un elenco suo: legge quello che le sezioni hanno registrato. Un
    secondo elenco scritto a mano sarebbe una cosa da tenere allineata, e prima
    o poi si aggiunge una sezione senza aggiungerla qui.

    Ogni voce fa due cose diverse con due bersagli diversi: **il nome porta
    li'**, **la freccia apre o chiude**. Tenerle separate serve perche' sono
    domande diverse — «fammi vedere dov'e'» e «aprimela» — e un solo bersaglio
    che fa entrambe ne sbaglia sempre una.

    Sta appiccicato in alto mentre la pagina scorre, e su schermi stretti sparisce:
    li' l'indice ruberebbe piu' spazio di quanto ne faccia risparmiare.
-->
<script>
    import Testo from "./Testo.svelte";
    import { sezioni } from "../lib/sezioni.svelte.js";

    let { chiudi = null } = $props();
</script>

{#if sezioni.elenco.length > 1}
    <nav class="navigatore d-none d-xl-block" aria-label="sezioni della pagina">
        <div class="d-flex justify-content-between align-items-center mb-1">
            <span class="small text-secondary">In questa pagina</span>
            {#if chiudi}
                <button class="btn btn-sm btn-link p-0 text-secondary"
                        onclick={chiudi} aria-label="nascondi l'indice">×</button>
            {/if}
        </div>

        <!-- I due comandi complessivi. Quello che serve di piu' e' il primo:
             una pagina tutta aperta si richiude in un colpo, e da li' si apre
             solo quello che serve. -->
        <div class="btn-group btn-group-sm w-100 mb-2" role="group">
            <button class="btn btn-outline-secondary" onclick={() => sezioni.tutte(false)}
                    disabled={sezioni.aperte === 0}>Chiudi tutto</button>
            <button class="btn btn-outline-secondary" onclick={() => sezioni.tutte(true)}
                    disabled={sezioni.aperte === sezioni.elenco.length}>Apri tutto</button>
        </div>

        <ul class="list-unstyled mb-0 small">
            {#each sezioni.elenco as sezione (sezione.id)}
                <li class="d-flex align-items-start gap-1">
                    <button class="btn btn-link btn-sm p-0 text-secondary text-decoration-none freccia"
                            onclick={() => sezioni.cambia(sezione.id)}
                            aria-expanded={sezione.aperta}
                            aria-label={`${sezione.aperta ? "chiudi" : "apri"} ${sezione.titolo}`}>
                        {sezione.aperta ? "▾" : "▸"}
                    </button>
                    <button class="btn btn-link btn-sm p-0 text-start text-decoration-none flex-grow-1"
                            class:fw-semibold={sezioni.attiva === sezione.id}
                            class:text-body={sezioni.attiva === sezione.id}
                            class:text-secondary={sezioni.attiva !== sezione.id}
                            onclick={() => sezioni.vaiA(sezione.id)}>
                        <Testo testo={sezione.titolo} />
                    </button>
                </li>
            {/each}
        </ul>
    </nav>
{/if}

<style>
    .navigatore {
        position: sticky;
        top: 1rem;
        border-left: 2px solid var(--bs-border-color);
        padding-left: 0.75rem;
    }

    /* La freccia e' un bersaglio piccolo: gli si da' un'area cliccabile vera. */
    .freccia {
        min-width: 1.25rem;
        line-height: 1.4;
    }
</style>
