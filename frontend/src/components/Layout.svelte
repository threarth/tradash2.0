<!--
    Layout.svelte — la barra in alto e il posto dove va il contenuto.
    feat (Blocco 4): navigazione, tema, e il conteggio dei lavori in corso.

    Il conteggio non e' un ornamento: la regola 1 dice che ogni lavoro dev'essere
    visibile, e un lavoro visibile solo su una pagina che non stai guardando e'
    visibile a meta'.
-->
<script>
    import { onMount } from "svelte";

    import { api } from "../lib/api.js";
    import { intercettaClick, percorso } from "../lib/router.js";
    import { alternaTema, SCURO, temaAttuale } from "../lib/tema.js";

    let { children } = $props();

    // Ogni quanto si chiede se c'e' qualcosa in corso. Non e' lavoro pesante:
    // e' una lettura in memoria del registro, e senza non ci si accorgerebbe di
    // un lavoro partito da un'altra pagina.
    const INTERVALLO_LAVORI_MS = 3000;

    const PAGINE = [
        { percorso: "/", etichetta: "Universo", icona: "bi-globe2" },
        { percorso: "/watchlist", etichetta: "Watchlist", icona: "bi-bookmark-star" },
        { percorso: "/operazioni", etichetta: "Operazioni", icona: "bi-activity" }
    ];

    let tema = $state(SCURO);
    let lavoriAttivi = $state(0);

    onMount(() => {
        tema = temaAttuale();
        let vivo = true;

        async function guarda() {
            try {
                const lavori = await api.lavoriAttivi();
                if (vivo) lavoriAttivi = lavori.length;
            } catch {
                // Il backend spento non deve far lampeggiare un errore nella barra:
                // se ne accorge la pagina che sta chiedendo davvero qualcosa.
                if (vivo) lavoriAttivi = 0;
            }
        }

        guarda();
        const battito = setInterval(guarda, INTERVALLO_LAVORI_MS);
        return () => {
            vivo = false;
            clearInterval(battito);
        };
    });

    const attiva = (destinazione) =>
        destinazione === "/" ? $percorso === "/" : $percorso.startsWith(destinazione);
</script>

<svelte:body onclick={intercettaClick} />

<nav class="navbar navbar-expand bg-body-tertiary navbar-tradash sticky-top">
    <div class="container-fluid contenuto">
        <a class="navbar-brand fw-semibold" href="/">tradash</a>

        <ul class="navbar-nav me-auto">
            {#each PAGINE as pagina (pagina.percorso)}
                <li class="nav-item">
                    <a class="nav-link" class:active={attiva(pagina.percorso)}
                       href={pagina.percorso}>
                        <i class="bi {pagina.icona}" aria-hidden="true"></i>
                        {pagina.etichetta}
                        {#if pagina.percorso === "/operazioni" && lavoriAttivi > 0}
                            <span class="badge text-bg-warning ms-1">{lavoriAttivi}</span>
                        {/if}
                    </a>
                </li>
            {/each}
        </ul>

        <button class="btn btn-sm btn-outline-secondary"
                onclick={() => (tema = alternaTema())}
                title="Cambia tema" aria-label="Cambia tema">
            <i class="bi {tema === SCURO ? 'bi-sun' : 'bi-moon-stars'}" aria-hidden="true"></i>
        </button>
    </div>
</nav>

<main class="container-fluid contenuto py-4">
    {@render children()}
</main>
