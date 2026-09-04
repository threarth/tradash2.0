<!--
    Scia.svelte — cosa ha fatto finora un lavoro, riga per riga.
    feat: la stessa scia nel pannello in alto e nella scheda del titolo.

    E' un componente e non due elenchi uguali in due file: sono lo stesso dato
    guardato da due posti — dal pannello mentre fai altro, dalla scheda mentre
    aspetti quel referto — e due copie prima o poi divergono.

    **Dalla piu' recente.** Un log che cresce in fondo ha bisogno di seguire il
    proprio fondo, e un riquadro che si sposta da solo mentre lo leggi non si
    legge: cosi' la riga nuova arriva sempre nello stesso punto, in cima.
-->
<script>
    import Testo from "./Testo.svelte";

    let { lavoro } = $props();

    /** L'ora di un istante ISO, come la legge chi sta guardando adesso. */
    const ora = (iso) => new Date(iso).toLocaleTimeString("it");

    const righe = $derived([...(lavoro?.eventi ?? [])].reverse());
</script>

{#if righe.length > 0}
    <ol class="scia">
        {#each righe as evento (evento.quando + evento.testo)}
            <li>
                <span class="numerico text-secondary">{ora(evento.quando)}</span>
                <Testo testo={evento.testo} />
            </li>
        {/each}
    </ol>

    <!-- Un elenco tagliato che non dice di esserlo si legge come l'elenco
         intero: qui c'e' scritto quante righe sono rimaste fuori, e dove
         stanno quelle vere. -->
    {#if lavoro.eventi_totali > righe.length}
        <p class="small text-secondary mb-0">
            ultime {righe.length} righe di {lavoro.eventi_totali} · ogni chiamata
            al modello resta per intero in Operazioni
        </p>
    {/if}
{/if}

<style>
    .scia {
        list-style: none;
        margin: 0.5rem 0 0;
        padding: 0;
        font-size: 0.8125rem;
        line-height: 1.35;
    }

    .scia li {
        padding: 0.15rem 0;
        border-bottom: 1px solid var(--bs-border-color-translucent);
    }

    .scia li:last-child {
        border-bottom: none;
    }
</style>
