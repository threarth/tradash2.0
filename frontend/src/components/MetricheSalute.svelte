<!--
    MetricheSalute.svelte — un grafico solo, e le metriche che ci si accendono sopra.
    feat: le figure di bilancio avevano un valore e nessuna storia.

    ## Un grafico, non dodici

    Dodici grafichini riempiono la pagina e non si confrontano: l'occhio non
    mette in relazione due riquadri lontani. Qui la linea si aggiunge a quella
    che c'e' gia', col colore dell'interruttore che l'ha accesa, e il confronto
    si fa dove serve — sovrapposto.

    ## Ogni metrica ha la SUA scala, ed e' una scelta dichiarata

    Il debito totale sta nei miliardi, la copertura degli interessi vale dieci:
    su una scala sola la seconda sarebbe una riga piatta sul fondo. Le
    alternative erano due, e nessuna e' gratis:

    * **normalizzare a base 100** — le forme diventano confrontabili in altezza,
      ma i numeri a video non sono piu' quelli veri, e un grafico che mostra
      numeri finti e' peggio di uno scomodo;
    * **una scala per metrica, nascosta** — i valori restano veri, le linee si
      confrontano nella FORMA e non nell'altezza. L'asse verticale non puo'
      dire nulla di sensato per tutte insieme, e infatti non c'e'.

    E' stata scelta la seconda, e la legenda porta il valore vero dell'ultimo
    trimestre: la forma la si guarda nel grafico, il numero si legge li'.
-->
<script>
    import { LineSeries, createChart } from "lightweight-charts";

    import Testo from "./Testo.svelte";

    let { figure = {}, rapporti = {}, altezza = 280 } = $props();

    // I colori delle metriche. Scelti per restare distinguibili sia sul tema
    // chiaro sia su quello scuro: un colore che sparisce su uno dei due rende
    // inutile proprio l'interruttore che lo accende.
    const COLORI = [
        "#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
        "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
        "#14b8a6", "#a855f7", "#eab308"
    ];

    // Quante ne puo' tenere accese insieme prima che il grafico diventi un
    // gomitolo. Non e' un limite tecnico: e' che sopra le cinque non si
    // distinguono piu'.
    const ACCESE_CONSIGLIATE = 5;

    const ETICHETTE = {
        patrimonio_netto: "Patrimonio netto",
        debito_totale: "Debito totale",
        cassa: "Cassa",
        debito_netto: "Debito netto",
        attivo_totale: "Attivo totale",
        passivo_totale: "Passivo totale",
        ebit_ttm: "EBIT (12 mesi)",
        ebitda_ttm: "EBITDA (12 mesi)",
        oneri_finanziari_ttm: "Oneri finanziari (12 mesi)",
        copertura_interessi: "Copertura interessi",
        debito_su_patrimonio: "Debito / patrimonio",
        copertura_attivi: "Attivo / passivo",
        debito_netto_su_ebitda: "Debito netto / EBITDA"
    };

    // Quali sono rapporti: si scrivono con due decimali e una «x», non in soldi.
    const SONO_RAPPORTI = new Set(Object.keys(ETICHETTE).slice(9));

    let contenitore;
    let accese = $state(new Set());

    /** Tutte le metriche disponibili, con la loro storia e il loro colore. */
    const disponibili = $derived(
        Object.entries({ ...figure, ...rapporti })
            .filter(([, punti]) => Array.isArray(punti) && punti.length > 1)
            .map(([chiave, punti], indice) => ({
                chiave,
                etichetta: ETICHETTE[chiave] ?? chiave,
                colore: COLORI[indice % COLORI.length],
                punti,
                ultimo: punti[punti.length - 1]
            }))
    );

    function alterna(chiave) {
        const nuove = new Set(accese);
        if (nuove.has(chiave)) nuove.delete(chiave);
        else nuove.add(chiave);
        accese = nuove;
    }

    /** Il valore dell'ultimo trimestre, scritto come va scritto quella metrica. */
    function scritto(metrica) {
        const v = metrica.ultimo?.valore;
        if (v === null || v === undefined) return "—";
        if (SONO_RAPPORTI.has(metrica.chiave)) return `${v.toFixed(2)}x`;
        return v.toLocaleString("it", { maximumFractionDigits: 0 });
    }

    const inSecondi = (periodo) =>
        Math.floor(new Date(`${periodo}T00:00:00Z`).getTime() / 1000);

    function coloriTema() {
        const stile = getComputedStyle(document.documentElement);
        const prendi = (nome, fallback) => stile.getPropertyValue(nome).trim() || fallback;
        return {
            testo: prendi("--bs-secondary-color", "#9bb0c4"),
            griglia: prendi("--bs-border-color", "#263544")
        };
    }

    // Il grafico si rifa' quando cambiano le metriche accese. Ricostruirlo costa
    // meno che riconciliare a mano quali serie togliere e quali aggiungere, e
    // non lascia niente dietro.
    $effect(() => {
        if (!contenitore || accese.size === 0) return;

        const colori = coloriTema();
        const grafico = createChart(contenitore, {
            height: altezza,
            layout: { background: { color: "transparent" }, textColor: colori.testo,
                      attributionLogo: false },
            grid: { vertLines: { color: colori.griglia },
                    horzLines: { color: colori.griglia } },
            rightPriceScale: { visible: false },
            timeScale: { borderColor: colori.griglia, timeVisible: false },
            crosshair: { mode: 0 }
        });

        for (const metrica of disponibili) {
            if (!accese.has(metrica.chiave)) continue;
            // Una scala per metrica, invisibile: e' cio' che permette di
            // sovrapporre miliardi e unita' senza appiattire le seconde.
            const serie = grafico.addSeries(LineSeries, {
                color: metrica.colore, lineWidth: 2,
                priceScaleId: metrica.chiave,
                priceLineVisible: false, lastValueVisible: false
            });
            grafico.priceScale(metrica.chiave).applyOptions({
                visible: false, scaleMargins: { top: 0.1, bottom: 0.1 }
            });
            serie.setData(metrica.punti
                .filter((p) => p.valore !== null && p.valore !== undefined)
                .map((p) => ({ time: inSecondi(p.periodo), value: p.valore })));
        }

        grafico.timeScale().fitContent();
        return () => grafico.remove();
    });
