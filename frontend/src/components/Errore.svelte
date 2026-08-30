<!--
    Errore.svelte — quello che il backend ha detto, non "qualcosa e' andato storto".
    feat (Blocco 4): il messaggio arriva dall'inviluppo `{error}`.
-->
<script>
    import Testo from "./Testo.svelte";

    let { errore, riprova = null } = $props();
</script>

<div class="alert alert-danger d-flex gap-3 align-items-start" role="alert">
    <i class="bi bi-exclamation-triangle fs-5" aria-hidden="true"></i>
    <div class="flex-grow-1">
        <div class="fw-semibold">Richiesta non riuscita</div>
        <div class="small mt-1"><Testo testo={errore?.message ?? String(errore)} /></div>
        {#if riprova}
            <button class="btn btn-sm btn-outline-danger mt-2" onclick={riprova}>Riprova</button>
        {/if}
    </div>
</div>
