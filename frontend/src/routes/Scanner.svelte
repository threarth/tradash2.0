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
        // I ricavi anno su anno mancavano in pagina pur esistendo nel backend:
        // si poteva premere solo quello trimestrale, che il rigioco misura
        // perdente a tutti e tre gli orizzonti, e non quello annuale, che vince.
        { chiave: "ricavi_yoy_minimo", etichetta: "Ricavi in crescita sull'anno almeno del",
          suffisso: "%", scala: 100 },
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

    // I preset arrivano dal backend col loro verdetto misurato. Scriverli qui
    // vorrebbe dire un verdetto che invecchia da solo il giorno in cui il
    // rigioco viene rifatto.
    // Chi sta gia' in watchlist, letto una volta quando arrivano i risultati.
    // Senza, aggiungeresti due volte lo stesso titolo e il backend risponderebbe
    // «gia' presente» — corretto, e inutile da leggere venti volte.
    let inWatchlist = $state(new Set());
    let aggiungendo = $state(new Set());
    let esitoAggiunta = $state(null);

    let preset = $state([]);
    let presetScelto = $state(null);
    let presetMisura = $state(null);

    onMount(() => {
        // Una lettura sola, da un elenco che sta in memoria nel backend: non e'
        // lavoro pesante e serve a disegnare il modulo (regola 2 resta salva).
        api.scannerCriteri()
            .then((dati) => {
                preset = dati.preset ?? [];
                presetMisura = {
                    misuratoIl: dati.misurato_il,
                    daRimisurare: dati.da_rimisurare,
                    perche: dati.perche ?? [],
                    azione: dati.azione
                };
            })
            .catch(() => (preset = []));

        return () => {
            clearInterval(battito);
            clearInterval(battitoRigioco);
        };
    });

    /** Riempie il modulo con un preset. Non cerca da solo: la ricerca la premi tu. */
    function applica(scelto) {
        presetScelto = scelto;
        const nuovi = {};
        for (const criterio of CRITERI) {
            const frazione = scelto.criteri[criterio.chiave];
            if (frazione !== undefined) nuovi[criterio.chiave] = frazione * criterio.scala;
        }
        valori = nuovi;
        rigioco = null;
    }

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
            leggiWatchlist();
        } catch {
            // Ancora in corso: il backend risponde 404 finche' non ha finito.
        }
    }

    /** Quali dei titoli trovati sono gia' osservati. Una lettura, non venti. */
    async function leggiWatchlist() {
        try {
            const dati = await api.watchlist({});
            inWatchlist = new Set(dati.titoli.map((t) => t.symbol));
        } catch {
            // Se non si riesce a leggerla, i pulsanti restano tutti «aggiungi»:
            // premerne uno gia' presente non fa danni, il backend lo dice.
            inWatchlist = new Set();
        }
    }

    /** Aggiunge un titolo alla watchlist, senza tema.
     *
     *  Senza tema di proposito: chiedere quale al momento del click bloccherebbe
     *  con una tendina proprio mentre scorri venti risultati. La classificazione
     *  si fa dopo, dalla watchlist, anche col giro esporta -> LLM -> importa.
     */
    async function aggiungi(simbolo) {
        if (inWatchlist.has(simbolo) || aggiungendo.has(simbolo)) return;

        aggiungendo = new Set([...aggiungendo, simbolo]);
        esitoAggiunta = null;
        try {
            const esito = await api.watchlistAggiungi(simbolo, null);
            if (esito.aggiunti?.length) {
                inWatchlist = new Set([...inWatchlist, simbolo]);
            } else if (esito.sconosciuti?.length) {
                esitoAggiunta = `${simbolo} non e' nell'universo: ricostruisci l'anagrafica`;
            } else if (esito.gia_presenti?.length) {
                inWatchlist = new Set([...inWatchlist, simbolo]);
            }
        } catch (problema) {
            esitoAggiunta = problema.message;
        } finally {
            const restanti = new Set(aggiungendo);
            restanti.delete(simbolo);
            aggiungendo = restanti;
        }
    }

    async function ferma() {
        await api.fermaLavoro(runId);
    }

    // --- «Ha mai funzionato?»: gli stessi criteri, ma all'indietro -----------
    //
    // Questo blocco mancava del tutto: il markup piu' in basso usava `rigioco`,
    // `rigiocoInCorso` e `rigioca()` senza che nessuno li dichiarasse, quindi la
    // pagina sollevava un ReferenceError appena si disegnava. Il build non lo
    // dice, e il commit che aveva aggiunto il pulsante era stato verificato
    // attraverso l'API invece che aprendo la pagina.
    let rigioco = $state(null);
    let rigiocoInCorso = $state(false);
    let rigiocoRunId = $state(null);
    let battitoRigioco = null;

    // Quale dei tre orizzonti si sta guardando. Sei mesi e' quello con cui sono
    // state fatte tutte le misure precedenti, quindi e' il punto di partenza.
    const ORIZZONTE_PREDEFINITO = 6;
    let orizzonteMostrato = $state(ORIZZONTE_PREDEFINITO);

    // Derivati invece che `{@const}` nel markup: quello vuole essere figlio
    // diretto di un blocco, e qui starebbe dentro a un <div>.
    const chiaveOrizzonte = $derived(String(orizzonteMostrato));
    const riepilogoMostrato = $derived(rigioco?.riepilogo?.[chiaveOrizzonte] ?? null);

    /** Rigioca i criteri scelti su tutti i mesi che i dati coprono. */
    async function rigioca() {
        errore = null;
        rigioco = null;
        try {
            const avvio = await api.rigiocaCriteri(criteriScelti());
            rigiocoRunId = avvio.run_id;
            rigiocoInCorso = true;
            battitoRigioco = setInterval(guardaRigioco, RITMO_MS);
        } catch (problema) {
            errore = problema;
        }
    }

    async function guardaRigioco() {
        try {
            rigioco = await api.rigiocoEsito(rigiocoRunId);
            rigiocoInCorso = false;
            clearInterval(battitoRigioco);
            orizzonteMostrato = rigioco.orizzonti_mesi.includes(ORIZZONTE_PREDEFINITO)
                ? ORIZZONTE_PREDEFINITO
                : rigioco.orizzonti_mesi[0];
        } catch {
            // Ancora in corso: il backend risponde 404 finche' non ha finito.
        }
    }
