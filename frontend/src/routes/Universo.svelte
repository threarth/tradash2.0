<!--
    Universo.svelte — i titoli disponibili, e i buchi che hanno.
    feat (Blocco 4): la pagina NON costruisce l'universo aprendosi.

    Regola 2: aprire questa pagina legge lo stato e basta. La costruzione costa
    minuti la prima volta, e parte solo se la chiedi — con un pulsante che
    consegna il lavoro al registro, dove si puo' fermare.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "../components/Assente.svelte";
    import Riquadro from "../components/Riquadro.svelte";
    import Valore from "../components/Valore.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";
    import { naviga } from "../lib/router.js";

    const TITOLI_PER_PAGINA = 50;

    let settore = $state("");
    let capMinima = $state("");
    let cerca = $state("");
    let avvio = $state(null);

    const elenco = richiedi(() =>
        api.universo({ sector: settore, min_market_cap: capMinima, search: cerca,
            limit: TITOLI_PER_PAGINA })
    );
    const stato = richiedi(() => api.universoStato());

    onMount(() => {
        elenco.ricarica();
        stato.ricarica();
    });

    async function costruisci() {
        avvio = null;
        try {
            avvio = await api.universoCostruisci(true);
            naviga("/operazioni");
        } catch (problema) {
            avvio = { errore: problema.message };
        }
    }

    function applicaFiltri(evento) {
        evento.preventDefault();
        elenco.ricarica();
    }
</script>

<div class="d-flex justify-content-between align-items-center mb-3">
    <h1 class="h4 mb-0">Universo</h1>
    <button class="btn btn-sm btn-primary" onclick={costruisci}>
        <i class="bi bi-arrow-repeat" aria-hidden="true"></i> Ricostruisci
    </button>
</div>

{#if avvio?.errore}
    <div class="alert alert-danger">{avvio.errore}</div>
{/if}

<Riquadro richiesta={stato} testoCaricamento="leggo lo stato dell'universo…">
    {#snippet children(dati)}
        {#if !dati.available}
            <Assente titolo="L'universo non e' ancora stato costruito"
                     motivo={dati.reason} azione={dati.action} />
        {:else}
            <div class="row g-3 mb-4">
                <div class="col-6 col-lg-3">
                    <div class="card h-100"><div class="card-body">
                        <div class="text-secondary small">Titoli</div>
                        <div class="fs-4 numerico">{dati.titoli.toLocaleString("it")}</div>
                    </div></div>
                </div>
                <div class="col-6 col-lg-3">
                    <div class="card h-100"><div class="card-body">
                        <div class="text-secondary small">Costruito il</div>
                        <div class="small mt-1">{dati.costruito_il}</div>
                    </div></div>
                </div>
                <div class="col-6 col-lg-3">
                    <div class="card h-100"><div class="card-body">
                        <div class="text-secondary small">Prezzo piu' vecchio di
                            {dati.prezzo_vecchio.oltre_giorni} giorni</div>
                        <div class="fs-4 numerico">{dati.prezzo_vecchio.titoli}</div>
                    </div></div>
                </div>
                <div class="col-6 col-lg-3">
                    <div class="card h-100"><div class="card-body">
                        <div class="text-secondary small">Capitalizzazione non derivabile</div>
                        <div class="fs-4 numerico">{dati.capitalizzazione.non_derivabile}</div>
                        <div class="small text-secondary">
                            {dati.capitalizzazione.perche_mancano_le_azioni} senza azioni in
                            circolazione
                        </div>
                    </div></div>
                </div>
            </div>

            <details class="mb-4">
                <summary class="text-secondary small">Cosa manca, colonna per colonna</summary>
                <div class="row g-2 mt-1">
                    {#each Object.entries(dati.copertura) as [colonna, buco] (colonna)}
                        <div class="col-6 col-lg-3 small">
                            <span class="text-secondary">{colonna}</span>
                            <span class="float-end numerico">
                                {buco.mancanti} ({buco.percentuale}%)
                            </span>
                        </div>
                    {/each}
                </div>
            </details>
        {/if}
    {/snippet}
</Riquadro>

<form class="row g-2 align-items-end mb-3" onsubmit={applicaFiltri}>
    <div class="col-12 col-md-3">
        <label class="form-label small" for="filtro-settore">Settore</label>
        <input id="filtro-settore" class="form-control form-control-sm" bind:value={settore}
               placeholder="Technology" />
    </div>
    <div class="col-12 col-md-3">
        <label class="form-label small" for="filtro-cap">Capitalizzazione minima</label>
        <input id="filtro-cap" class="form-control form-control-sm" bind:value={capMinima}
               placeholder="500000000000" inputmode="numeric" />
    </div>
    <div class="col-12 col-md-3">
        <label class="form-label small" for="filtro-cerca">Simbolo</label>
        <input id="filtro-cerca" class="form-control form-control-sm" bind:value={cerca}
               placeholder="NVD" />
    </div>
    <div class="col-12 col-md-3">
        <button class="btn btn-sm btn-outline-primary w-100" type="submit">Filtra</button>
    </div>
</form>

<Riquadro richiesta={elenco} testoCaricamento="cerco nei titoli…">
    {#snippet children(dati)}
        {#if !dati.available}
            <Assente motivo={dati.reason} azione={dati.action} />
        {:else if dati.titoli.length === 0}
            <Assente titolo="Nessun titolo con questi filtri"
                     motivo={`l'universo ne contiene ${dati.totale}, ma nessuno corrisponde`}
                     azione="allarga i filtri" />
        {:else}
            <div class="table-responsive">
                <table class="table table-sm table-hover align-middle">
                    <thead>
                        <tr>
                            <th>Simbolo</th><th>Settore</th><th>Industria</th>
                            <th class="text-end">Capitalizzazione</th>
                            <th class="text-end">Ultima chiusura</th>
                            <th>Del</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each dati.titoli as titolo (titolo.symbol)}
                            <tr>
                                <td class="fw-semibold">
                                    <a href="/titolo/{titolo.symbol}"
                                       class="text-decoration-none">{titolo.symbol}</a>
                                </td>
                                <td><Valore valore={titolo.sector} mancante="non classificato" /></td>
                                <td><Valore valore={titolo.industry} mancante="non classificata" /></td>
                                <td class="numerico"><Valore valore={titolo.market_cap} /></td>
                                <td class="numerico"><Valore valore={titolo.last_close} /></td>
                                <td class="small"><Valore valore={titolo.last_close_date} /></td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
            <p class="text-secondary small">
                Mostrati {dati.titoli.length} titoli su {dati.totale.toLocaleString("it")}.
            </p>
        {/if}
    {/snippet}
</Riquadro>
