<!--
    PannelloLavori.svelte — cosa sta girando, mentre sei dove l'hai lanciato.
    feat: il job manager del vecchio tradash, in alto a destra.

    La pagina Operazioni c'e' da sempre e mostra tutto — ma e' la pagina che NON
    stai guardando mentre lanci un'analisi. La regola 1 dice che ogni lavoro
    dev'essere visibile, e un lavoro visibile solo altrove e' visibile a meta':
    finora, sulla scheda di un titolo, di tre minuti di analisi si vedeva un
    numero in un pallino giallo.

    Compare quando qualcosa parte e se ne va qualche secondo dopo la fine. Non
    c'e' un interruttore per aprirlo o chiuderlo perche' non serve: quando non
    gira niente non c'e' niente da mostrare, ed e' il 95% del tempo.

    Le righe le disegna `Scia.svelte`, che le disegna anche nella scheda del
    titolo: sono lo stesso dato guardato da due posti.
-->
<script>
    import Scia from "./Scia.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { lavori } from "../lib/lavori.svelte.js";

    // Un lavoro che ha finito ma di cui non conosciamo ancora l'esito.
    const CONCLUSO = "concluso";

    let errore = $state(null);

    $effect(() => lavori.guarda());

    /** Quanto e' avanzato, in percentuale. `null` quando i passi non si sanno. */
    function avanzamento(lavoro) {
        if (!lavoro.total) return null;
        return Math.min(100, Math.round((lavoro.done / lavoro.total) * 100));
    }

    async function ferma(runId) {
        errore = null;
        try {
            await api.fermaLavoro(runId);
        } catch (problema) {
            errore = problema.message;
        }
    }
</script>

{#if lavori.visibili.length > 0}
    <aside class="pannello-lavori" aria-label="Lavori in corso">
        {#each lavori.visibili as lavoro (lavoro.run_id)}
            {@const percentuale = avanzamento(lavoro)}
            <div class="lavoro">
                <div class="d-flex justify-content-between align-items-start gap-2">
                    <div class="min-w-0">
                        <div class="small fw-semibold text-truncate">
                            <Testo testo={lavoro.label} />
                        </div>
                        <div class="small text-secondary numerico">
                            {#if lavoro.status === CONCLUSO}
                                finito
                            {:else}
                                {lavoro.done}{#if lavoro.total} di {lavoro.total}{/if} ·
                                {lavoro.kind}
                            {/if}
                        </div>
                    </div>
                    {#if lavoro.status !== CONCLUSO}
                        <button class="btn btn-sm btn-outline-danger py-0"
                                disabled={lavoro.stop_requested}
                                onclick={() => ferma(lavoro.run_id)}>
                            {lavoro.stop_requested ? "mi fermo…" : "Stop"}
                        </button>
                    {/if}
                </div>

                <!-- Senza il numero dei passi la barra non puo' dire a che punto
                     e': si muove e basta, che e' cio' che sappiamo davvero. -->
                <div class="progress mt-2" style="height: 4px">
                    {#if percentuale === null}
                        <div class="progress-bar progress-bar-striped progress-bar-animated
                                    w-100"></div>
                    {:else}
                        <div class="progress-bar" style="width: {percentuale}%"></div>
                    {/if}
                </div>

                <Scia {lavoro} />
            </div>
        {/each}

        {#if errore}
            <p class="small text-danger mb-0">{errore}</p>
        {/if}
    </aside>
{/if}

<style>
    /* Sotto alla barra di navigazione, che e' appiccicata in alto: il pannello
       le si mette sotto invece di coprirla. */
    .pannello-lavori {
        position: fixed;
        top: 4rem;
        right: 1rem;
        z-index: 1030;
        width: min(24rem, calc(100vw - 2rem));
        max-height: 70vh;
        overflow-y: auto;
        padding: 0.75rem;
        border: 1px solid var(--bs-border-color);
        border-radius: 0.5rem;
        background: var(--bs-body-bg);
        box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 25%);
    }

    .lavoro + .lavoro {
        margin-top: 0.75rem;
        padding-top: 0.75rem;
        border-top: 1px solid var(--bs-border-color);
    }

</style>
