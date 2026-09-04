<!--
    SchedaTitolo.svelte — un titolo: a colpo d'occhio chiuso, modificabile aperto.
    feat (Blocco 4): la scheda del thematic-equity-monitor, ma editabile.

    Nel monitor la classificazione la scriveva un LLM in un file. Qui la scheda
    si apre e si cambia: temi, profilo e maturity sono attributi tuoi, e il
    posto giusto per correggerli e' quello in cui li stai guardando.

    Sotto agli attributi ci sono le due note: **perche'** questo titolo e' qui, e
    **cosa lo distingue** dagli altri dello stesso tema. Sono le due domande a
    cui il prompt di scoperta risponde gia' — e la cui risposta l'import
    buttava via. Adesso arrivano fin qui, e si correggono come tutto il resto:
    un perche' scritto da un modello sei mesi fa vale finche' non lo si
    riscrive.
-->
<script>
    import { untrack } from "svelte";

    import Nota from "./Nota.svelte";
    import Pillola from "./Pillola.svelte";
    import Valore from "./Valore.svelte";

    let { titolo, tag, profili, maturity, notaMax, onSalva, onRimuovi,
          onPreferito } = $props();

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
    let perche = $state("");
    let cosaLoDistingue = $state("");
    let salvataggio = $state(null);

    /** La firma di uno stato della scheda: due firme uguali, due schede uguali.

        E' JSON e non testo incollato con un separatore perche' le note sono
        testo libero: qualunque separatore si scegliesse, prima o poi qualcuno
        lo scriverebbe dentro una nota e due schede diverse sembrerebbero uguali.
    */
    const firma = (temi, profilo, maturita, motivo, distinzione) =>
        JSON.stringify([temi, profilo ?? "", maturita ?? "", motivo ?? "", distinzione ?? ""]);

    /** Com'e' il titolo adesso, secondo il backend. */
    const firmaSalvata = $derived(firma(
        titolo.temi.map((t) => t.nome), titolo.profilo, titolo.maturity,
        titolo.perche, titolo.cosa_lo_distingue
    ));

    // Ultima versione del backend che l'editor ha adottato.
    let firmaAdottata = $state(null);

    // L'editor si riallinea quando il dato di partenza cambia DAVVERO: dopo un
    // import, per esempio. Riallinearsi a ogni ricarica dell'elenco — che
    // avviene anche solo cliccando una stella — cancellerebbe invece le
    // modifiche che qualcuno sta scrivendo in un'altra scheda aperta.
    // `firmaAdottata` si legge senza tracciarla: e' scritta da questo stesso
    // effetto, e tracciarla lo fa ripartire per concludere che non c'e' niente
    // da fare. Qui converge grazie alla guardia — ma e' la stessa forma del
    // ciclo infinito che ha bloccato la scheda titolo, e una guardia e' l'unica
    // cosa che separa le due.
    $effect(() => {
        if (firmaSalvata !== untrack(() => firmaAdottata)) {
            firmaAdottata = firmaSalvata;
            temiScelti = titolo.temi.map((t) => t.nome);
            profiloScelto = titolo.profilo ?? "";
            maturityScelta = titolo.maturity ?? "";
            perche = titolo.perche ?? "";
            cosaLoDistingue = titolo.cosa_lo_distingue ?? "";
        }
    });

    const sporco = $derived(
        firma(temiScelti, profiloScelto, maturityScelta, perche, cosaLoDistingue)
            !== firmaSalvata
    );

    /** Quale nota sfora il tetto, se una sfora. Il backend rifiuta un testo
        troppo lungo invece di tagliarlo: qui lo si dice prima di provarci, e
        col numero, perche' «troppo lungo» senza un numero non dice di quanto. */
    const troppoLunga = $derived.by(() => {
        if (perche.trim().length > notaMax) return "Il perche'";
        if (cosaLoDistingue.trim().length > notaMax) return "Cosa lo distingue";
        return null;
    });

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
                maturity: maturityScelta || null,
                perche: perche.trim() || null,
                cosa_lo_distingue: cosaLoDistingue.trim() || null
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

            <div class="col-12 col-lg-6">
                <Nota id="perche-{titolo.symbol}" etichetta="Perche' e' in watchlist"
                      segnaposto="Cosa fa, a chi vende, e da dove viene il legame col tema."
                      massimo={notaMax} bind:valore={perche} />
            </div>

            <div class="col-12 col-lg-6">
                <Nota id="distingue-{titolo.symbol}" etichetta="Cosa lo distingue"
                      segnaposto="Che cosa ha, che gli altri dello stesso tema non hanno."
                      massimo={notaMax} bind:valore={cosaLoDistingue} />
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
                <button class="btn btn-sm btn-primary"
                        disabled={!sporco || troppoLunga !== null} onclick={salva}>
                    {sporco ? "Salva" : "Salvato"}
                </button>
            </div>
        </div>

        {#if troppoLunga}
            <div class="alert alert-warning py-2 small mt-2 mb-0">
                {troppoLunga} supera il tetto di {notaMax} caratteri: accorcialo per salvare.
            </div>
        {/if}

        {#if salvataggio}
            <div class="alert alert-danger py-2 small mt-2 mb-0">{salvataggio}</div>
        {/if}
    </div>
</details>
