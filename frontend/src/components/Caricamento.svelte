<!--
    Caricamento.svelte — "sto lavorando", detto in un modo solo.
    feat (Blocco 4): un'attesa senza spiegazione si legge come un blocco.
-->
<script>
    let { testo = "caricamento…" } = $props();
</script>

<div class="d-flex align-items-center gap-2 text-secondary py-3">
    <div class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></div>
    <span>{testo}</span>
</div>
