<!--
    Watchlist.svelte — i titoli che segui, nello stile del thematic-equity-monitor.
    feat (Blocco 4): filtri in cima, legenda, schede che si aprono e si modificano.

    Il monitor era una pagina generata: bella da leggere, immodificabile. Qui la
    stessa forma, ma ogni scheda si apre e si corregge — perche' temi, profilo e
    maturity sono giudizi tuoi, non dati scaricati.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "../components/Assente.svelte";
    import Freschezza from "../components/Freschezza.svelte";
    import ImportExport from "../components/ImportExport.svelte";
    import Legenda from "../components/Legenda.svelte";
    import Riquadro from "../components/Riquadro.svelte";
    import SchedaTitolo from "../components/SchedaTitolo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let filtroTema = $state("");
    let filtroProfilo = $state("");
    let filtroMaturity = $state("");
    let soloPreferiti = $state(false);
    let cerca = $state("");

    let daAggiungere = $state("");
    let esitoAggiunta = $state(null);
    let nuovoTag = $state("");
    let padreNuovoTag = $state("");

    const watchlist = richiedi(() =>
        api.watchlist({
            tag: filtroTema, profilo: filtroProfilo, maturity: filtroMaturity,
            preferiti: soloPreferiti ? 1 : ""
        })
    );

    onMount(watchlist.ricarica);

    /** La ricerca per simbolo si fa a video: i titoli sono decine, non migliaia. */
    const visibili = $derived.by(() => {
        const dati = watchlist.dato;
        if (!dati) return [];
        const cercato = cerca.trim().toUpperCase();
        return cercato ? dati.titoli.filter((t) => t.symbol.includes(cercato)) : dati.titoli;
    });

    const ambiti = (tag) => tag.filter((t) => t.parent === null);
    const sottoAmbiti = (tag) => tag.filter((t) => t.parent !== null);

    /** L'etichetta dell'ambito padre: nei menu si legge quella, non lo slug. */
    function nomePadre(etichetta) {
        if (!etichetta.parent) return "";
        const padre = watchlist.dato?.tag.find((t) => t.name === etichetta.parent);
        return `${padre?.label ?? etichetta.parent} / `;
    }

    async function aggiungi(evento) {
        evento.preventDefault();
        esitoAggiunta = null;
        try {
            esitoAggiunta = await api.watchlistAggiungi(daAggiungere, null);
            daAggiungere = "";
            await watchlist.ricarica();
        } catch (problema) {
            esitoAggiunta = { errore: problema.message };
        }
    }

    async function creaTag(evento) {
        evento.preventDefault();
        esitoAggiunta = null;
        try {
            await api.tagCrea(nuovoTag, padreNuovoTag || null);
            nuovoTag = "";
            padreNuovoTag = "";
            await watchlist.ricarica();
        } catch (problema) {
            esitoAggiunta = { errore: problema.message };
        }
    }

    async function salvaAttributi(simbolo, attributi) {
        await api.watchlistAttributi(simbolo, attributi);
        await watchlist.ricarica();
    }

    async function rimuovi(simbolo) {
        await api.watchlistRimuovi([simbolo]);
        await watchlist.ricarica();
    }

    async function cambiaPreferito(simbolo, valore) {
        await api.watchlistModifica({ simboli: [simbolo], preferito: valore });
        await watchlist.ricarica();
    }
</script>

<h1 class="h4 mb-3">Watchlist</h1>

