<!--
    PannelloGlossario.svelte — la definizione completa, di lato.
    feat (Blocco 5): pannello scritto a mano, senza il JavaScript di Bootstrap.

    Il modale di Bootstrap muta il DOM che Svelte considera suo e va distrutto a
    mano allo smontaggio: qui sono trenta righe, e lo smontaggio lo fa Svelte.
-->
<script>
    import { glossario } from "../lib/glossario.svelte.js";

    const termine = $derived(glossario.apertoSu ? glossario.termine(glossario.apertoSu) : null);

    /** I termini collegati che esistono davvero: un rimando rotto e' peggio di nessuno. */
    const collegati = $derived(
        (termine?.related ?? [])
            .map((id) => glossario.termine(id))
            .filter((t) => t !== null)
    );

    function chiudiConEsc(evento) {
        if (evento.key === "Escape") glossario.chiudi();
    }
</script>

<svelte:window onkeydown={chiudiConEsc} />

{#if termine}
    <!-- Il velo: cliccarlo chiude, come ci si aspetta da un pannello. -->
    <div class="velo-glossario" onclick={() => glossario.chiudi()}
         onkeydown={chiudiConEsc} role="presentation"></div>

    <aside class="pannello-glossario" aria-label="Glossario: {termine.label}">
        <header class="d-flex justify-content-between align-items-start gap-2 mb-3">
            <h2 class="h5 mb-0">{termine.label}</h2>
            <button class="btn btn-sm btn-outline-secondary" onclick={() => glossario.chiudi()}
                    aria-label="Chiudi">
                <i class="bi bi-x-lg"></i>
            </button>
        </header>

        <p>{termine.short}</p>
        <p class="text-secondary">{termine.full}</p>

        {#if termine.formula}
            <h3 class="h6 mt-3">Formula</h3>
            <p class="font-monospace small">{termine.formula}</p>
        {/if}

        {#if termine.example}
            <h3 class="h6 mt-3">Esempio</h3>
            <p class="small">{termine.example}</p>
        {/if}

        {#if termine.context}
            <h3 class="h6 mt-3">Dove si usa</h3>
            <p class="small text-secondary">{termine.context}</p>
        {/if}

        {#if collegati.length}
            <h3 class="h6 mt-3">Termini collegati</h3>
            <div class="d-flex flex-wrap gap-2">
                {#each collegati as collegato (collegato.id)}
                    <button class="btn btn-sm btn-outline-secondary"
                            onclick={() => glossario.apri(collegato.id)}>
                        {collegato.label}
                    </button>
                {/each}
            </div>
        {/if}

        {#if termine.source_url}
            <p class="small mt-3 mb-0">
                <a href={termine.source_url} target="_blank" rel="noopener noreferrer">
                    {termine.source_label ?? "fonte"} ↗
                </a>
            </p>
        {/if}
    </aside>
{/if}
