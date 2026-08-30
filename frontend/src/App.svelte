<!--
    App.svelte — quale pagina, in base al percorso.
    feat (Blocco 4): tre pagine e un fuori-strada che lo dice.
-->
<script>
    import Assente from "./components/Assente.svelte";
    import Layout from "./components/Layout.svelte";
    import { percorso } from "./lib/router.js";
    import Glossario from "./routes/Glossario.svelte";
    import Operazioni from "./routes/Operazioni.svelte";
    import Universo from "./routes/Universo.svelte";
    import Watchlist from "./routes/Watchlist.svelte";

    const PAGINE = {
        "/": Universo,
        "/watchlist": Watchlist,
        "/operazioni": Operazioni,
        "/glossario": Glossario
    };

    const Pagina = $derived(PAGINE[$percorso]);
</script>

<Layout>
    {#if Pagina}
        <Pagina />
    {:else}
        <Assente titolo="Pagina non trovata"
                 motivo={`il percorso ${$percorso} non corrisponde a nessuna pagina`}
                 azione="torna all'universo dalla barra in alto" />
    {/if}
</Layout>