<Riquadro richiesta={watchlist} testoCaricamento="leggo la watchlist…">
    {#snippet children(dati)}
        <div class="riga-filtri mb-3">
            <input class="form-control form-control-sm" bind:value={cerca}
                   placeholder="Cerca un simbolo" />

            <select class="form-select form-select-sm" bind:value={filtroTema}
                    onchange={watchlist.ricarica}>
                <option value="">Tutti i temi</option>
                {#each ambiti(dati.tag) as tag (tag.name)}
                    <option value={tag.name}>{tag.label} ({tag.totale})</option>
                {/each}
            </select>

            <select class="form-select form-select-sm" bind:value={filtroTema}
                    onchange={watchlist.ricarica}>
                <option value="">Tutti i sottoambiti</option>
                {#each sottoAmbiti(dati.tag) as tag (tag.name)}
                    <option value={tag.name}>{nomePadre(tag)}{tag.label} ({tag.totale})</option>
                {/each}
            </select>

            <select class="form-select form-select-sm" bind:value={filtroProfilo}
                    onchange={watchlist.ricarica}>
                <option value="">Tutti i profili</option>
                {#each dati.profili as valore (valore)}
                    <option value={valore}>{valore}</option>
                {/each}
            </select>

            <select class="form-select form-select-sm" bind:value={filtroMaturity}
                    onchange={watchlist.ricarica}>
                <option value="">Tutte le maturity</option>
                {#each dati.maturity as valore (valore)}
                    <option value={valore}>{valore}</option>
                {/each}
            </select>
        </div>

        <div class="d-flex justify-content-between align-items-center mb-2">
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="solo-preferiti"
                       bind:checked={soloPreferiti} onchange={watchlist.ricarica} />
                <label class="form-check-label small" for="solo-preferiti">Solo preferiti</label>
            </div>
            <span class="small text-secondary">
                {visibili.length} titoli visibili su {dati.titoli.length}
            </span>
        </div>

        <Legenda />

        {#if visibili.length === 0}
            <Assente titolo="Nessun titolo da mostrare"
                     motivo={dati.titoli.length === 0
                         ? "la watchlist e' vuota"
                         : "nessun titolo corrisponde ai filtri"}
                     azione={dati.titoli.length === 0
                         ? "aggiungi dei simboli qui sotto, o importa una classificazione"
                         : "allarga i filtri in cima"} />
        {:else}
            {#each visibili as titolo (titolo.symbol)}
                <SchedaTitolo {titolo} tag={dati.tag} profili={dati.profili}
                              maturity={dati.maturity}
                              notaMax={dati.nota_max_caratteri}
                              onSalva={salvaAttributi} onRimuovi={rimuovi}
                              onPreferito={cambiaPreferito} />
            {/each}
        {/if}

        <div class="row g-4 mt-3">
            <div class="col-12 col-lg-4">
                <form class="card h-100" onsubmit={aggiungi}>
                    <div class="card-body">
                        <h2 class="h6">Aggiungi titoli</h2>
                        <textarea class="form-control form-control-sm mb-2" rows="2"
                                  bind:value={daAggiungere}
                                  placeholder="NVDA, MU; TSM"></textarea>
                        <button class="btn btn-sm btn-primary" type="submit">Aggiungi</button>
                        {#if esitoAggiunta && !esitoAggiunta.errore}
                            <ul class="list-unstyled small mb-0 mt-2">
                                <li>Aggiunti: <strong>{esitoAggiunta.aggiunti.join(", ")
                                    || "nessuno"}</strong></li>
                                {#if esitoAggiunta.gia_presenti.length}
                                    <li class="text-secondary">Gia' presenti:
                                        {esitoAggiunta.gia_presenti.join(", ")}</li>
                                {/if}
                                {#if esitoAggiunta.scartati.length}
                                    <li class="text-warning">Scartati:
                                        {esitoAggiunta.scartati.join(", ")}</li>
                                {/if}
                                {#if esitoAggiunta.sconosciuti.length}
                                    <li class="text-warning">Sconosciuti all'universo:
                                        {esitoAggiunta.sconosciuti.join(", ")}</li>
                                {/if}
                                {#if esitoAggiunta.avvertimento}
                                    <li class="text-secondary">{esitoAggiunta.avvertimento}</li>
                                {/if}
                            </ul>
                        {/if}
                        {#if esitoAggiunta?.errore}
                            <div class="alert alert-danger py-2 small mt-2 mb-0">
                                {esitoAggiunta.errore}
                            </div>
                        {/if}
                    </div>
                </form>
            </div>

            <div class="col-12 col-lg-3">
                <form class="card h-100" onsubmit={creaTag}>
                    <div class="card-body">
                        <h2 class="h6">Nuovo tema</h2>
                        <input class="form-control form-control-sm mb-2" bind:value={nuovoTag}
                               placeholder="Semiconductors" />
                        <select class="form-select form-select-sm mb-2" bind:value={padreNuovoTag}>
                            <option value="">ambito di primo livello</option>
                            {#each ambiti(dati.tag) as tag (tag.name)}
                                <option value={tag.name}>sottoambito di {tag.label}</option>
                            {/each}
                        </select>
                        <button class="btn btn-sm btn-outline-primary" type="submit">Crea</button>
                    </div>
                </form>
            </div>

            <div class="col-12 col-lg-5">
                <ImportExport onImportato={watchlist.ricarica} />
            </div>
        </div>

        <hr class="my-4" />
        <h2 class="h6">Cosa e' ormai vecchio</h2>
        <p class="small text-secondary">
            La freschezza si guarda per categoria e non in blocco: il prezzo di
            un titolo puo' essere da rinfrescare mentre il suo profilo va
            benissimo, e chiedere tutto insieme vorrebbe dire riscaricare ogni
            volta anche cio' che non serve.
        </p>
        <Freschezza />
    {/snippet}
</Riquadro>
