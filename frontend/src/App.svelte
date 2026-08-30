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
    import Titolo from "./routes/Titolo.svelte";
    import Universo from "./routes/Universo.svelte";
    import Watchlist from "./routes/Watchlist.svelte";

    const PAGINE = {
        "/": Universo,
        "/watchlist": Watchlist,
        "/operazioni": Operazioni,
        "/glossario": Glossario
    };

    const Pagina = $derived(PAGINE[$percorso]);

    // La scheda di un titolo e' l'unica rotta con un pezzo variabile: il
    // simbolo. Un router generico per un caso solo sarebbe piu' codice di
    // questo, e con piu' modi di sbagliare.
    const PREFISSO_TITOLO = "/titolo/";
    const simbolo = $derived(
        $percorso.startsWith(PREFISSO_TITOLO)
            ? decodeURIComponent($percorso.slice(PREFISSO_TITOLO.length))
            : null
    );
</script>

<Layout>
    {#if simbolo}
        <Titolo {simbolo} />
    {:else if Pagina}
        <Pagina />
    {:else}
        <Assente titolo="Pagina non trovata"
                 motivo={`il percorso ${$percorso} non corrisponde a nessuna pagina`}
                 azione="torna all'universo dalla barra in alto" />
    {/if}
</Layout>
