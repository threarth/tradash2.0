<!--
    SchedaTitolo.svelte — un titolo: a colpo d'occhio chiuso, modificabile aperto.
    feat (Blocco 4): la scheda del thematic-equity-monitor, ma editabile.

    Nel monitor la classificazione la scriveva un LLM in un file. Qui la scheda
    si apre e si cambia: temi, profilo e maturity sono attributi tuoi, e il
    posto giusto per correggerli e' quello in cui li stai guardando.
-->
<script>
    import Pillola from "./Pillola.svelte";
    import Valore from "./Valore.svelte";

    let { titolo, tag, profili, maturity, onSalva, onRimuovi, onPreferito } = $props();

    /** "Semiconductors / " davanti a un sotto-ambito: l'etichetta del padre,
        non il suo nome interno, che e' uno slug e si legge male. */
    const nomePadre = (etichetta) => {
        if (!etichetta.parent) return "";
        const padre = tag.find((t) => t.name === etichetta.parent);
        return `${padre?.label ?? etichetta.parent} / `;
    };

    // Cio' che si sta modificando, staccato dal titolo: finche' non si salva,
    // l'elenco alle spalle non deve cambiare sotto le mani di chi scrive.
    let temiScelti = $state([]);
    let profiloScelto = $state("");
    let maturityScelta = $state("");
    let salvataggio = $state(null);

    /** Com'e' il titolo adesso, secondo il backend. */
    const firmaSalvata = $derived(
        [titolo.temi.map((t) => t.nome).join("|"), titolo.profilo ?? "",
         titolo.maturity ?? ""].join("\u00b7")
    );

    // Ultima versione del backend che l'editor ha adottato.
    let firmaAdottata = $state(null);

    // L'editor si riallinea quando il dato di partenza cambia DAVVERO: dopo un
    // import, per esempio. Riallinearsi a ogni ricarica dell'elenco — che
    // avviene anche solo cliccando una stella — cancellerebbe invece le
    // modifiche che qualcuno sta scrivendo in un'altra scheda aperta.
    $effect(() => {
        if (firmaSalvata !== firmaAdottata) {
            firmaAdottata = firmaSalvata;
            temiScelti = titolo.temi.map((t) => t.nome);
            profiloScelto = titolo.profilo ?? "";
            maturityScelta = titolo.maturity ?? "";
        }
    });

    const sporco = $derived(
        [temiScelti.join("|"), profiloScelto, maturityScelta].join("\u00b7") !== firmaSalvata
    );

    function alterna(nome) {
        temiScelti = temiScelti.includes(nome)
            ? temiScelti.filter((t) => t !== nome)
            : [...temiScelti, nome];
    }

    async function salva() {
        salvataggio = null;
        try {
            await onSalva(titolo.symbol, {
                tag: temiScelti,
                profilo: profiloScelto || null,
                maturity: maturityScelta || null
            });
        } catch (problema) {
            salvataggio = problema.message;
        }
    }
</script>

<details class="scheda-titolo">
    <summary>
        <span class="d-flex gap-3 align-items-center flex-grow-1 min-w-0">
            <button class="btn btn-sm btn-link p-0"
                    title={titolo.favorite ? "Togli dai preferiti" : "Segna come preferito"}
                    onclick={(evento) => {
                        evento.preventDefault();
                        onPreferito(titolo.symbol, !titolo.favorite);
                    }}>
                <i class="bi {titolo.favorite ? 'bi-star-fill text-warning' : 'bi-star'}"></i>
            </button>
            <a class="simbolo text-decoration-none" href="/titolo/{titolo.symbol}"
               onclick={(e) => e.stopPropagation()}>{titolo.symbol}</a>
            <span class="text-truncate">
                <span class="small">
                    {#if titolo.name}<Valore valore={titolo.name} /> · {/if}
                    <Valore valore={titolo.sector} mancante="non classificato" />
                </span>
                <small class="d-block text-secondary">
                    <Valore valore={titolo.industry} mancante="industria non classificata" />
                </small>
            </span>
        </span>

        <span class="d-flex gap-2 align-items-center flex-wrap justify-content-end">
            {#each titolo.temi as tema (tema.nome)}
                <Pillola testo={tema.etichetta} genere="tema"
                         titolo={tema.padre ? `sotto-ambito di ${tema.padre}` : "ambito"} />
            {/each}
            {#if titolo.profilo}
                <Pillola testo={titolo.profilo} />
            {/if}
            {#if titolo.maturity}
                <Pillola testo={titolo.maturity} genere="maturity" />
            {/if}
            <span class="numerico small text-secondary">
                <Valore valore={titolo.market_cap} />
            </span>
        </span>
    </summary>

    <div class="scheda-corpo">
        <div class="row g-3">
            <div class="col-12 col-lg-6">
                <div class="form-label small">Temi</div>
                <div class="d-flex flex-wrap gap-2">
                    {#each tag as etichetta (etichetta.name)}
                        <button class="btn btn-sm {temiScelti.includes(etichetta.name)
                                    ? 'btn-info' : 'btn-outline-secondary'}"
                                onclick={() => alterna(etichetta.name)}>
                            {nomePadre(etichetta)}{etichetta.label}
                        </button>
                    {/each}
                    {#if tag.length === 0}
                        <span class="assente small">nessun tema definito: creane uno qui sotto</span>
                    {/if}
                </div>
            </div>

            <div class="col-6 col-lg-3">
                <label class="form-label small" for="profilo-{titolo.symbol}">Profilo</label>
                <select id="profilo-{titolo.symbol}" class="form-select form-select-sm"
                        bind:value={profiloScelto}>
                    <option value="">non deciso</option>
                    {#each profili as valore (valore)}
                        <option value={valore}>{valore}</option>
                    {/each}
                </select>
            </div>

            <div class="col-6 col-lg-3">
                <label class="form-label small" for="maturity-{titolo.symbol}">Maturity</label>
                <select id="maturity-{titolo.symbol}" class="form-select form-select-sm"
                        bind:value={maturityScelta}>
                    <option value="">non decisa</option>
                    {#each maturity as valore (valore)}
                        <option value={valore}>{valore}</option>
                    {/each}
                </select>
            </div>
        </div>

        <div class="d-flex justify-content-between align-items-center mt-3">
            <div class="small text-secondary">
                In watchlist dal {titolo.added_at?.slice(0, 10)} ·
                ultima chiusura <Valore valore={titolo.last_close} />
                del <Valore valore={titolo.last_close_date} />
            </div>
            <div class="d-flex gap-2">
                <button class="btn btn-sm btn-outline-danger"
                        onclick={() => onRimuovi(titolo.symbol)}>
                    Togli dalla watchlist
                </button>
                <button class="btn btn-sm btn-primary" disabled={!sporco} onclick={salva}>
                    {sporco ? "Salva" : "Salvato"}
                </button>
            </div>
        </div>

        {#if salvataggio}
            <div class="alert alert-danger py-2 small mt-2 mb-0">{salvataggio}</div>
        {/if}
    </div>
</details>
