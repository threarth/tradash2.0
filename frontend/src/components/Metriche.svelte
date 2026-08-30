<!--
    Metriche.svelte — ROE, margini, multipli, e il confronto col settore.
    feat (Blocco 8): calcolate dalla libreria di Defeatbeta, lette dal registro.

    Il confronto col settore e' la cosa che il vecchio tradash non sapeva fare:
    il suo registro dei peer copriva 7 ticker su 18, e per gli altri la domanda
    "questo ROE e' alto?" non aveva risposta. Qui la media dell'industria arriva
    insieme al dato del titolo, dalla stessa fonte.

    Nessuna metrica si calcola aprendo la pagina: si chiedono una alla volta
    (regola 2). Alcune costano trenta secondi, e la pagina lo dice prima.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "./Assente.svelte";
    import Errore from "./Errore.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    let scelta = $state("");
    let inCorso = $state(false);
    let risultato = $state(null);
    let errore = $state(null);

    const catalogo = richiedi(() => api.catalogoMetriche(simbolo));

    onMount(catalogo.ricarica);

    $effect(() => {
        simbolo;
        risultato = null;
        scelta = "";
    });

    async function carica(nome) {
        scelta = nome;
        inCorso = true;
        errore = null;
        risultato = null;
        try {
            risultato = await api.metrica(simbolo, nome);
        } catch (problema) {
            errore = problema;
        } finally {
            inCorso = false;
        }
    }

    /** I numeri leggibili: le percentuali come percentuali, i miliardi come miliardi. */
    function mostra(valore) {
        if (valore === null || valore === undefined) return "—";
        if (typeof valore !== "number") return String(valore);
        const assoluto = Math.abs(valore);
        if (assoluto >= 1e9) return `${(valore / 1e9).toLocaleString("it",
            { maximumFractionDigits: 2 })} mld`;
        if (assoluto >= 1e6) return `${(valore / 1e6).toLocaleString("it",
            { maximumFractionDigits: 1 })} mln`;
        return valore.toLocaleString("it", { maximumFractionDigits: 4 });
    }

    /** L'ultima riga di una serie: il valore che si guarda per primo. */
    const ultima = (serie) => serie?.righe?.at(-1) ?? null;
</script>

<Riquadro richiesta={catalogo} testoCaricamento="leggo quali metriche ci sono…">
    {#snippet children(d)}
        <div class="d-flex flex-wrap gap-1 mb-3">
            {#each d.metriche as metrica (metrica.nome)}
                <button class="btn btn-sm {scelta === metrica.nome
                            ? 'btn-primary' : 'btn-outline-secondary'}"
                        disabled={inCorso}
                        title={metrica.lenta
                            ? "Questa richiede una trentina di secondi"
                            : metrica.descrizione}
                        onclick={() => carica(metrica.nome)}>
                    {metrica.nome.replaceAll("_", " ")}
                    {#if metrica.lenta}<i class="bi bi-hourglass ms-1"></i>{/if}
                    {#if metrica.gemella_di_settore}
                        <i class="bi bi-diagram-2 ms-1" title="c'e' il confronto col settore"></i>
                    {/if}
                </button>
            {/each}
        </div>
    {/snippet}
</Riquadro>

{#if inCorso}
    <p class="small text-secondary">calcolo {scelta.replaceAll("_", " ")}…</p>
{/if}

{#if errore}
    <Errore {errore} />
{/if}

{#if risultato}
    <h3 class="h6"><Testo testo={risultato.descrizione} /></h3>

    {#if !risultato.titolo.available}
        <Assente motivo={risultato.titolo.reason} azione={risultato.titolo.action} />
    {:else}
        {@const riga = ultima(risultato.titolo)}
        {@const rigaSettore = ultima(risultato.settore)}

        {#if rigaSettore}
            <p class="small">
                Ultimo valore del titolo e della sua industria, per confronto — il
                dato che nel vecchio sistema mancava per undici titoli su diciotto.
            </p>
        {/if}

        <div class="table-responsive">
            <table class="table table-sm table-hover">
                <thead>
                    <tr>
                        {#each risultato.titolo.colonne as colonna (colonna)}
                            <th class={colonna === "report_date" ? "" : "text-end"}>
                                {colonna.replaceAll("_", " ")}
                            </th>
                        {/each}
                    </tr>
                </thead>
                <tbody>
                    {#each risultato.titolo.righe.slice().reverse() as r, indice (indice)}
                        <tr>
                            {#each risultato.titolo.colonne as colonna (colonna)}
                                <td class={colonna === "report_date" ? "small" : "numerico"}>
                                    {colonna === "report_date" ? r[colonna] : mostra(r[colonna])}
                                </td>
                            {/each}
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>

        {#if risultato.settore?.available}
            <h3 class="h6 mt-3">La stessa cosa, per l'industria</h3>
            <div class="table-responsive">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            {#each risultato.settore.colonne as colonna (colonna)}
                                <th class={colonna === "report_date" || colonna === "industry"
                                    ? "" : "text-end"}>{colonna.replaceAll("_", " ")}</th>
                            {/each}
                        </tr>
                    </thead>
                    <tbody>
                        {#each risultato.settore.righe.slice().reverse().slice(0, 6) as r, i (i)}
                            <tr>
                                {#each risultato.settore.colonne as colonna (colonna)}
                                    <td class={colonna === "report_date" || colonna === "industry"
                                        ? "small" : "numerico"}>
                                        {typeof r[colonna] === "number"
                                            ? mostra(r[colonna]) : (r[colonna] ?? "—")}
                                    </td>
                                {/each}
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {:else if risultato.settore}
            <Assente titolo="Nessun confronto di settore"
                     motivo={risultato.settore.reason}
                     azione={risultato.settore.action} />
        {/if}

        <p class="small text-secondary">
            Serie completa con le sue date: una ricostruzione a una data passata
            taglia qui, come per i bilanci.
        </p>
    {/if}
{/if}