</script>

<div class="mb-2 d-flex flex-wrap gap-1">
    {#each disponibili as metrica (metrica.chiave)}
        <button class="btn btn-sm py-0 interruttore"
                class:acceso={accese.has(metrica.chiave)}
                style="--colore: {metrica.colore}"
                onclick={() => alterna(metrica.chiave)}>
            <span class="pastiglia"></span>
            {metrica.etichetta}
            <span class="numerico ms-1 text-secondary">{scritto(metrica)}</span>
        </button>
    {/each}
</div>

{#if accese.size === 0}
    <p class="small text-secondary mb-0">
        <Testo testo="Accendi una metrica qui sopra per vederne la storia. Se ne accendi piu' d'una si sovrappongono, ognuna col suo colore." />
    </p>
{:else}
    <div bind:this={contenitore}></div>
    <p class="small text-secondary mb-0 mt-1">
        <Testo testo="Ogni metrica ha la sua scala, nascosta: debito e rapporti differiscono di ordini di grandezza, e su una scala sola il piccolo sarebbe una riga piatta. Le linee si confrontano nella FORMA, non nell'altezza; il valore vero dell'ultimo trimestre e' accanto al nome." />
    </p>
    {#if accese.size > ACCESE_CONSIGLIATE}
        <p class="small text-warning mb-0">
            <Testo testo="Sopra le cinque linee insieme il grafico smette di dire qualcosa: non e' un limite, e' che non si distinguono piu'." />
        </p>
    {/if}
{/if}

<style>
    .interruttore {
        border: 1px solid var(--bs-border-color);
        color: var(--bs-body-color);
    }

    .interruttore.acceso {
        border-color: var(--colore);
        background-color: color-mix(in srgb, var(--colore) 14%, transparent);
    }

    /* Il pallino porta il colore della linea: e' l'unico legame fra
       l'interruttore e la riga che compare nel grafico. */
    .pastiglia {
        display: inline-block;
        width: 0.6rem;
        height: 0.6rem;
        border-radius: 50%;
        background-color: var(--colore);
        margin-right: 0.15rem;
    }

    .interruttore:not(.acceso) .pastiglia {
        opacity: 0.35;
    }
</style>
