<!--
    ImportExport.svelte — il giro completo: esci, classifichi altrove, rientri.
    feat (Blocco 4): prompt pronto, JSON in uscita, JSON in entrata.

    Il giro previsto e' questo: si copia il prompt — che porta con se' i valori
    ammessi e i temi che esistono gia', altrimenti l'LLM ne inventa di paralleli
    e l'import si riempie di doppioni — lo si incolla in un LLM insieme
    all'elenco dei titoli, e si riporta qui il JSON che risponde.

    L'esportato e l'importato hanno la STESSA forma: un formato per uscire e un
    altro per rientrare sarebbero due occasioni di sbagliare.
-->
<script>
    import { api } from "../lib/api.js";
    import Testo from "./Testo.svelte";

    let { onImportato } = $props();

    let daImportare = $state("");
    let esito = $state(null);
    let testoCopiato = $state("");

    async function copia(testo, etichetta) {
        try {
            await navigator.clipboard.writeText(testo);
            testoCopiato = `${etichetta} copiato`;
        } catch {
            // Gli appunti possono essere negati (permessi, contesto non sicuro):
            // il testo resta a video e si copia a mano.
            testoCopiato = `${etichetta} qui sotto: copialo a mano`;
        }
    }

    let anteprima = $state("");

    async function preparaPrompt() {
        esito = null;
        try {
            const risposta = await api.prompt();
            anteprima = risposta.prompt;
            await copia(risposta.prompt, "Prompt");
        } catch (problema) {
            esito = { errore: problema.message };
        }
    }

    async function esporta() {
        esito = null;
        try {
            const dati = await api.esporta();
            anteprima = JSON.stringify(dati, null, 2);
            await copia(anteprima, "JSON della watchlist");
        } catch (problema) {
            esito = { errore: problema.message };
        }
    }

    async function importa() {
        esito = null;
        let dati;
        try {
            dati = JSON.parse(daImportare);
        } catch (problema) {
            esito = { errore: `il testo non e' JSON valido: ${problema.message}` };
            return;
        }
        try {
            esito = await api.importa(dati);
            daImportare = "";
            await onImportato();
        } catch (problema) {
            esito = { errore: problema.message };
        }
    }
</script>

<div class="card">
    <div class="card-body">
        <h2 class="h6">Classificare altrove, riportare qui</h2>
        <p class="small text-secondary">
            Copia il prompt, incollalo in un LLM, riporta qui il JSON che risponde.
            Il prompt porta con se' i valori ammessi e i temi che esistono gia'.
        </p>

        <div class="d-flex gap-2 flex-wrap mb-2">
            <button class="btn btn-sm btn-outline-primary" onclick={preparaPrompt}>
                <i class="bi bi-clipboard"></i> Copia il prompt
            </button>
            <button class="btn btn-sm btn-outline-secondary" onclick={esporta}>
                <i class="bi bi-box-arrow-up"></i> Esporta la watchlist
            </button>
            {#if testoCopiato}
                <span class="small text-success align-self-center">{testoCopiato}</span>
            {/if}
        </div>

        {#if anteprima}
            <textarea class="form-control form-control-sm mb-3" rows="6" readonly
                      value={anteprima}></textarea>
        {/if}

        <label class="form-label small" for="da-importare">JSON classificato da importare</label>
        <textarea id="da-importare" class="form-control form-control-sm mb-2" rows="4"
                  bind:value={daImportare}
                  placeholder={'{ "titoli": [ { "symbol": "MU", "tag": ["semiconductors.memory"], '
                      + '"profilo": "CORE", "maturity": "SCALED" } ] }'}></textarea>
        <button class="btn btn-sm btn-primary" disabled={!daImportare.trim()} onclick={importa}>
            <i class="bi bi-box-arrow-in-down"></i> Importa
        </button>

        {#if esito}
            <div class="mt-2">
                {#if esito.errore}
                    <div class="alert alert-danger py-2 small mb-0">{esito.errore}</div>
                {:else}
                    <ul class="list-unstyled small mb-0">
                        <li>Aggiornati: <strong>{esito.aggiornati.length}</strong> ·
                            aggiunti: <strong>{esito.aggiunti.length}</strong></li>
                        {#if esito.tag_creati.length}
                            <li class="text-info">Temi creati: {esito.tag_creati.join(", ")}</li>
                        {/if}
                        {#if esito.sconosciuti.length}
                            <li class="text-warning">Sconosciuti all'universo:
                                {esito.sconosciuti.join(", ")}</li>
                        {/if}
                        {#if esito.scartati.length}
                            <li class="text-warning">Scartati, non hanno la forma di un simbolo:
                                {esito.scartati.join(", ")}</li>
                        {/if}
                        {#each esito.rifiutati as rifiutato (rifiutato.symbol)}
                            <li class="text-danger">{rifiutato.symbol}: <Testo testo={rifiutato.motivo} /></li>
                        {/each}
                    </ul>
                {/if}
            </div>
        {/if}
    </div>
</div>
