<!--
    Valore.svelte — un numero, oppure il motivo per cui non c'e'.
    feat (Blocco 4): una cella vuota non dice niente; questa dice cosa manca.
-->
<script>
    import Testo from "./Testo.svelte";

    // `null` e `undefined` non sono zero: mostrarli come "0" sarebbe una bugia.
    let { valore, unita = "", decimali = 2, mancante = "n/d" } = $props();

    const MILLE = 1000;
    const MILIONE = 1_000_000;
    const MILIARDO = 1_000_000_000;

    /** Numeri grandi in forma leggibile: 4.670.485.000.000 diventa "4.670 mld". */
    function abbrevia(numero) {
        const assoluto = Math.abs(numero);
        if (assoluto >= MILIARDO) return `${(numero / MILIARDO).toLocaleString("it", {
            maximumFractionDigits: 0 })} mld`;
        if (assoluto >= MILIONE) return `${(numero / MILIONE).toLocaleString("it", {
            maximumFractionDigits: 1 })} mln`;
        if (assoluto >= MILLE) return numero.toLocaleString("it", { maximumFractionDigits: 0 });
        return numero.toLocaleString("it", { maximumFractionDigits: decimali });
    }
</script>

{#if valore === null || valore === undefined}
    <span class="assente" title="il backend non ha questo dato">{mancante}</span>
{:else if typeof valore === "number"}
    <span>{abbrevia(valore)}{unita}</span>
{:else}
    <span><Testo testo={String(valore)} />{unita}</span>
{/if}
