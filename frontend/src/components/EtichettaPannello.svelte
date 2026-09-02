<!--
    EtichettaPannello.svelte — l'interruttore di un pannello laterale.
    feat: aprire e chiudere devono essere lo stesso gesto, nello stesso posto.

    Prima il pulsante per chiudere stava dentro il pannello e quello per
    riaprirlo da un'altra parte: due bersagli diversi per una cosa sola, e il
    secondo si trovava solo cercandolo. Qui l'etichetta e' **la stessa** aperta
    o chiusa, resta dov'e', e si preme due volte per tornare al punto di prima.

    Sta appiccicata in alto e scritta in verticale quando il pannello e' chiuso:
    chiusa deve occupare una striscia, non una riga.
-->
<script>
    let { nome, aperto, cambia } = $props();
</script>

<button class="etichetta" class:chiusa={!aperto} onclick={cambia}
        aria-expanded={aperto} title={aperto ? `nascondi ${nome}` : `mostra ${nome}`}>
    <span class="segno">{aperto ? "\u00d7" : "\u2039"}</span>
    <span class="nome">{nome}</span>
</button>

<style>
    .etichetta {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: var(--bs-tertiary-bg);
        border: 1px solid var(--bs-border-color);
        border-radius: 0.25rem;
        color: var(--bs-secondary-color);
        padding: 0.15rem 0.5rem;
        font-family: var(--font-numeri);
        font-size: 0.7rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        cursor: pointer;
    }

    .etichetta:hover {
        color: var(--bs-body-color);
        border-color: var(--bs-secondary-color);
    }

    /* Chiusa: una striscia verticale, che ruba una colonna sottile invece di
       una riga intera in mezzo al contenuto. */
    .etichetta.chiusa {
        writing-mode: vertical-rl;
        padding: 0.5rem 0.15rem;
    }

    .segno {
        opacity: 0.7;
    }
</style>
