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
    import { glossario } from "../lib/glossario.svelte.js";
    import { intercettaClick, percorso } from "../lib/router.js";
    import { alternaTema, SCURO, temaAttuale } from "../lib/tema.js";
    import PannelloGlossario from "./PannelloGlossario.svelte";

    let { children } = $props();

    // Ogni quanto si chiede se c'e' qualcosa in corso. Due ritmi, non uno:
    // svelto mentre qualcosa gira, lento quando non gira niente.
    //
    // Con un ritmo solo, una scheda dimenticata continuerebbe a chiedere per
    // giorni — e "il costo di una pagina non dipende da quanto resta aperta" e'
    // la regola 2 alla lettera. Il vecchio sistema e' morto proprio cosi', con
    // una scheda aperta che al riavvio del backend ha rilanciato 500 download.
    const RITMO_ATTIVO_MS = 2000;
    const RITMO_FERMO_MS = 30000;

    const PAGINE = [
        { percorso: "/", etichetta: "Universo", icona: "bi-globe2" },
        { percorso: "/watchlist", etichetta: "Watchlist", icona: "bi-bookmark-star" },
        { percorso: "/scanner", etichetta: "Scanner", icona: "bi-search" },
        { percorso: "/operazioni", etichetta: "Operazioni", icona: "bi-activity" },
        { percorso: "/glossario", etichetta: "Glossario", icona: "bi-book" }
    ];

    let tema = $state(SCURO);
    let lavoriAttivi = $state(0);

    onMount(() => {
        tema = temaAttuale();
        // Una lettura sola per tutta la sessione, da un file locale: e' cio' che
        // serve perche' la sottolineatura funzioni ovunque senza che ogni
        // pagina se la vada a prendere per conto suo.
        glossario.carica();

        let vivo = true;
        let prossimo = null;

        async function guarda() {
            try {
                const lavori = await api.lavoriAttivi();
                if (vivo) lavoriAttivi = lavori.length;
            } catch {
                // Il backend spento non deve far lampeggiare un errore nella barra:
                // se ne accorge la pagina che sta chiedendo davvero qualcosa.
                if (vivo) lavoriAttivi = 0;
            }
            if (vivo) {
                prossimo = setTimeout(
                    guarda, lavoriAttivi > 0 ? RITMO_ATTIVO_MS : RITMO_FERMO_MS
                );
            }
        }

        guarda();
        return () => {
            vivo = false;
            clearTimeout(prossimo);
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

        <div class="d-flex gap-2">
            <button class="btn btn-sm {glossario.attivo
                        ? 'btn-outline-primary' : 'btn-outline-secondary'}"
                    onclick={() => glossario.alterna()}
                    title={glossario.attivo
                        ? "Spegni la sottolineatura dei termini"
                        : "Accendi la sottolineatura dei termini"}
                    aria-label="Sottolineatura dei termini">
                <i class="bi bi-journal-text" aria-hidden="true"></i>
            </button>
            <button class="btn btn-sm btn-outline-secondary"
                    onclick={() => (tema = alternaTema())}
                    title="Cambia tema" aria-label="Cambia tema">
                <i class="bi {tema === SCURO ? 'bi-sun' : 'bi-moon-stars'}" aria-hidden="true"></i>
            </button>
        </div>
    </div>
</nav>

<main class="container-fluid contenuto py-4">
    {@render children()}
</main>

<PannelloGlossario />
