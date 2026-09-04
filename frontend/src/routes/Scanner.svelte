<!--
    Scanner.svelte — cercare titoli nell'universo, anche a una data passata.
    feat (Blocco 9): ogni titolo trovato porta la ragione per cui e' stato trovato.

    Il vecchio tradash aveva scanner che rispondevano con un elenco di simboli e
    basta: "sette titoli" costringe a fidarsi, e "basato su cosa?" non aveva
    risposta. Qui ogni riga dice quale criterio ha soddisfatto e con che numero.

    La scansione e' un lavoro del registro: parte, si vede, si ferma.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "../components/Assente.svelte";
    import Errore from "../components/Errore.svelte";
    import Spinoff from "../components/Spinoff.svelte";
    import Testo from "../components/Testo.svelte";
    import Valore from "../components/Valore.svelte";
    import { api } from "../lib/api.js";

    // Ogni quanto si chiede se la scansione e' finita, mentre gira.
    const RITMO_MS = 1000;

    const CRITERI = [
        { chiave: "drawdown_minimo", etichetta: "Sceso almeno del", suffisso: "%", scala: 100 },
        { chiave: "drawdown_massimo", etichetta: "Sceso non piu' del", suffisso: "%", scala: 100 },
        { chiave: "recupero_minimo", etichetta: "Recuperato almeno il", suffisso: "%", scala: 100 },
        { chiave: "variazione_1a_minima", etichetta: "Cresciuto in un anno almeno del",
          suffisso: "%", scala: 100 },
        { chiave: "sopra_media_200", etichetta: "Sopra la media a 200 sedute del",
          suffisso: "%", scala: 100 },
        { chiave: "volume_medio_minimo", etichetta: "Volume medio almeno", suffisso: "", scala: 1 }
    ];

    let valori = $state({});
    let settore = $state("");
    let capMinima = $state("");
    let finoA = $state("");
    let runId = $state(null);
    let inCorso = $state(false);
    let risultato = $state(null);
    let errore = $state(null);

    let battito = null;

    onMount(() => () => clearInterval(battito));

    /** I criteri valorizzati, riportati alla scala del backend (le % in frazioni). */
    function criteriScelti() {
        const scelti = {};
        for (const criterio of CRITERI) {
            const grezzo = valori[criterio.chiave];
            if (grezzo !== undefined && grezzo !== "" && grezzo !== null) {
                scelti[criterio.chiave] = Number(grezzo) / criterio.scala;
            }
        }
        return scelti;
    }

    async function avvia() {
        errore = null;
        risultato = null;
        try {
            const avvio = await api.scannerAvvia({
                criteri: criteriScelti(),
                filtri: { sector: settore || null,
                          min_market_cap: capMinima ? Number(capMinima) : null },
                fino_a: finoA || null
            });
            runId = avvio.run_id;
            inCorso = true;
            battito = setInterval(guarda, RITMO_MS);
        } catch (problema) {
            errore = problema;
        }
    }

    async function guarda() {
        try {
            risultato = await api.scannerEsito(runId);
            inCorso = false;
            clearInterval(battito);
        } catch {
            // Ancora in corso: il backend risponde 404 finche' non ha finito.
        }
    }

    async function ferma() {
        await api.fermaLavoro(runId);
    }
</script>

<h1 class="h4 mb-3">Scanner</h1>

<!-- Sta qui e non in una pagina sua: e' un elenco da cui si parte per cercare,
     ed e' questa la pagina in cui si cerca. -->
<Spinoff />

<div class="card mb-3">
    <div class="card-body">
        <h2 class="h6">Criteri</h2>
        <div class="row g-2">
            {#each CRITERI as criterio (criterio.chiave)}
                <div class="col-12 col-md-6 col-lg-4">
                    <label class="form-label small mb-0" for={criterio.chiave}>
                        <Testo testo={criterio.etichetta} />
                    </label>
                    <div class="input-group input-group-sm">
                        <input id={criterio.chiave} class="form-control" inputmode="numeric"
                               bind:value={valori[criterio.chiave]} placeholder="—" />
                        {#if criterio.suffisso}
                            <span class="input-group-text">{criterio.suffisso}</span>
                        {/if}
                    </div>
                </div>
            {/each}
        </div>

        <h2 class="h6 mt-3">Dove cercare</h2>
        <div class="row g-2 align-items-end">
            <div class="col-12 col-md-4">
                <label class="form-label small mb-0" for="scanner-settore">Settore</label>
                <input id="scanner-settore" class="form-control form-control-sm"
                       bind:value={settore} placeholder="Technology" />
            </div>
            <div class="col-12 col-md-4">
                <label class="form-label small mb-0" for="scanner-cap">
                    Capitalizzazione minima
                </label>
                <input id="scanner-cap" class="form-control form-control-sm"
                       bind:value={capMinima} placeholder="10000000000" inputmode="numeric" />
            </div>
            <div class="col-12 col-md-4">
                <label class="form-label small mb-0" for="scanner-data">
                    Come se fosse il giorno
                </label>
                <input id="scanner-data" type="date" class="form-control form-control-sm"
                       bind:value={finoA} />
            </div>
        </div>

        <div class="d-flex gap-2 mt-3">
            <button class="btn btn-sm btn-primary" onclick={avvia}
                    disabled={inCorso || Object.keys(criteriScelti()).length === 0}>
                {inCorso ? "sto cercando…" : "Cerca"}
            </button>
            {#if inCorso}
                <button class="btn btn-sm btn-outline-danger" onclick={ferma}>Ferma</button>
                <a class="btn btn-sm btn-outline-secondary" href="/operazioni">
                    guarda in Operazioni
                </a>
            {/if}
        </div>
    </div>
</div>

{#if errore}
    <Errore {errore} />
{/if}

{#if risultato}
    <p class="small text-secondary">
        {risultato.esaminati} titoli esaminati su {risultato.totale}
        {#if risultato.fino_a}, come se fosse il {risultato.fino_a}{/if}
        {#if !risultato.completata}· <strong>scansione fermata</strong>{/if}
        {#if risultato.senza_dati.length}
            · {risultato.senza_dati.length} senza prezzi
        {/if}
    </p>

    {#if risultato.trovati.length === 0}
        <Assente titolo="Nessun titolo soddisfa questi criteri"
                 motivo={`esaminati ${risultato.esaminati} titoli`}
                 azione="allarga le soglie, o cerca in un settore diverso" />
    {:else}
        {#each risultato.trovati as trovato (trovato.symbol)}
            <div class="card mb-2">
                <div class="card-body py-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <a class="simbolo text-decoration-none"
                           href="/titolo/{trovato.symbol}">{trovato.symbol}</a>
                        <span class="small text-secondary numerico">
                            <Valore valore={trovato.misure.ultimo_prezzo} />
                            {#if trovato.misure.drawdown}
                                · {(trovato.misure.drawdown.profondita_attuale * 100).toFixed(1)}%
                                dal massimo
                            {/if}
                        </span>
                    </div>
                    <ul class="small text-secondary mb-0 mt-1">
                        {#each trovato.perche as ragione (ragione)}
                            <li><Testo testo={ragione} /></li>
                        {/each}
                    </ul>
                </div>
            </div>
        {/each}
    {/if}
{/if}
