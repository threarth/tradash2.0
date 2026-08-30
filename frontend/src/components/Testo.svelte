<!--
    Testo.svelte — IL componente di testo. Ogni frase dell'applicazione passa di qui.
    feat (Blocco 5): la sottolineatura del glossario e' sistematica, non ricordata.

    Il difetto che questo componente esiste per impedire: nel vecchio tradash la
    sottolineatura c'era, ma andava aggiunta a mano avvolgendo il testo in
    `GlossaryText`, e su tutto il frontend lo facevano **21 file**. Una copertura
    parziale che sembrava completa — se apri una pagina e i termini sono
    sottolineati, dai per scontato che lo siano ovunque.

    Qui la regola e': la prosa si scrive dentro `<Testo>`. Un test della suite
    legge i sorgenti e verifica che nessun componente stampi frasi fuori di qui
    senza essere nell'elenco delle eccezioni dichiarate.
-->
<script>
    import { glossario } from "../lib/glossario.svelte.js";

    let { children, testo = null, classe = "" } = $props();

    // Il testo puo' arrivare come prop (dai dati) o come contenuto scritto a
    // mano. Nel secondo caso non si puo' analizzare: sono nodi, non stringhe.
    const pezzi = $derived(testo === null ? null : glossario.segmenta(testo));
</script>

{#if pezzi}
    <span class={classe}>{#each pezzi as pezzo, indice (indice)}{#if pezzo.id}<button
        type="button" class="termine-glossario"
        title={glossario.termine(pezzo.id)?.short ?? ""}
        onclick={() => glossario.apri(pezzo.id)}>{pezzo.testo}</button>{:else}{pezzo.testo}{/if}{/each}</span>
{:else if testo !== null}
    <span class={classe}>{testo}</span>
{:else}
    <span class={classe}>{@render children()}</span>
{/if}
