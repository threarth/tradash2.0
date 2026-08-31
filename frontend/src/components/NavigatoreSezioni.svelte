<!--
    NavigatoreSezioni.svelte — l'indice della pagina, che segue dove sei.
    feat: la scheda titolo e' lunga, e senza indice si scorre a memoria.

    Non ha un elenco suo: legge quello che le sezioni hanno registrato. Un
    secondo elenco scritto a mano sarebbe una cosa da tenere allineata, e prima
    o poi si aggiunge una sezione senza aggiungerla qui.

    Sta appiccicato in alto mentre la pagina scorre, e su schermi stretti sparisce:
    li' l'indice ruberebbe piu' spazio di quanto ne faccia risparmiare.
-->
<script>
    import Testo from "./Testo.svelte";
    import { sezioni } from "../lib/sezioni.svelte.js";
</script>

{#if sezioni.elenco.length > 1}
    <nav class="navigatore d-none d-xl-block" aria-label="sezioni della pagina">
        <div class="small text-secondary mb-1">In questa pagina</div>
        <ul class="list-unstyled mb-0 small">
            {#each sezioni.elenco as sezione (sezione.id)}
                <li>
                    <button class="btn btn-link btn-sm p-0 text-start text-decoration-none w-100"
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
</style>
