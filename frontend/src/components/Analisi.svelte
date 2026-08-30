<!--
    Analisi.svelte — le sette analisi, comprese quelle che non ci sono ancora.
    feat (Blocco 8): un metodo che manca lo dice, col perche'.

    Toglierle dall'elenco finche' non sono pronte le farebbe sparire, e
    un'analisi che manca senza dirlo e' indistinguibile da un'analisi che non
    serve. Qui ognuna dichiara la propria fonte e cosa le manca.

    Il costo si vede: un'analisi che gira senza che si sappia quanto brucia e'
    esattamente il difetto che il registro esiste per chiudere.
-->
<script>
    import { onMount } from "svelte";

    import Errore from "./Errore.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    let inCorso = $state(null);
    let referto = $state(null);
    let errore = $state(null);

    const metodi = richiedi(() => api.metodiAnalisi());
    const fatti = richiedi(() => api.referti(simbolo));

    onMount(() => {
        metodi.ricarica();
        fatti.ricarica();
    });

    // Cio' che non e' prosa da mostrare: sono i dati su cui il referto poggia,
    // e stanno gia' nelle loro sezioni della scheda.
    const TECNICI = new Set(["segnali", "metriche", "misure", "metriche_mancanti",
                             "call", "call_precedente", "testi_troncati",
                             "caratteri_originali", "confidenza", "lettura"]);

    /** Le sezioni a elenco del referto, quali che siano. */
    const sezioni = (contenuto) =>
        Object.entries(contenuto ?? {})
            .filter(([chiave, voci]) => !TECNICI.has(chiave) && Array.isArray(voci) && voci.length);

    const etichetta = (chiave) =>
        chiave.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

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
        <p class="small text-secondary">
            Speso finora con i modelli: <strong>${d.speso.costo_usd.toFixed(4)}</strong>
            su {d.speso.chiamate} chiamate.
        </p>

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
                                {inCorso === metodo.metodo ? "sto chiedendo…" : "Esegui"}
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
                        {#if r.contenuto.lettura}
                            <p><Testo testo={r.contenuto.lettura} /></p>
                        {/if}

                        <!-- Le sezioni si scoprono dal referto invece di essere
                             elencate qui: ogni metodo ne ha di sue — la
                             fondamentale ha punti di forza, l'earnings ha la
                             guidance — e un elenco fisso ne perderebbe una a
                             ogni metodo nuovo, senza dirlo. -->
                        {#each sezioni(r.contenuto) as [chiave, voci] (chiave)}
                            <div class="mt-2">
                                <div class="fw-semibold">{etichetta(chiave)}</div>
                                <ul class="mb-0">
                                    {#each voci as voce, i (i)}
                                        <li><Testo testo={String(voce)} /></li>
                                    {/each}
                                </ul>
                            </div>
                        {/each}

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
