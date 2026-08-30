<!--
    Glossario.svelte — i 171 termini, cercabili.
    feat (Blocco 5): l'elenco completo, per chi vuole guardare invece di inciampare.

    La sottolineatura serve quando stai leggendo altro; questa pagina serve
    quando la domanda e' "cosa vuol dire", e non hai un testo sotto mano.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "../components/Assente.svelte";
    import Caricamento from "../components/Caricamento.svelte";
    import Errore from "../components/Errore.svelte";
    import Testo from "../components/Testo.svelte";
    import { glossario } from "../lib/glossario.svelte.js";

    let cerca = $state("");

    onMount(glossario.carica.bind(glossario));

    /** Cerca nell'etichetta e nella definizione breve: chi cerca "utile" non
        sta cercando un id, sta cercando un concetto. */
    const trovati = $derived.by(() => {
        const cercato = cerca.trim().toLowerCase();
        if (!cercato) return glossario.termini;
        return glossario.termini.filter(
            (t) => t.label.toLowerCase().includes(cercato) ||
                   t.short.toLowerCase().includes(cercato)
        );
    });
</script>

<div class="d-flex justify-content-between align-items-center mb-3">
    <h1 class="h4 mb-0">Glossario</h1>
    <span class="small text-secondary">{glossario.termini.length} termini</span>
</div>

{#if glossario.errore}
    <Errore errore={glossario.errore} riprova={() => glossario.carica()} />
{:else if !glossario.caricato}
    <Caricamento testo="carico i termini…" />
{:else}
    <input class="form-control form-control-sm mb-3" bind:value={cerca}
           placeholder="Cerca un termine o un concetto" />

    {#if trovati.length === 0}
        <Assente titolo="Nessun termine trovato"
                 motivo={`nessuno dei ${glossario.termini.length} termini contiene "${cerca}"`}
                 azione="prova con una parola piu' corta" />
    {:else}
        <div class="row g-3">
            {#each trovati as termine (termine.id)}
                <div class="col-12 col-lg-6">
                    <button class="card w-100 h-100 text-start border-0"
                            onclick={() => glossario.apri(termine.id)}>
                        <div class="card-body">
                            <div class="fw-semibold">{termine.label}</div>
                            <div class="small text-secondary mt-1">
                                <Testo testo={termine.short} />
                            </div>
                        </div>
                    </button>
                </div>
            {/each}
        </div>
    {/if}
{/if}
