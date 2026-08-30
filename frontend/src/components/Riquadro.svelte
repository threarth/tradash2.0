<!--
    Riquadro.svelte — caricamento, errore, dato: sempre nello stesso ordine.
    feat (Blocco 4): l'unico posto in cui si decide cosa mostrare quando.

    Regola 19: se tre pagine ripetono la stessa struttura, la struttura si
    estrae. E cosi' nessuna delle tre puo' dimenticarsi di gestire l'errore.
-->
<script>
    import Caricamento from "./Caricamento.svelte";
    import Errore from "./Errore.svelte";

    let { richiesta, testoCaricamento = "caricamento…", children } = $props();
</script>

{#if richiesta.primoCaricamento}
    <Caricamento testo={testoCaricamento} />
{:else if richiesta.errore}
    <Errore errore={richiesta.errore} riprova={richiesta.ricarica} />
{:else if richiesta.dato !== null}
    {@render children(richiesta.dato)}
{/if}
