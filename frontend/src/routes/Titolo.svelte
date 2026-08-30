<!--
    Titolo.svelte — la scheda di un titolo: il guscio, e le sezioni che verranno.
    feat (Blocco 6): intestazione, grafico, e le sezioni che dichiarano di mancare.

    Il precedente da non ripetere sono le 1.342 righe della pagina omonima nel
    vecchio tradash, che montava una ventina di componenti sapendo tutto. Qui
    e' un guscio: i blocchi 7 e 8 aggiungono le loro sezioni senza toccare le
    altre, e finche' non ci sono la pagina lo DICE — con dentro quale blocco le
    portera' — invece di far finta che quel dato non esista.
-->
<script>
    import Assente from "../components/Assente.svelte";
    import Caricamento from "../components/Caricamento.svelte";
    import Errore from "../components/Errore.svelte";
    import Analisi from "../components/Analisi.svelte";
    import Documenti from "../components/Documenti.svelte";
    import Fondamentali from "../components/Fondamentali.svelte";
    import Grafico from "../components/Grafico.svelte";
    import Segnali from "../components/Segnali.svelte";
    import Testo from "../components/Testo.svelte";
    import Valore from "../components/Valore.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    let intervallo = $state("1A");

    const scheda = richiedi(() => api.titolo(simbolo));
    const grafico = richiedi(() => api.titoloPrezzi(simbolo, intervallo));

    // La scheda si ricarica quando cambia il simbolo, il grafico anche quando
    // cambia l'intervallo. Leggerli qui li rende dipendenze dell'effetto.
    $effect(() => {
        simbolo;
        scheda.ricarica();
    });

    $effect(() => {
        simbolo;
        intervallo;
        grafico.ricarica();
    });
</script>

{#if scheda.primoCaricamento}
    <Caricamento testo={`carico ${simbolo}…`} />
{:else if scheda.errore}
    <Errore errore={scheda.errore} riprova={scheda.ricarica} />
{:else if scheda.dato}
    {@const profilo = scheda.dato.profilo}

    <div class="d-flex justify-content-between align-items-start gap-3 mb-3">
        <div>
            <h1 class="h3 mb-1">{scheda.dato.symbol}</h1>
            {#if profilo.available}
                <div class="text-secondary">
                    <Valore valore={profilo.sector} mancante="settore non classificato" />
                    ·
                    <Valore valore={profilo.industry} mancante="industria non classificata" />
                    {#if profilo.country}· {profilo.country}{/if}
                </div>
            {/if}
        </div>
        <a class="btn btn-sm btn-outline-secondary" href="/watchlist">← Watchlist</a>
    </div>

    {#if !profilo.available}
        <Assente titolo="Questo titolo non ha un profilo"
                 motivo={profilo.reason} azione={profilo.action} />
    {:else}
        {#if profilo.long_business_summary}
            <details class="mb-3">
                <summary class="text-secondary small">Cosa fa questa societa'</summary>
                <p class="small mt-2 mb-0"><Testo testo={profilo.long_business_summary} /></p>
            </details>
        {/if}

        <div class="d-flex justify-content-between align-items-center mb-2">
            <h2 class="h6 mb-0">Prezzo</h2>
            <div class="btn-group btn-group-sm">
                {#each (grafico.dato?.intervalli ?? []) as nome (nome)}
                    <button class="btn {intervallo === nome
                                ? 'btn-primary' : 'btn-outline-secondary'}"
                            onclick={() => (intervallo = nome)}>{nome}</button>
                {/each}
            </div>
        </div>

        {#if grafico.primoCaricamento}
            <Caricamento testo="carico i prezzi…" />
        {:else if grafico.errore}
            <Errore errore={grafico.errore} riprova={grafico.ricarica} />
        {:else if grafico.dato}
            <Grafico barre={grafico.dato.barre} serie={grafico.dato.serie}
                     configurazione={grafico.dato.configurazione} />
            <p class="small text-secondary mt-2">
                {grafico.dato.barre.length} sedute · dati arrivati da {grafico.dato.source}
            </p>
        {/if}

        <hr class="my-4" />
        <h2 class="h6">Segnali di rischio fondamentale</h2>
        <p class="small text-secondary">
            Deterministici: calcolati dai bilanci, senza modelli linguistici.
        </p>
        <Segnali {simbolo} />

        <hr class="my-4" />
        <h2 class="h6">Fondamentali</h2>
        <Fondamentali {simbolo} />

        <hr class="my-4" />
        <Documenti {simbolo} />

        <hr class="my-4" />
        <h2 class="h6">Analisi</h2>
        <Analisi {simbolo} />

        <hr class="my-4" />
        <div class="row g-3">
            {#each Object.entries(scheda.dato.sezioni_future) as [nome, sezione] (nome)}
                <div class="col-12 col-lg-6">
                    <h2 class="h6 text-capitalize">{nome}</h2>
                    <Assente titolo="Non ancora costruita"
                             motivo={sezione.reason} azione={sezione.action} />
                </div>
            {/each}
        </div>
    {/if}
{/if}
