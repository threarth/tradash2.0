<!--
    SelettoreModello.svelte — quale modello risponde alle analisi.
    feat: il selettore globale del vecchio tradash, ridotto all'osso.

    Nel vecchio era una tabella di sedici task, ognuno col suo modello. Qui le
    fasi sono sette e usano tutte lo stesso: una tendina sola dice la verita'
    che c'e' da dire, e sedici righe da tenere allineate sarebbero sedici
    occasioni di scoprire un giorno che una fase gira su un modello che non
    ricordavi di aver scelto.

    Il nome sta SUL pulsante, non solo dentro al pannello: quale modello sta
    rispondendo e' cio' che cambia il conto, e un dato che si vede solo aprendo
    un menu e' un dato che si guarda quando ormai la spesa e' fatta.

    Il prezzo si vede accanto a ogni voce. Scegliere un modello e' scegliere
    quanto si paga, e la differenza fra due righe di questa tendina e' il conto
    di fine mese.
-->
<script>
    import { onMount } from "svelte";

    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";

    let aperto = $state(false);
    let dati = $state(null);
    let errore = $state(null);
    let salvando = $state(false);
    let scelto = $state("");

    async function carica() {
        try {
            dati = await api.impostazioniLlm();
            scelto = dati.modello;
            errore = null;
        } catch (problema) {
            errore = problema.message;
        }
    }

    onMount(carica);

    /** La riga di listino del modello scelto, se il listino ce l'ha. */
    const listino = $derived(dati?.modelli.find((m) => m.nome === scelto) ?? null);

    const cambiato = $derived(dati !== null && scelto !== dati.modello);

    async function salva() {
        salvando = true;
        errore = null;
        try {
            await api.scegliModello(scelto);
            await carica();
            aperto = false;
        } catch (problema) {
            errore = problema.message;
        } finally {
            salvando = false;
        }
    }

    function chiudiConEsc(evento) {
        if (evento.key === "Escape") aperto = false;
    }
</script>

<svelte:window onkeydown={chiudiConEsc} />

<div class="selettore-modello">
    <button class="btn btn-sm btn-outline-secondary" onclick={() => (aperto = !aperto)}
            title="Quale modello risponde alle analisi" aria-expanded={aperto}>
        <i class="bi bi-robot" aria-hidden="true"></i>
        <span class="d-none d-md-inline numerico">{dati?.modello ?? "…"}</span>
    </button>

    {#if aperto}
        <div class="menu-modello">
            <div class="d-flex justify-content-between align-items-start gap-2 mb-2">
                <strong class="small">Modello per tutte le analisi</strong>
                <button class="btn btn-sm btn-outline-secondary py-0"
                        onclick={() => (aperto = false)} aria-label="Chiudi">
                    <i class="bi bi-x-lg"></i>
                </button>
            </div>

            {#if dati}
                <select class="form-select form-select-sm" bind:value={scelto}>
                    {#each dati.modelli as modello (modello.nome)}
                        <option value={modello.nome}>
                            {modello.nome} — {modello.fornitore}
                        </option>
                    {/each}
                    <!-- Il file accetta anche un nome fuori elenco, scritto a
                         mano: se e' quello attuale deve comparire, altrimenti
                         la tendina mostrerebbe un modello che non e' in uso. -->
                    {#if !listino}
                        <option value={scelto}>{scelto} — fuori elenco</option>
                    {/if}
                </select>

                {#if listino}
                    <p class="small text-secondary mt-2 mb-1 numerico">
                        ${listino.ingresso.toFixed(2)} in entrata ·
                        ${listino.uscita.toFixed(2)} in uscita, per milione di token
                    </p>
                {:else}
                    <p class="small text-warning mt-2 mb-1">
                        <Testo testo="Di questo modello non conosciamo il listino: le sue chiamate risulteranno a costo zero finche' il prezzo non viene aggiunto. I token restano salvati, e «manage.py costi» ricalcola all'indietro." />
                    </p>
                {/if}

                <p class="small text-secondary mb-2">
                    Vale dalla prossima chiamata, comprese le analisi gia' aperte.
                    {#if !dati.scelto_da_te}
                        Adesso vale il predefinito ({dati.predefinito}).
                    {/if}
                </p>

                <button class="btn btn-sm btn-primary w-100"
                        disabled={!cambiato || salvando} onclick={salva}>
                    {salvando ? "salvo…" : cambiato ? "Usa questo" : "In uso"}
                </button>
            {:else if !errore}
                <p class="small text-secondary mb-0">leggo…</p>
            {/if}

            {#if errore}
                <p class="small text-danger mt-2 mb-0">{errore}</p>
            {/if}
        </div>
    {/if}
</div>

<style>
    .selettore-modello {
        position: relative;
    }

    /* Ancorato al pulsante e non al centro dello schermo: e' una scelta
       piccola, e un modale la farebbe sembrare una decisione grave. */
    .menu-modello {
        position: absolute;
        top: calc(100% + 0.35rem);
        right: 0;
        z-index: 1040;
        width: min(22rem, calc(100vw - 2rem));
        padding: 0.75rem;
        border: 1px solid var(--bs-border-color);
        border-radius: 0.5rem;
        background: var(--bs-body-bg);
        box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 25%);
    }
</style>
