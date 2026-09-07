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
    import Ticker from "../components/Ticker.svelte";
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
        { chiave: "volume_medio_minimo", etichetta: "Volume medio almeno", suffisso: "", scala: 1 },
        // I tre di bilancio. Prima lo scanner sapeva solo com'e' andato il
        // prezzo: questi chiedono a undicimila titoli la stessa cosa che il
        // rilevatore spin-off chiede ai suoi ventisette.
        { chiave: "ricavi_qoq_minimo", etichetta: "Ricavi in crescita sul trimestre almeno del",
          suffisso: "%", scala: 100 },
        { chiave: "margine_crescita_minima", etichetta: "Margine lordo in crescita almeno di",
          suffisso: " punti", scala: 100 },
        { chiave: "eps_minimo", etichetta: "EPS dell'ultimo trimestre almeno",
          suffisso: "", scala: 1 }
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
            <!-- Gli STESSI criteri, ma all'indietro. Sta accanto a «Cerca» e non
                 in una pagina a parte, perche' la domanda «ha mai funzionato?»
                 va fatta prima di accenderli — e in una pagina a parte non la
                 farebbe nessuno. -->
            <button class="btn btn-sm btn-outline-primary" onclick={rigioca}
                    disabled={rigiocoInCorso || inCorso
                              || Object.keys(criteriScelti()).length === 0}>
                {rigiocoInCorso ? "rigioco…" : "Ha mai funzionato?"}
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

{#if rigiocoInCorso}
    <p class="small text-secondary">
        <Testo testo="Sto rigiocando questi criteri su tutti i mesi che i dati coprono. Il pannello in alto a destra dice a che punto e'." />
    </p>
{/if}

{#if rigioco}
    {@const r = rigioco.riepilogo}
    <div class="card mb-3">
        <div class="card-body">
            <h2 class="h6">Questo criterio, all'indietro</h2>
            <p class="small text-secondary mb-2">
                <Testo testo="Per ogni mese: come sono andati nei {rigioco.orizzonte_mesi} mesi dopo i titoli che il criterio avrebbe trovato, contro come e' andato TUTTO il resto. La seconda colonna e' il paragone che conta: un criterio che trova titoli col +12% non vale niente se in quei mesi il mercato ha fatto +15%." />
            </p>

            {#if r.reason}
                <p class="small text-warning mb-0"><Testo testo={r.reason} /></p>
            {:else}
                <p class="mb-2">
                    <strong class="numerico">{r.vinti} mesi su {r.mesi_utili}</strong>
                    ({(r.quota_vinti * 100).toFixed(0)}%) battono il non-filtrare ·
                    vantaggio mediano
                    <strong class="numerico"
                            class:text-success={r.vantaggio_mediano > 0}
                            class:text-danger={r.vantaggio_mediano < 0}>
                        {r.vantaggio_mediano > 0 ? "+" : ""}{(r.vantaggio_mediano * 100).toFixed(1)}%
                    </strong>
                    · {r.trovati_per_mese} titoli trovati al mese
                </p>

                <div class="table-responsive" style="max-height: 22rem">
                    <table class="table table-sm small mb-0">
                        <thead class="sticky-top">
                            <tr>
                                <th>mese</th>
                                <th class="text-end">trovati</th>
                                <th class="text-end">loro</th>
                                <th class="text-end">tutti</th>
                                <th class="text-end">differenza</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each rigioco.mesi as m (m.mese)}
                                {#if m.mediana_trovati !== null && m.mediana_universo !== null}
                                    {@const differenza = m.mediana_trovati - m.mediana_universo}
                                    <tr>
                                        <td class="numerico">{m.mese}</td>
                                        <td class="text-end numerico">{m.trovati}</td>
                                        <td class="text-end numerico">
                                            {(m.mediana_trovati * 100).toFixed(1)}%
                                        </td>
                                        <td class="text-end numerico text-secondary">
                                            {(m.mediana_universo * 100).toFixed(1)}%
                                        </td>
                                        <td class="text-end numerico"
                                            class:text-success={differenza > 0}
                                            class:text-danger={differenza < 0}>
                                            {differenza > 0 ? "+" : ""}{(differenza * 100).toFixed(1)}%
                                        </td>
                                    </tr>
                                {/if}
                            {/each}
                        </tbody>
                    </table>
                </div>

                <p class="small text-warning mt-2 mb-0">
                    <Testo testo="Il paragone e' con la mediana di TUTTO l'universo, comprese migliaia di societa' minuscole e poco scambiate: un criterio che le evita risulta perdente anche quando sta solo evitando il fondo del barile. Va letto sapendolo." />
                </p>
            {/if}
        </div>
    </div>
{/if}

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
                        <!-- Il risultato dice il simbolo e i numeri che l'hanno
                             fatto trovare, non chi e': l'anteprima al passaggio
                             del mouse risponde a «ma questo chi e'?» senza
                             aprire e richiudere una pagina. -->
                        <Ticker simbolo={trovato.symbol} classe="simbolo text-decoration-none" />
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
