<!--
    Ticker.svelte — un simbolo, e cosa c'e' dietro senza andarci.
    feat: l'anteprima al passaggio del mouse del vecchio tradash.

    In un elenco di venti candidati la domanda «ma questo chi e'?» si fa venti
    volte, e ogni volta costava una pagina aperta e una chiusa. Qui basta
    fermarcisi sopra: nome, settore, industria e dimensione compaiono accanto al
    simbolo, e il click resta quello di prima — apre la scheda.

    **Si legge una volta sola per simbolo.** La cache sta nel modulo e non nel
    componente: lo stesso ticker puo' comparire in due tabelle, e la seconda non
    deve richiedere quello che la prima ha gia' chiesto. Le richieste in volo si
    condividono, altrimenti passare velocemente su una colonna ne farebbe partire
    una per ogni riga sfiorata.

    **Non parte al montaggio.** Un elenco di venti simboli che si prepara
    l'anteprima di tutti sarebbe venti richieste per una che ne servira': si
    legge quando il mouse si ferma davvero, dopo un attimo di ritardo.
-->
<script module>
    import { api } from "../lib/api.js";

    // Quanto sta fermo il mouse prima che valga la pena chiedere: attraversare
    // una colonna non deve diventare una raffica di richieste.
    const RITARDO_MS = 250;

    // Cio' che si e' gia' letto, e cio' che si sta leggendo adesso.
    const memoria = new Map();
    const in_volo = new Map();

    /** Legge una volta sola per simbolo, condividendo le richieste in corso. */
    function anagrafica(simbolo) {
        if (memoria.has(simbolo)) return Promise.resolve(memoria.get(simbolo));
        if (in_volo.has(simbolo)) return in_volo.get(simbolo);

        const richiesta = api.universoTitolo(simbolo)
            .then((dato) => {
                memoria.set(simbolo, dato);
                return dato;
            })
            .catch((problema) => {
                // Un'anteprima che non arriva non e' un guasto della pagina: si
                // dichiara nella cartellina e non si ritenta da sola.
                const guasto = { disponibile: false, symbol: simbolo,
                                 motivo: problema.message };
                memoria.set(simbolo, guasto);
                return guasto;
            })
            .finally(() => in_volo.delete(simbolo));

        in_volo.set(simbolo, richiesta);
        return richiesta;
    }
</script>

<script>
    import Testo from "./Testo.svelte";
    import Valore from "./Valore.svelte";

    let { simbolo, grassetto = false, classe = "" } = $props();

    let dato = $state(memoria.get(simbolo) ?? null);
    let sopra = $state(false);
    let attesa = null;

    function entra() {
        attesa = setTimeout(async () => {
            sopra = true;
            dato = await anagrafica(simbolo);
        }, RITARDO_MS);
    }

    function esce() {
        clearTimeout(attesa);
        sopra = false;
    }
</script>

<span class="ticker" onmouseenter={entra} onmouseleave={esce}
      onfocusin={entra} onfocusout={esce}>
    <a class="numerico {classe}" class:fw-semibold={grassetto}
       href="/titolo/{simbolo}">{simbolo}</a>

    {#if sopra}
        <span class="anteprima small" role="tooltip">
            <span class="numerico fw-semibold">{simbolo}</span>
            {#if !dato}
                <span class="d-block text-secondary">leggo…</span>
            {:else if !dato.disponibile}
                <!-- Il motivo arriva dal backend ed e' prosa: passa dal
                     glossario come tutto il resto. -->
                <span class="d-block text-secondary"><Testo testo={dato.motivo} /></span>
            {:else}
                {#if dato.name}<span class="d-block">{dato.name}</span>{/if}
                <span class="d-block text-secondary">
                    <Valore valore={dato.sector} mancante="settore non classificato" />
                </span>
                <span class="d-block text-secondary">
                    <Valore valore={dato.industry} mancante="industria non classificata" />
                </span>
                <span class="d-block numerico">
                    <Valore valore={dato.market_cap} /> di capitalizzazione
                </span>
                {#if dato.last_close}
                    <span class="d-block numerico text-secondary">
                        ultima chiusura <Valore valore={dato.last_close} />
                        del <Valore valore={dato.last_close_date} />
                    </span>
                {/if}
            {/if}
        </span>
    {/if}
</span>

<style>
    .ticker {
        position: relative;
        white-space: nowrap;
    }

    /* Sopra alla riga e non sotto: in una tabella lunga il posto sotto e'
       occupato dalla riga dopo, e l'anteprima la coprirebbe proprio mentre la
       si sta confrontando. */
    .anteprima {
        position: absolute;
        bottom: 100%;
        left: 0;
        z-index: 1050;
        width: 15rem;
        padding: 0.5rem 0.65rem;
        margin-bottom: 0.25rem;
        white-space: normal;
        border: 1px solid var(--bs-border-color);
        border-radius: 0.375rem;
        background: var(--bs-body-bg);
        box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 25%);
        pointer-events: none;
    }
</style>
