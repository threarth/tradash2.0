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

    **La cartellina e' `fixed`, non `absolute`, e non e' un dettaglio di stile.**
    Le tabelle in cui compare scorrono dentro un contenitore alto al massimo
    ventisei righe: un elemento posizionato dentro a quel contenitore viene
    TAGLIATO dal suo bordo, e sulla prima riga — dove l'anteprima si apre verso
    l'alto — spariva la meta' superiore. Con `fixed` le coordinate si contano
    sullo schermo e nessun contenitore la ritaglia; in cambio vanno calcolate a
    mano al momento, e l'anteprima si chiude se la pagina scorre, perche' resta
    ferma mentre la riga sotto se ne va.
-->
<script module>
    import { api } from "../lib/api.js";

    // Quanto sta fermo il mouse prima che valga la pena chiedere: attraversare
    // una colonna non deve diventare una raffica di richieste.
    const RITARDO_MS = 250;

    // Quanto spazio prende la cartellina, per decidere da che parte aprirla.
    // E' una stima: misurarla davvero vorrebbe dire disegnarla, guardarla e
    // spostarla, cioe' vederla saltare. Sbagliare di poco non fa danno, perche'
    // le coordinate vengono comunque tenute dentro allo schermo.
    const ALTEZZA_STIMATA_PX = 170;
    const LARGHEZZA_PX = 240;
    const MARGINE_PX = 8;

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
    let posizione = $state("");
    let ancora;
    let attesa = null;

    /** Dove disegnare la cartellina, in coordinate dello schermo.

        Sopra al simbolo se c'e' posto, sotto altrimenti — e in ogni caso dentro
        ai bordi della finestra: su una tabella che scorre, la prima riga ha il
        bordo del contenitore appena sopra, e quella era la meta' che spariva. */
    function collocazione() {
        const punto = ancora.getBoundingClientRect();
        const ciSta = punto.top > ALTEZZA_STIMATA_PX + MARGINE_PX;
        const alto = ciSta
            ? punto.top - MARGINE_PX - ALTEZZA_STIMATA_PX
            : punto.bottom + MARGINE_PX;

        const massimo = window.innerWidth - LARGHEZZA_PX - MARGINE_PX;
        const sinistra = Math.max(MARGINE_PX, Math.min(punto.left, massimo));
        return `top: ${Math.max(MARGINE_PX, alto)}px; left: ${sinistra}px; ` +
               `width: ${LARGHEZZA_PX}px;`;
    }

    function entra() {
        attesa = setTimeout(async () => {
            posizione = collocazione();
            sopra = true;
            dato = await anagrafica(simbolo);
        }, RITARDO_MS);
    }

    function esce() {
        clearTimeout(attesa);
        sopra = false;
    }
</script>

<!-- Una cartellina ferma sullo schermo mentre la riga scorre via indicherebbe
     un titolo che non e' piu' li' sotto: alla prima rotella si chiude. -->
<svelte:window onscroll={esce} onresize={esce} />

<span class="ticker" bind:this={ancora}
      onmouseenter={entra} onmouseleave={esce}
      onfocusin={entra} onfocusout={esce}>
    <a class="numerico {classe}" class:fw-semibold={grassetto}
       href="/titolo/{simbolo}">{simbolo}</a>

    {#if sopra}
        <span class="anteprima small" role="tooltip" style={posizione}>
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
    /* Niente `position: relative` qui: la cartellina e' `fixed` e non si ancora
       al genitore. Lasciarlo suggerirebbe che qualcosa lo faccia. */
    .ticker {
        white-space: nowrap;
    }

    /* `fixed` e non `absolute`: dentro a una tabella che scorre, un elemento
       assoluto viene tagliato dal bordo del contenitore, e sulla prima riga
       spariva la meta' di sopra. Le coordinate le mette lo script. */
    .anteprima {
        position: fixed;
        z-index: 1050;
        padding: 0.5rem 0.65rem;
        white-space: normal;
        border: 1px solid var(--bs-border-color);
        border-radius: 0.375rem;
        background: var(--bs-body-bg);
        box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 25%);
        pointer-events: none;
    }
</style>
