<!--
    Pillola.svelte — un attributo detto a colpo d'occhio.
    feat (Blocco 4): la forma copiata dal thematic-equity-monitor.

    Il colore non e' decorazione: CORE verde, EMERGING ambra, OPTIONALITY rosso
    dicono quanto del valore di un titolo e' gia' provato, e sono la prima cosa
    che si legge scorrendo l'elenco.
-->
<script>
    let { testo, genere = "tema", titolo = null } = $props();

    const CLASSI = {
        CORE: "pillola-core",
        EMERGING: "pillola-emerging",
        OPTIONALITY: "pillola-optionality"
    };

    const classe = $derived(CLASSI[testo] ?? `pillola-${genere}`);
</script>

<span class="pillola {classe}" title={titolo}>{testo}</span>
