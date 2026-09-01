<!--
    GraficoVoci.svelte — l'andamento di una o piu' voci di bilancio, al volo.
    feat: dalla tabella dei fondamentali al grafico senza passare da nessuna parte.

    Una tabella di ottantadue voci per venti trimestri e' un archivio, non una
    lettura: la domanda «questa voce sta salendo o scendendo?» si risponde a
    occhio solo se le cifre sono poche e vicine. Qui si scelgono le voci e si
    vede la forma.

    ## Perche' non riusa il grafico dei prezzi

    Quello disegna candele e indicatori su un asse temporale di sedute, con i
    nodi che decidono i pannelli. Qui ci sono N serie trimestrali, ognuna con la
    sua scala — i ricavi in miliardi e le azioni in circolazione in miliardi di
    PEZZI non stanno sullo stesso asse. Per questo c'e' l'interruttore
    **«confronta la forma»**, che porta tutte le serie a base 100 sul primo
    periodo: e' l'unico modo onesto di mettere insieme grandezze diverse.

    Senza quell'interruttore due voci di scala diversa producono un grafico in
    cui la piu' piccola e' una riga piatta sul fondo, e sembra che non si muova.
-->
<script>
    import { LineSeries, createChart } from "lightweight-charts";

    import Testo from "./Testo.svelte";

    let { voci = {}, periodi = [], scelte = [], altezza = 300 } = $props();

    // I colori delle serie, ripetuti se le voci sono piu' dei colori. Sono
    // quelli del monitor, gia' scelti per stare insieme su fondo scuro.
    const COLORI = ["#62d4ff", "#66d19e", "#f2c166", "#ff7b8d", "#b8eaff", "#8fa4b5"];

    // Il valore a cui si porta ogni serie nel confronto delle forme.
    const BASE_COMUNE = 100;

    let comune = $state(true);
    let contenitore;

    /** Le date dei periodi, dalla piu' vecchia. */
    const ordinati = $derived([...periodi].sort());

    /** Una voce come serie di punti, gia' pronta per la libreria. */
    function serieDi(nome) {
        const valori = voci[nome] ?? {};
        const punti = ordinati
            .filter((p) => valori[p] !== null && valori[p] !== undefined)
            .map((p) => ({ time: Math.floor(new Date(p).getTime() / 1000), valore: valori[p] }));

        if (!comune || punti.length === 0) {
            return punti.map((p) => ({ time: p.time, value: p.valore }));
        }

        // Base 100 sul primo periodo disponibile. Se il primo valore e' zero il
        // rapporto non esiste: quella voce non si puo' confrontare per forma, e
        // si mostra com'e' invece di dividere per zero.
        const primo = punti[0].valore;
        if (!primo) return punti.map((p) => ({ time: p.time, value: p.valore }));
        return punti.map((p) => ({ time: p.time, value: (p.valore / primo) * BASE_COMUNE }));
    }

    /** Le voci scelte che hanno un primo valore nullo: non si portano a base 100. */
    const nonConfrontabili = $derived(
        !comune ? [] : scelte.filter((nome) => {
            const valori = voci[nome] ?? {};
            const primo = ordinati.map((p) => valori[p]).find((v) => v !== null && v !== undefined);
            return !primo;
        })
    );

    function coloriTema() {
        const stile = getComputedStyle(document.documentElement);
        const prendi = (nome, fallback) => stile.getPropertyValue(nome).trim() || fallback;
        return {
            testo: prendi("--bs-body-color", "#e9f0f5"),
            griglia: prendi("--bs-border-color", "#263544")
        };
    }

    $effect(() => {
        if (!contenitore || scelte.length === 0 || ordinati.length === 0) return;

        const colori = coloriTema();
        const grafico = createChart(contenitore, {
            height: altezza,
            layout: { background: { color: "transparent" }, textColor: colori.testo,
                      attributionLogo: false },
            grid: { vertLines: { color: colori.griglia }, horzLines: { color: colori.griglia } },
            rightPriceScale: { borderColor: colori.griglia },
            timeScale: { borderColor: colori.griglia, timeVisible: false },
            crosshair: { mode: 0 }
        });

        scelte.forEach((nome, i) => {
            const dati = serieDi(nome);
            if (dati.length === 0) return;
            grafico.addSeries(LineSeries, {
                color: COLORI[i % COLORI.length], lineWidth: 2,
                priceLineVisible: false, lastValueVisible: false
            }).setData(dati);
        });

        grafico.timeScale().fitContent();
        return () => grafico.remove();
    });

    const etichetta = (nome) => nome.replaceAll("_", " ");
</script>

<div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
    <div class="d-flex flex-wrap gap-2 small">
        {#each scelte as nome, i (nome)}
            <span class="numerico" style={`color: ${COLORI[i % COLORI.length]}`}>
                ● <Testo testo={etichetta(nome)} />
            </span>
        {/each}
    </div>

    <button class="btn btn-sm btn-outline-secondary" class:active={comune}
            onclick={() => (comune = !comune)}>
        {comune ? "Confronta la forma (base 100)" : "Valori veri"}
    </button>
</div>

{#if comune}
    <p class="small text-secondary mb-1">
        <Testo testo="Ogni voce parte da 100 sul primo periodo. E' l'unico modo onesto di mettere insieme grandezze di scala diversa: coi valori veri la piu' piccola diventa una riga piatta sul fondo, e sembra che non si muova." />
    </p>
{/if}

{#if nonConfrontabili.length}
    <p class="small text-warning mb-1">
        Mostrate coi valori veri perche' partono da zero e non si possono portare
        a base 100: <Testo testo={nonConfrontabili.map(etichetta).join(", ")} />.
    </p>
{/if}

<div bind:this={contenitore} class="grafico"></div>
