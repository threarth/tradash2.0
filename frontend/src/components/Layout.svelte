<!--
    Layout.svelte — la barra in alto e il posto dove va il contenuto.
    feat (Blocco 4): navigazione, tema, e il conteggio dei lavori in corso.

    Il conteggio non e' un ornamento: la regola 1 dice che ogni lavoro dev'essere
    visibile, e un lavoro visibile solo su una pagina che non stai guardando e'
    visibile a meta'. Il numero pero' dice solo QUANTI: a che punto sono lo dice
    il pannello, che sta qui accanto e compare da solo quando serve.

    Il battito non e' piu' qui dentro: sta in `lavori.svelte.js`, uno per tutti.
    Tre componenti che chiedono lo stesso elenco ogni due secondi sarebbero tre
    richieste per la stessa risposta.
-->
<script>
    import { onMount } from "svelte";

    import { freschezza } from "../lib/freschezza.svelte.js";
    import { glossario } from "../lib/glossario.svelte.js";
    import { lavori } from "../lib/lavori.svelte.js";
    import { intercettaClick, percorso } from "../lib/router.js";
    import { sessione } from "../lib/sessione.svelte.js";
    import { alternaTema, SCURO, temaAttuale } from "../lib/tema.js";
    import PannelloGlossario from "./PannelloGlossario.svelte";
    import PannelloLavori from "./PannelloLavori.svelte";
    import SelettoreModello from "./SelettoreModello.svelte";

    let { children } = $props();

    const PAGINE = [
        { percorso: "/", etichetta: "Universo", icona: "bi-globe2" },
        { percorso: "/watchlist", etichetta: "Watchlist", icona: "bi-bookmark-star" },
        { percorso: "/scanner", etichetta: "Scanner", icona: "bi-search" },
        { percorso: "/operazioni", etichetta: "Operazioni", icona: "bi-activity" },
        { percorso: "/glossario", etichetta: "Glossario", icona: "bi-book" }
    ];

    let tema = $state(SCURO);

    onMount(() => {
        tema = temaAttuale();
        // Una lettura sola per tutta la sessione, da un file locale: e' cio' che
        // serve perche' la sottolineatura funzioni ovunque senza che ogni
        // pagina se la vada a prendere per conto suo.
        glossario.carica();
        // Cosa e' invecchiato: una lettura di SQLite e di un file, all'apertura.
        // Non e' un battito e non ricostruisce niente — il sistema DICE, tu
        // decidi. E' la scelta dichiarata: nessuno scheduler.
        freschezza.carica();
    });

    // Quando un lavoro finisce, qualcosa puo' essere tornato fresco: si
    // richiede allora, non a intervalli.
    let lavoriPrima = 0;
    $effect(() => {
        if (lavoriPrima > 0 && lavori.quanti === 0) freschezza.carica();
        lavoriPrima = lavori.quanti;
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
                        {#if pagina.percorso === "/operazioni" && lavori.quanti > 0}
                            <span class="badge text-bg-warning ms-1">{lavori.quanti}</span>
                        {/if}
                    </a>
                </li>
            {/each}
        </ul>

        <div class="d-flex gap-2 align-items-start">
            <SelettoreModello />
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

            <!-- Chi sei, e i due modi di smettere di esserlo. Il nome non e'
                 decorativo: su una macchina raggiungibile da internet, sapere
                 con quale accesso stai guardando e' parte di cosa stai
                 guardando. -->
            <!-- L'allarme. Sta nella barra e non nella pagina Universo perche'
                 un avviso che si vede solo se vai a cercarlo non e' un avviso:
                 e' una nota a pie' di pagina. -->
            <button class="btn btn-sm {freschezza.quanti
                        ? 'btn-outline-warning' : 'btn-outline-secondary'}"
                    onclick={() => freschezza.alterna()}
                    title={freschezza.quanti
                        ? `${freschezza.quanti} cose da aggiornare`
                        : "dati aggiornati"}
                    aria-label="Freschezza dei dati">
                <i class="bi {freschezza.quanti ? 'bi-exclamation-triangle' : 'bi-check2-circle'}"
                   aria-hidden="true"></i>
                {#if freschezza.quanti}
                    <span class="badge text-bg-warning ms-1">{freschezza.quanti}</span>
                {/if}
            </button>

            <a class="btn btn-sm btn-outline-secondary" href="/privacy"
               title="Privacy, cosa viene salvato, e la tua password">
                <i class="bi bi-person-circle" aria-hidden="true"></i>
                {sessione.utente ?? ""}
            </a>
            <button class="btn btn-sm btn-outline-secondary" onclick={() => sessione.esci()}
                    title="Esci" aria-label="Esci">
                <i class="bi bi-box-arrow-right" aria-hidden="true"></i>
            </button>
        </div>
    </div>
</nav>

<!-- Il pannello dell'allarme: cosa e' vecchio, da quanto, e CHE COSA FARE.
     L'azione e' il nome del pulsante, non quello dell'endpoint: chi legge un
     avviso vuole sapere dove cliccare, non quale rotta chiamare. -->
{#if freschezza.aperto}
    <div class="container-fluid contenuto pt-3">
        <div class="card">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <h2 class="h6 mb-2">Freschezza dei dati</h2>
                    <button class="btn-close" aria-label="Chiudi"
                            onclick={() => freschezza.alterna()}></button>
                </div>

                <table class="table table-sm small mb-2">
                    <tbody>
                        {#each freschezza.tutti as riga (riga.categoria)}
                            <tr class:text-secondary={!riga.vecchio}>
                                <td style="width: 1.5rem">
                                    <i class="bi {riga.vecchio
                                        ? 'bi-exclamation-triangle text-warning'
                                        : 'bi-check2'}" aria-hidden="true"></i>
                                </td>
                                <td>{riga.etichetta}</td>
                                <td class="numerico text-end" style="width: 7rem">
                                    {riga.eta_giorni === null ? "—"
                                        : riga.eta_giorni + " giorni"}
                                </td>
                                <td class="numerico text-end" style="width: 7rem">
                                    {riga.limite_giorni === null ? ""
                                        : "su " + riga.limite_giorni}
                                </td>
                                <td class="text-end">
                                    {#if !riga.vecchio}
                                        <span class="text-secondary">aggiornato</span>
                                    {:else if riga.endpoint}
                                        <!-- Il pulsante non aggiorna da solo: lo
                                             premi tu. E' la scelta dichiarata —
                                             il sistema dice cosa e' vecchio, la
                                             decisione resta tua. -->
                                        <button class="btn btn-sm btn-warning"
                                                disabled={freschezza.inCorso.has(riga.categoria)}
                                                onclick={() => freschezza.avvia(riga)}>
                                            {freschezza.inCorso.has(riga.categoria)
                                                ? "avvio…" : riga.azione}
                                        </button>
                                    {:else}
                                        <!-- Niente rotta: si rifa' da terminale, e
                                             si mostra il comando invece di un
                                             pulsante che non potrebbe esistere. -->
                                        <code class="small">{riga.azione}</code>
                                    {/if}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>

                {#if freschezza.errore}
                    <div class="alert alert-danger small py-2">{freschezza.errore}</div>
                {/if}

                <p class="small text-secondary mb-0">
                    <i class="bi bi-hand-index" aria-hidden="true"></i>
                    {freschezza.nota}
                </p>
            </div>
        </div>
    </div>
{/if}

<main class="container-fluid contenuto py-4">
    {@render children()}
</main>

<PannelloGlossario />
<PannelloLavori />
