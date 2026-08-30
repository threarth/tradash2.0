<!--
    FilingDaSalvare.svelte — quali documenti SEC servono, e dove metterli.
    feat (Blocco 8): Defeatbeta ha l'indice dei depositi, non il loro testo.

    L'analisi qualitativa ha come fonte primaria il testo dei filing. Quel testo
    lo scarichi tu: qui c'e' l'elenco di quali servono, il collegamento per
    aprirli, la cartella in cui metterli e il nome proposto.

    Il nome proposto e' un suggerimento, non un requisito: il riconoscimento
    avviene sul numero di protocollo — la chiave univoca di EDGAR, che compare
    gia' nell'URL. Se salvi con un nome tuo ma quel numero c'e' dentro, il
    documento viene trovato lo stesso.
-->
<script>
    import Assente from "./Assente.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    let copiato = $state("");

    const dati = richiedi(() => api.filingDaSalvare(simbolo));

    $effect(() => {
        simbolo;
        dati.ricarica();
    });

    async function copia(testo, etichetta) {
        try {
            await navigator.clipboard.writeText(testo);
            copiato = `${etichetta} copiato`;
        } catch {
            copiato = `${etichetta}: copialo a mano`;
        }
    }
</script>

<Riquadro richiesta={dati} testoCaricamento="guardo quali documenti servono…">
    {#snippet children(d)}
        {#if d.documenti.length === 0}
            <Assente titolo="Nessun documento periodico"
                     motivo={d.reason}
                     azione="Defeatbeta non ha depositi 10-K o 10-Q per questo titolo" />
        {:else}
            <div class="d-flex flex-wrap gap-2 align-items-center mb-2 small">
                <span>
                    <strong>{d.pronti}</strong> documenti su {d.richiesti} gia' salvati
                </span>
                {#if d.completo}
                    <span class="badge text-bg-success">pronti</span>
                {:else}
                    <span class="badge text-bg-warning"><Testo testo={d.reason} /></span>
                {/if}
            </div>

            <div class="input-group input-group-sm mb-3">
                <span class="input-group-text">Cartella</span>
                <input class="form-control font-monospace" readonly value={d.cartella} />
                <button class="btn btn-outline-secondary"
                        onclick={() => copia(d.cartella, "Percorso")}>
                    <i class="bi bi-clipboard"></i>
                </button>
            </div>
            {#if copiato}
                <p class="small text-success">{copiato}</p>
            {/if}

            <div class="list-group">
                {#each d.documenti as documento (documento.accession_number)}
                    <div class="list-group-item">
                        <div class="d-flex justify-content-between align-items-start gap-2">
                            <div class="flex-grow-1 min-w-0">
                                <div class="small">
                                    <span class="badge {documento.presente
                                        ? 'text-bg-success' : 'text-bg-secondary'}">
                                        {documento.presente ? "c'e'" : "manca"}
                                    </span>
                                    <strong class="ms-1">{documento.form_type}</strong>
                                    <span class="text-secondary">
                                        periodo {documento.report_date} ·
                                        depositato {documento.filing_date}
                                    </span>
                                </div>
                                <div class="small font-monospace text-secondary text-truncate">
                                    {documento.presente
                                        ? documento.file.split("/").pop()
                                        : documento.nome_atteso}
                                </div>
                            </div>
                            <div class="d-flex gap-1">
                                {#if !documento.presente}
                                    <button class="btn btn-sm btn-outline-secondary"
                                            title="Copia il nome proposto"
                                            onclick={() =>
                                                copia(documento.nome_atteso, "Nome")}>
                                        <i class="bi bi-clipboard"></i>
                                    </button>
                                {/if}
                                <a class="btn btn-sm btn-outline-primary"
                                   href={documento.filing_url}
                                   target="_blank" rel="noopener noreferrer">
                                    apri su sec.gov ↗
                                </a>
                            </div>
                        </div>
                    </div>
                {/each}
            </div>

            <p class="small text-secondary mt-2 mb-0">
                Il nome proposto e' un suggerimento: il riconoscimento avviene sul
                numero di protocollo, che compare gia' nell'indirizzo. Un nome
                diverso va bene, purche' quel numero ci sia dentro.
            </p>
        {/if}
    {/snippet}
</Riquadro>
