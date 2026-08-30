<!--
    Assente.svelte — la regola 5 vista dall'utente.
    feat (Blocco 4): mai una casella vuota, sempre motivo e azione.

    Il backend decide `available`, `reason` e `action`; questo componente li
    mostra. Il difetto che impedisce: un elenco vuoto senza spiegazione si
    legge come "non c'e' niente", quando quasi sempre vuol dire "non e' stato
    ancora chiesto".
-->
<script>
    import Testo from "./Testo.svelte";

    let { motivo, azione = null, titolo = "Non c'e' niente da mostrare", children } = $props();
</script>

<div class="alert alert-secondary d-flex gap-3 align-items-start" role="status">
    <i class="bi bi-info-circle fs-5" aria-hidden="true"></i>
    <div class="flex-grow-1">
        <div class="fw-semibold">{titolo}</div>
        {#if motivo}
            <div class="small mt-1"><Testo testo={motivo} /></div>
        {/if}
        {#if azione}
            <div class="small text-secondary mt-1">Cosa fare: <Testo testo={azione} /></div>
        {/if}
        {#if children}
            <div class="mt-2">{@render children()}</div>
        {/if}
    </div>
</div>
