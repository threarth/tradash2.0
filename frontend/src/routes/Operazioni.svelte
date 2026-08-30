<!--
    Operazioni.svelte — cosa sta girando, e come fermarlo.
    feat (Blocco 4): la regola 1 resa visibile.

    E' la pagina che nel vecchio sistema non esisteva: il 28/08 girava un
    download di ~500 ticker che nessun endpoint vedeva, e l'unico modo di
    fermarlo era uccidere il processo.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "../components/Assente.svelte";
    import Errore from "../components/Errore.svelte";
    import { api } from "../lib/api.js";

    // Il battito con cui si aggiorna la pagina mentre un lavoro gira.
    const INTERVALLO_MS = 1500;

    // Quante righe di log si mostrano.
    const CHIAMATE_MOSTRATE = 40;

    let attivi = $state([]);
    let storici = $state([]);
    let chiamate = $state([]);
    let riepilogo = $state(null);
    let errore = $state(null);
    let caricato = $state(false);

    async function aggiorna() {
        try {
            [attivi, storici, chiamate, riepilogo] = await Promise.all([
                api.lavoriAttivi(),
                api.lavoriStorici(),
                api.chiamate({ limit: CHIAMATE_MOSTRATE }),
                api.chiamateRiepilogo()
            ]);
            errore = null;
        } catch (problema) {
            errore = problema;
        } finally {
            caricato = true;
        }
    }

    onMount(() => {
        aggiorna();
        const battito = setInterval(aggiorna, INTERVALLO_MS);
        return () => clearInterval(battito);
    });

    async function ferma(runId) {
        try {
            await api.fermaLavoro(runId);
            await aggiorna();
        } catch (problema) {
            errore = problema;
        }
    }

    const CLASSE_ESITO = {
        done: "text-bg-success", stopped: "text-bg-warning",
        failed: "text-bg-danger", running: "text-bg-primary"
    };
    const CLASSE_PROVENIENZA = {
        network: "text-bg-primary", cache: "text-bg-success",
        local: "text-bg-secondary", undeclared: "text-bg-danger"
    };
</script>

<h1 class="h4 mb-3">Operazioni</h1>

{#if errore}
    <Errore {errore} riprova={aggiorna} />
{/if}

<h2 class="h6 text-secondary">In corso</h2>
{#if attivi.length === 0}
    {#if caricato}
        <Assente titolo="Non sta girando niente"
                 motivo="nessun lavoro attivo in questo momento"
                 azione="i lavori partono solo quando li chiedi" />
    {/if}
{:else}
    <div class="list-group mb-4">
        {#each attivi as lavoro (lavoro.run_id)}
            <div class="list-group-item">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="fw-semibold">{lavoro.label}</span>
                        <span class="text-secondary small ms-2">{lavoro.kind}</span>
                        {#if lavoro.detail}
                            <div class="small text-secondary">{lavoro.detail}</div>
                        {/if}
                    </div>
                    <button class="btn btn-sm btn-outline-danger"
                            disabled={lavoro.stop_requested}
                            onclick={() => ferma(lavoro.run_id)}>
                        {lavoro.stop_requested ? "si sta fermando…" : "Ferma"}
                    </button>
                </div>
                {#if lavoro.total}
                    <div class="progress mt-2" style="height:4px">
                        <div class="progress-bar" role="progressbar"
                             style="width:{(100 * lavoro.done) / lavoro.total}%"></div>
                    </div>
                {/if}
            </div>
        {/each}
    </div>
{/if}

<h2 class="h6 text-secondary mt-4">Cronologia dei lavori</h2>
{#if storici.length === 0}
    <p class="text-secondary small">Nessun lavoro ancora eseguito.</p>
{:else}
    <div class="table-responsive mb-4">
        <table class="table table-sm align-middle">
            <thead><tr>
                <th>Esito</th><th>Lavoro</th><th class="text-end">Passi</th>
                <th>Dettaglio</th><th>Avviato</th>
            </tr></thead>
            <tbody>
                {#each storici as lavoro (lavoro.run_id)}
                    <tr>
                        <td><span class="badge {CLASSE_ESITO[lavoro.status] ?? 'text-bg-secondary'}"
                              >{lavoro.status}</span></td>
                        <td>{lavoro.label}</td>
                        <td class="numerico">{lavoro.done}{lavoro.total
                            ? ` / ${lavoro.total}` : ""}</td>
                        <td class="small text-secondary">{lavoro.detail ?? ""}</td>
                        <td class="small">{lavoro.started_at}</td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
{/if}

<h2 class="h6 text-secondary mt-4">Chiamate</h2>
{#if riepilogo}
    <p class="small">
        {#each Object.entries(riepilogo.per_provenienza) as [provenienza, quante] (provenienza)}
            <span class="badge {CLASSE_PROVENIENZA[provenienza] ?? 'text-bg-secondary'} me-1">
                {provenienza}: {quante}
            </span>
        {/each}
        {#if riepilogo.non_dichiarate > 0}
            <span class="badge text-bg-danger">
                senza provenienza dichiarata: {riepilogo.non_dichiarate}
            </span>
        {/if}
    </p>
{/if}
{#if chiamate.length === 0}
    <p class="text-secondary small">Nessuna chiamata registrata.</p>
{:else}
    <div class="table-responsive">
        <table class="table table-sm align-middle">
            <thead><tr>
                <th>Provenienza</th><th>Fornitore</th><th>Endpoint</th><th>Ambito</th>
                <th class="text-end">Durata</th><th>Quando</th>
            </tr></thead>
            <tbody>
                {#each chiamate as chiamata (chiamata.id)}
                    <tr class:table-danger={chiamata.status === "error"}>
                        <td><span class="badge {CLASSE_PROVENIENZA[chiamata.source]
                              ?? 'text-bg-secondary'}">{chiamata.source}</span></td>
                        <td>{chiamata.provider}</td>
                        <td class="small">{chiamata.endpoint}</td>
                        <td class="small">{chiamata.scope ?? ""}</td>
                        <td class="numerico">{chiamata.duration_ms} ms</td>
                        <td class="small">{chiamata.called_at}</td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
{/if}