</script>

<h1 class="h4 mb-3">Scanner</h1>

<!-- I preset: combinazioni a cui e' GIA' stata fatta la domanda «ha mai
     funzionato?». Ognuno porta il proprio verdetto, compresi i due che
     perdono — che restano in elenco proprio per questo: un'idea scartata che
     non sta scritta da qualche parte torna da sola fra sei mesi. -->
{#if preset.length}
    <div class="card mb-3">
        <div class="card-body">
            <h2 class="h6">Da dove partire</h2>
            <p class="small text-secondary mb-2">
                <Testo testo="Combinazioni gia' rigiocate sul 2019-2026. Il verdetto e' misurato, non consigliato: due di queste perdono, e sono in elenco per non doverle riscoprire." />
            </p>

            <div class="d-flex flex-wrap gap-2 mb-2">
                {#each preset as scelto (scelto.nome)}
                    <button class="btn btn-sm {scelto.verdetto?.vince
                                ? 'btn-outline-success' : 'btn-outline-secondary'}"
                            class:active={presetScelto?.nome === scelto.nome}
                            onclick={() => applica(scelto)}>
                        <i class="bi {scelto.verdetto?.vince ? 'bi-check2'
                                    : scelto.verdetto ? 'bi-x' : 'bi-question'}"
                           aria-hidden="true"></i>
                        {scelto.etichetta}
                    </button>
                {/each}
            </div>

            {#if presetScelto}
                <div class="border rounded p-3 small">
                    <div class="mb-1"><Testo testo={presetScelto.idea} /></div>

                    {#if !presetScelto.verdetto}
                        <!-- Regola 5: un preset senza misura non e' un preset
                             neutro, e' uno a cui la domanda non e' mai stata
                             fatta — e va detto col comando per farla. -->
                        <div class="text-warning">
                            mai rigiocato: non si sa se funziona
                            <span class="numerico">· {presetMisura?.azione}</span>
                        </div>
                    {:else}
                        {@const v = presetScelto.verdetto}
                        <div class:text-success={v.vince} class:text-warning={!v.vince}>
                            <strong>{v.forma}</strong>
                            {#each Object.entries(v.orizzonti) as [mesi, riga] (mesi)}
                                <span class="numerico ms-2">
                                    {mesi}m {riga.vantaggio === null ? "n.g."
                                        : (riga.vantaggio > 0 ? "+" : "")
                                          + (riga.vantaggio * 100).toFixed(1) + "%"}
                                </span>
                            {/each}
                            <span class="text-secondary numerico">
                                · {v.mesi_giudicabili} mesi giudicabili a sei
                            </span>
                        </div>
                    {/if}

                    <div class="text-secondary mt-1">
                        <Testo testo={presetScelto.cautela} />
                    </div>
                </div>
            {/if}

            <!-- Un verdetto vecchio non si aggiorna da solo: il sistema lo DICE
                 e la decisione di rigiocare resta tua. Nessuno scheduler. -->
            {#if presetMisura?.daRimisurare}
                <div class="alert alert-warning small mt-2 mb-0 py-2">
                    <strong>I verdetti sono da rimisurare.</strong>
                    {presetMisura.perche.join("; ")}.
                    Da terminale: <span class="numerico">{presetMisura.azione}</span>
                </div>
            {:else if presetMisura?.misuratoIl}
                <p class="small text-secondary mt-2 mb-0">
                    Verdetti misurati il <span class="numerico">
                        {presetMisura.misuratoIl.slice(0, 10)}</span>.
                </p>
            {/if}
        </div>
    </div>
{/if}

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
    <div class="card mb-3">
        <div class="card-body">
            <h2 class="h6">Questo criterio, all'indietro</h2>
            <p class="small text-secondary mb-2">
                <Testo testo="Per ogni mese: come sono andati nei mesi dopo i titoli che il criterio avrebbe trovato, contro come e' andato IL RESTO degli investibili. La seconda colonna e' il paragone che conta: un criterio che trova titoli col +12% non vale niente se in quei mesi il resto ha fatto +15%." />
            </p>

            <!-- Le soglie si dichiarano PRIMA dei numeri: un filtro che non si
                 dichiara e' un filtro di cui nessuno sa l'effetto. -->
            <p class="small text-secondary mb-3">
                Paragone fra investibili: capitalizzazione <span class="numerico"
                >&ge; ${(rigioco.soglie.capitalizzazione_minima / 1e6).toFixed(0)}M</span>
                e scambiato <span class="numerico"
                >&ge; ${(rigioco.soglie.scambiato_minimo_al_giorno / 1e6).toFixed(1)}M</span>
                al giorno — <Testo testo={rigioco.soglie.nota} />
            </p>

            <!-- Tre orizzonti e non uno: chi perde a tre mesi e vince a dodici
                 e' LENTO, chi perde a tutti e tre e' SBAGLIATO. -->
            <ul class="nav nav-tabs mb-3">
                {#each rigioco.orizzonti_mesi as mesi (mesi)}
                    <li class="nav-item">
                        <button class="nav-link" class:active={orizzonteMostrato === mesi}
                                onclick={() => (orizzonteMostrato = mesi)}>
                            {mesi} mesi
                        </button>
                    </li>
                {/each}
            </ul>

            {#if !riepilogoMostrato}
                <p class="small text-secondary mb-0">
                    <Testo testo="nessun riepilogo per questo orizzonte" />
                </p>
            {:else if riepilogoMostrato.reason}
                <p class="small text-warning mb-0">
                    <Testo testo={riepilogoMostrato.reason} />
                </p>
            {:else}
                <p class="mb-2">
                    <strong class="numerico">{riepilogoMostrato.vinti} mesi su {riepilogoMostrato.mesi_utili}</strong>
                    ({(riepilogoMostrato.quota_vinti * 100).toFixed(0)}%) battono il non-filtrare ·
                    vantaggio mediano
                    <strong class="numerico"
                            class:text-success={riepilogoMostrato.vantaggio_mediano > 0}
                            class:text-danger={riepilogoMostrato.vantaggio_mediano < 0}>
                        {riepilogoMostrato.vantaggio_mediano > 0 ? "+" : ""}{(riepilogoMostrato.vantaggio_mediano * 100).toFixed(1)}%
                    </strong>
                    · {riepilogoMostrato.trovati_per_mese} titoli trovati al mese
                </p>

                <div class="table-responsive" style="max-height: 22rem">
                    <table class="table table-sm small mb-0">
                        <thead class="sticky-top">
                            <tr>
                                <th>mese</th>
                                <th class="text-end">investibili</th>
                                <th class="text-end">trovati</th>
                                <th class="text-end">loro</th>
                                <th class="text-end">il resto</th>
                                <th class="text-end">differenza</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each rigioco.mesi as m (m.mese)}
                                {@const riga = m.orizzonti[chiaveOrizzonte]}
                                {#if riga && riga.mediana_trovati !== null && riga.mediana_resto !== null}
                                    {@const differenza = riga.mediana_trovati - riga.mediana_resto}
                                    <tr>
                                        <td class="numerico">{m.mese}</td>
                                        <td class="text-end numerico text-secondary">
                                            {m.investibili.toLocaleString("it")}
                                        </td>
                                        <td class="text-end numerico">{riga.trovati}</td>
                                        <td class="text-end numerico">
                                            {(riga.mediana_trovati * 100).toFixed(1)}%
                                        </td>
                                        <td class="text-end numerico text-secondary">
                                            {(riga.mediana_resto * 100).toFixed(1)}%
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
                    <Testo testo="Non e' un backtest di strategia: non si compra, non si vende, non ci sono costi ne' pesi di portafoglio. E' la domanda «cosa avresti trovato quel mese, e come sarebbe andata» ripetuta su tutti i mesi che i dati coprono." />
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
        {#if esitoAggiunta}
            <div class="alert alert-warning small py-2">{esitoAggiunta}</div>
        {/if}

        {#each risultato.trovati as trovato (trovato.symbol)}
            <div class="card mb-2">
                <div class="card-body py-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <!-- Il risultato dice il simbolo e i numeri che l'hanno
                             fatto trovare, non chi e': l'anteprima al passaggio
                             del mouse risponde a «ma questo chi e'?» senza
                             aprire e richiudere una pagina. -->
                        <span class="d-flex align-items-center gap-2">
                            <Ticker simbolo={trovato.symbol}
                                    classe="simbolo text-decoration-none" />
                            {#if inWatchlist.has(trovato.symbol)}
                                <span class="badge text-bg-success" title="gia' in watchlist">
                                    <i class="bi bi-bookmark-check" aria-hidden="true"></i>
                                </span>
                            {:else}
                                <button class="btn btn-sm btn-outline-primary py-0"
                                        disabled={aggiungendo.has(trovato.symbol)}
                                        title="aggiungi alla watchlist"
                                        onclick={() => aggiungi(trovato.symbol)}>
                                    <i class="bi bi-bookmark-plus" aria-hidden="true"></i>
                                </button>
                            {/if}
                        </span>
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
