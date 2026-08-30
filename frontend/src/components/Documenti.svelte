<!--
    Documenti.svelte — i depositi alla SEC e le notizie, con la stessa data.
    feat (Blocco 7): due elenchi semplici, tagliati su `as_of` quando serve.

    Qui il taglio e' esatto e non stimato: la data di deposito e' proprio la
    colonna che abbiamo, quindi "cosa esisteva quel giorno" e' un fatto.
-->
<script>
    import Assente from "./Assente.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    const filings = richiedi(() => api.filings(simbolo));
    const news = richiedi(() => api.news(simbolo));

    $effect(() => {
        simbolo;
        filings.ricarica();
        news.ricarica();
    });
</script>

<div class="row g-4">
    <div class="col-12 col-lg-6">
        <h2 class="h6">Depositi SEC</h2>
        <Riquadro richiesta={filings} testoCaricamento="carico i depositi…">
            {#snippet children(d)}
                {#if !d.available}
                    <Assente motivo={d.reason} azione={d.action} />
                {:else}
                    <p class="small text-secondary">
                        {d.documenti.length} mostrati su {d.totale}
                    </p>
                    <div class="list-group list-group-flush">
                        {#each d.documenti as documento (documento.filing_url)}
                            <a class="list-group-item list-group-item-action py-2"
                               href={documento.filing_url} target="_blank" rel="noopener noreferrer">
                                <div class="d-flex justify-content-between gap-2">
                                    <span class="fw-semibold small">{documento.form_type}</span>
                                    <span class="small text-secondary">{documento.filing_date}</span>
                                </div>
                                <div class="small text-secondary">
                                    <Testo testo={documento.form_type_description ?? ""} />
                                </div>
                            </a>
                        {/each}
                    </div>
                {/if}
            {/snippet}
        </Riquadro>
    </div>

    <div class="col-12 col-lg-6">
        <h2 class="h6">Notizie</h2>
        <Riquadro richiesta={news} testoCaricamento="carico le notizie…">
            {#snippet children(d)}
                {#if !d.available}
                    <Assente motivo={d.reason} azione={d.action} />
                {:else}
                    <div class="list-group list-group-flush">
                        {#each d.notizie as notizia (notizia.link)}
                            <a class="list-group-item list-group-item-action py-2"
                               href={notizia.link} target="_blank" rel="noopener noreferrer">
                                <div class="small"><Testo testo={notizia.title ?? ""} /></div>
                                <div class="small text-secondary">
                                    {notizia.publisher} · {notizia.report_date}
                                </div>
                            </a>
                        {/each}
                    </div>
                {/if}
            {/snippet}
        </Riquadro>
    </div>
</div>
