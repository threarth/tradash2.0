<!--
    Analisi.svelte — le sette analisi, comprese quelle che non ci sono ancora.
    feat (Blocco 8): un metodo che manca lo dice, col perche'.

    Toglierle dall'elenco finche' non sono pronte le farebbe sparire, e
    un'analisi che manca senza dirlo e' indistinguibile da un'analisi che non
    serve. Qui ognuna dichiara la propria fonte e cosa le manca.

    Il costo si vede: un'analisi che gira senza che si sappia quanto brucia e'
    esattamente il difetto che il registro esiste per chiudere.

    E mentre gira si vede COSA sta facendo. Prima il pulsante scriveva «fase 1
    di 4» e restava fermo su quella scritta fino alla fine — anche quando era
    alla terza, anche quando era andata storta. Il registro sapeva tutto e
    nessuno glielo chiedeva: adesso la scheda guarda il lavoro che porta il
    proprio simbolo, e ne mostra la scia riga per riga.
-->
<script>
    import { onMount } from "svelte";

    import Errore from "./Errore.svelte";
    import Referto from "./Referto.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Scia from "./Scia.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { lavori } from "../lib/lavori.svelte.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    // Il lavoro che riguarda QUESTO titolo, se ce n'e' uno. Lo si riconosce
    // dall'ambito che il registro dichiara, non leggendo l'etichetta:
    // un'etichetta e' una frase per gli occhi, e cercarci dentro un simbolo
    // vorrebbe dire che cambiarla romperebbe questo.
    const mio = $derived(lavori.per(simbolo));

    $effect(() => lavori.guarda());

    let inCorso = $state(null);
    let referto = $state(null);
    let errore = $state(null);

    const metodi = richiedi(() => api.metodiAnalisi());
    const fatti = richiedi(() => api.referti(simbolo));

    onMount(() => {
        metodi.ricarica();
        fatti.ricarica();
    });

    async function esegui(metodo) {
        inCorso = metodo;
        errore = null;
        referto = null;
        try {
            referto = await api.eseguiAnalisi(metodo, simbolo);
            await Promise.all([fatti.ricarica(), metodi.ricarica()]);
        } catch (problema) {
            errore = problema;
        } finally {
            inCorso = null;
        }
    }
</script>

<Riquadro richiesta={metodi} testoCaricamento="leggo i metodi…">
    {#snippet children(d)}
        <p class="small text-secondary mb-1">
            Speso finora con i modelli: <strong>${d.speso.costo_usd.toFixed(4)}</strong>
            su {d.speso.chiamate} chiamate.
        </p>

        <!-- Un listino mancante si legge come "gratis": il totale resta a zero
             mentre i soldi escono. Va detto dove si guarda il totale. -->
        {#if d.speso.chiamate_senza_listino > 0}
            <p class="small text-warning">
                Di quelle, <strong>{d.speso.chiamate_senza_listino}</strong> non
                sanno quanto sono costate — manca il listino di
                {d.speso.modelli_senza_listino.join(", ")}, e i loro
                {d.speso.token_senza_listino.toLocaleString("it")} token non
                entrano nel totale qui sopra.
            </p>
        {/if}

        <div class="list-group mb-3">
            {#each d.metodi as metodo (metodo.metodo)}
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-start gap-2">
                        <div>
                            <div class="fw-semibold small">
                                <Testo testo={metodo.nome} />
                                <span class="text-secondary">— {metodo.natura}</span>
                            </div>
                            <div class="small text-secondary">
                                Fonte: <Testo testo={metodo.fonte} />
                            </div>
                            {#if !metodo.pronta}
                                <div class="small text-warning">
                                    Manca: <Testo testo={metodo.manca} />
                                </div>
                            {/if}
                        </div>
                        {#if metodo.pronta}
                            <button class="btn btn-sm btn-primary"
                                    disabled={inCorso !== null}
                                    onclick={() => esegui(metodo.metodo)}>
                                {#if inCorso !== metodo.metodo}
                                    Esegui
                                {:else if mio?.total}
                                    fase {Math.max(mio.done, 1)} di {mio.total}…
                                {:else}
                                    sto chiedendo…
                                {/if}
                            </button>
                        {:else}
                            <span class="badge text-bg-secondary">non ancora</span>
                        {/if}
                    </div>
                </div>
            {/each}
        </div>
    {/snippet}
</Riquadro>

<!-- La scia sta QUI, sotto ai metodi: e' la parte di pagina che si sta
     guardando mentre si aspetta, e mandarla a cercare nel pannello in alto
     vorrebbe dire spostare gli occhi da quello che si e' appena premuto. -->
{#if inCorso && mio}
    <div class="scia-analisi mb-3">
        <div class="small text-secondary">
            <Testo testo={mio.label} />
            {#if mio.total} · passo {mio.done} di {mio.total}{/if}
        </div>
        <Scia lavoro={mio} />
    </div>
{/if}

{#if errore}
    <Errore {errore} />
{/if}

{#if referto}
    <div class="alert alert-success py-2 small">
        Referto prodotto con {referto.contenuto ? "successo" : "—"}, costo
        ${referto.costo_usd.toFixed(4)}.
    </div>
{/if}

<Riquadro richiesta={fatti} testoCaricamento="leggo i referti…">
    {#snippet children(elenco)}
        {#if elenco.length === 0}
            <p class="small text-secondary">Nessun referto per questo titolo.</p>
        {:else}
            {#each elenco as r (r.id)}
                <details class="scheda-titolo">
                    <summary>
                        <span class="small">
                            <strong>{r.metodo}</strong> · {r.creato_il}
                        </span>
                        <span class="small text-secondary numerico">
                            {r.modello} · ${r.costo_usd.toFixed(4)}
                        </span>
                    </summary>
                    <div class="scheda-corpo small">
                        <Referto contenuto={r.contenuto} />

                        <p class="mt-2 mb-0 text-secondary">
                            {#if r.contenuto.confidenza}
                                Confidenza dichiarata: {r.contenuto.confidenza}.
                            {/if}
                            {#if r.contenuto.testi_troncati > 0}
                                {r.contenuto.testi_troncati} testi troncati prima di
                                arrivare al modello.
                            {/if}
                        </p>
                    </div>
                </details>
            {/each}
        {/if}
    {/snippet}
</Riquadro>

<style>
    /* Un riquadro che si distingue dal resto della scheda senza gridare: qui
       dentro le righe arrivano da sole mentre guardi. */
    .scia-analisi {
        padding: 0.5rem 0.75rem;
        border: 1px solid var(--bs-border-color);
        border-radius: 0.375rem;
        background: var(--bs-tertiary-bg);
    }
</style>
