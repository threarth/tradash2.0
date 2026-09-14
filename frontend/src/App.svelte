<!--
    App.svelte — quale pagina, in base al percorso.
    feat (Blocco 4): tre pagine e un fuori-strada che lo dice.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "./components/Assente.svelte";
    import Caricamento from "./components/Caricamento.svelte";
    import Cookie from "./components/Cookie.svelte";
    import Layout from "./components/Layout.svelte";
    import { allaSessioneScaduta } from "./lib/api.js";
    import { percorso } from "./lib/router.js";
    import { sessione } from "./lib/sessione.svelte.js";
    import Accesso from "./routes/Accesso.svelte";
    import Glossario from "./routes/Glossario.svelte";
    import Operazioni from "./routes/Operazioni.svelte";
    import Privacy from "./routes/Privacy.svelte";
    import Scanner from "./routes/Scanner.svelte";
    import Titolo from "./routes/Titolo.svelte";
    import Universo from "./routes/Universo.svelte";
    import Watchlist from "./routes/Watchlist.svelte";

    const PAGINE = {
        "/": Universo,
        "/watchlist": Watchlist,
        "/operazioni": Operazioni,
        "/scanner": Scanner,
        "/glossario": Glossario,
        "/privacy": Privacy
    };

    onMount(() => {
        // Una lettura sola, e non e' lavoro pesante: sapere se sei dentro o
        // fuori e' la domanda che decide cosa disegnare, e senza risposta non
        // si puo' disegnare niente (regola 2 resta salva).
        sessione.carica();

        // Il cookie muore chiudendo il browser e scade se cambi la password
        // altrove: qualunque chiamata puo' incontrare un 401. Quando succede si
        // torna all'accesso, invece di riempire la pagina di riquadri rossi che
        // dicono tutti la stessa cosa.
        allaSessioneScaduta(() => {
            sessione.connesso = false;
            sessione.utente = null;
        });
    });

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

{#if !sessione.pronta}
    <!-- Un istante solo, ma senza questo si vedrebbe lampeggiare la schermata
         di accesso anche a chi e' gia' dentro. -->
    <div class="d-flex align-items-center justify-content-center min-vh-100">
        <Caricamento testo="controllo l'accesso…" />
    </div>
{:else if !sessione.connesso}
    <Accesso />
{:else}
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

    <!-- Il banner compare finche' non hai deciso, e poi mai piu': la decisione
         la ricorda il server, quindi non torna a ogni visita. -->
    {#if sessione.consenso === null}
        <Cookie />
    {/if}
{/if}
