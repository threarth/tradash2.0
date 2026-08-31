<!--
    PannelloIndicatori.svelte — quali indicatori disegnare, e come.
    feat (Blocco 6, ripreso): il pannello laterale che aveva il vecchio tradash.

    Il vocabolario e' UNO SOLO: `lib/indicators.ts`, la stessa tabella che il
    grafico usa per disegnare e che il backend rispecchia in `domain/indicators.py`.
    Qui non c'e' nessun elenco di indicatori scritto a mano — se ce ne fosse uno,
    aggiungere un indicatore vorrebbe dire ricordarsi di toccare due posti, e il
    secondo prima o poi si dimentica.

    **Niente si salva da solo.** Le modifiche restano locali finche' non premi
    Salva: un pannello che scrive a ogni click farebbe partire un ricalcolo del
    grafico per ogni cifra digitata dentro un periodo.
-->
<script>
    import Assente from "./Assente.svelte";
    import Errore from "./Errore.svelte";
    import Testo from "./Testo.svelte";
    import {
        ALL_KINDS, BASE_PRICE, BASE_VOLUME, KIND_META, makeNode
    } from "../lib/indicators.ts";
    import { api } from "../lib/api.js";

    let { simbolo, configurazione = { nodes: [] }, salvata } = $props();

    // Copia di lavoro: si tocca questa, e solo Salva la manda al backend.
    let nodi = $state(structuredClone(configurazione.nodes ?? []));
    let daAggiungere = $state("ema");
    let inCorso = $state(false);
    let errore = $state(null);

    // Se il grafico viene ricaricato da fuori (cambio titolo), si riparte da li'.
    let ultimaVista = $state(JSON.stringify(configurazione.nodes ?? []));
    $effect(() => {
        const arrivata = JSON.stringify(configurazione.nodes ?? []);
        if (arrivata !== ultimaVista) {
            ultimaVista = arrivata;
            nodi = structuredClone(configurazione.nodes ?? []);
        }
    });

    const modificato = $derived(JSON.stringify(nodi) !== ultimaVista);

    const nome = (nodo) => KIND_META[nodo.kind]?.label ?? nodo.kind;
    const parametri = (nodo) => KIND_META[nodo.kind]?.params ?? [];
    const haColore = (nodo) => KIND_META[nodo.kind]?.hasStyle ?? false;

    /** Su cosa si appoggia un indicatore nuovo: il prezzo, o il volume. */
    function sorgenteDi(kind) {
        return KIND_META[kind]?.sourceConstraint === "volume" ? BASE_VOLUME : BASE_PRICE;
    }

    function aggiungi() {
        nodi = [...nodi, makeNode(daAggiungere, sorgenteDi(daAggiungere))];
    }

    function togli(id) {
        nodi = nodi.filter((n) => n.id !== id);
    }

    async function salva() {
        inCorso = true;
        errore = null;
        try {
            await api.titoloSalvaGrafico(simbolo, { nodes: nodi });
            ultimaVista = JSON.stringify(nodi);
            await salvata?.();
        } catch (problema) {
            errore = problema;
        } finally {
            inCorso = false;
        }
    }
</script>

<div class="d-flex justify-content-between align-items-center mb-2">
    <h3 class="h6 mb-0">Indicatori</h3>
    <button class="btn btn-sm btn-primary" disabled={!modificato || inCorso} onclick={salva}>
        {inCorso ? "salvo…" : "Salva"}
    </button>
</div>

{#if errore}
    <Errore {errore} />
{/if}

<div class="d-flex gap-2 mb-3">
    <select class="form-select form-select-sm" bind:value={daAggiungere}>
        {#each ALL_KINDS as kind (kind)}
            <option value={kind}>{KIND_META[kind].label}</option>
        {/each}
    </select>
    <button class="btn btn-sm btn-outline-secondary" onclick={aggiungi}>Aggiungi</button>
</div>

{#if nodi.length === 0}
    <Assente titolo="Nessun indicatore"
             motivo="il grafico mostra solo il prezzo"
             azione="scegline uno qui sopra e premi Aggiungi" />
{/if}

<div class="list-group list-group-flush">
    {#each nodi as nodo (nodo.id)}
        <div class="list-group-item px-0">
            <div class="d-flex align-items-center gap-2">
                <input class="form-check-input mt-0" type="checkbox" bind:checked={nodo.enabled}
                       aria-label={`mostra ${nome(nodo)}`} />
                <span class="small fw-semibold flex-grow-1">
                    <Testo testo={nome(nodo)} />
                    {#if nodo.source === BASE_VOLUME}
                        <span class="text-secondary">sul volume</span>
                    {/if}
                </span>
                {#if haColore(nodo)}
                    <input type="color" class="form-control form-control-color form-control-sm"
                           bind:value={nodo.style.color} aria-label={`colore di ${nome(nodo)}`} />
                {/if}
                <button class="btn btn-sm btn-link text-danger p-0" onclick={() => togli(nodo.id)}
                        aria-label={`togli ${nome(nodo)}`}>togli</button>
            </div>

            {#each parametri(nodo) as parametro (parametro.key)}
                <div class="d-flex align-items-center gap-2 mt-1 small">
                    <label class="text-secondary flex-grow-1" for={`${nodo.id}-${parametro.key}`}>
                        {parametro.label}
                    </label>
                    <!-- I limiti vengono dalla tabella degli indicatori, non da
                         qui: un periodo fuori scala lo rifiuterebbe il backend,
                         e vale la pena non arrivarci. -->
                    <input id={`${nodo.id}-${parametro.key}`} type="number"
                           class="form-control form-control-sm" style="width: 6rem"
                           min={parametro.min} max={parametro.max} step={parametro.step ?? 1}
                           bind:value={nodo.params[parametro.key]} />
                </div>
            {/each}
        </div>
    {/each}
</div>

{#if modificato}
    <p class="small text-warning mt-2 mb-0">
        Modifiche non salvate: il grafico mostra ancora quelle di prima.
    </p>
{/if}
