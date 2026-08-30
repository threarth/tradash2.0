<!--
    Grafico.svelte — il prezzo e i suoi indicatori, con lightweight-charts.
    feat (Blocco 6): il grafico che il vecchio tradash faceva in 1.674 righe.

    Il disegno e' pilotato dai NODI: `resolvePanels` dice quanti pannelli
    servono e cosa ci va dentro, e questo componente si limita a creare le serie
    e a riempirle. Aggiungere un indicatore non tocca questo file — tocca
    `indicators.ts`, che e' la tabella condivisa col pannello impostazioni.

    lightweight-charts e' JavaScript puro e crea il proprio DOM dentro un
    contenitore che gli diamo noi: Svelte non lo considera suo, quindi non c'e'
    il conflitto che tiene fuori il JavaScript di Bootstrap. In compenso va
    distrutto a mano, ed e' quello che fa il ritorno di `$effect`.
-->
<script>
    import { createChart, LineSeries, HistogramSeries, CandlestickSeries } from "lightweight-charts";

    import { priceOverlays, resolvePanels, seriesKeys, KIND_META } from "../lib/indicators.ts";

    let { barre = [], serie = {}, configurazione = { nodes: [] }, altezza = 420 } = $props();

    // Quanto spazio prende ogni pannello sotto il prezzo, in pixel.
    const ALTEZZA_PANNELLO = 130;

    let contenitorePrezzo;
    let contenitoriPannelli = $state({});

    const pannelli = $derived(resolvePanels(configurazione));
    const sovrapposti = $derived(priceOverlays(configurazione));

    /** Come si chiama un pannello: il nome del suo indicatore, piu' gli aggiunti. */
    function etichettaPannello(pannello) {
        const nomi = [pannello.owner, ...pannello.children].map(
            (n) => KIND_META[n.kind]?.label ?? n.kind
        );
        return nomi.join(" + ");
    }

    /** I punti {t, v} del backend nella forma che vuole la libreria. */
    function punti(chiave) {
        return (serie[chiave] ?? [])
            .filter((p) => p.v !== null && p.v !== undefined)
            .map((p) => ({ time: Math.floor(p.t / 1000), value: p.v }));
    }

    /** Le candele, dalle barre grezze. */
    const candele = $derived(
        barre.map((b) => ({
            time: Math.floor(new Date(b.timestamp).getTime() / 1000),
            open: b.open, high: b.high, low: b.low, close: b.close
        }))
    );

    /** I colori del tema, letti dal documento: il grafico segue chiaro e scuro. */
    function coloriTema() {
        const stile = getComputedStyle(document.documentElement);
        const prendi = (nome, fallback) => stile.getPropertyValue(nome).trim() || fallback;
        return {
            testo: prendi("--bs-body-color", "#e9f0f5"),
            griglia: prendi("--bs-border-color", "#263544"),
            su: prendi("--bs-success", "#66d19e"),
            giu: prendi("--bs-danger", "#ff7b8d")
        };
    }

    function creaGrafico(contenitore, altezzaGrafico) {
        const colori = coloriTema();
        return createChart(contenitore, {
            height: altezzaGrafico,
            layout: { background: { color: "transparent" }, textColor: colori.testo,
                      attributionLogo: false },
            grid: { vertLines: { color: colori.griglia }, horzLines: { color: colori.griglia } },
            rightPriceScale: { borderColor: colori.griglia },
            timeScale: { borderColor: colori.griglia, timeVisible: false },
            crosshair: { mode: 0 }
        });
    }

    /** Disegna un nodo dentro un grafico gia' creato. */
    function disegnaNodo(grafico, nodo) {
        const meta = KIND_META[nodo.kind];
        for (const { key, def } of seriesKeys(nodo)) {
            const dati = punti(key);
            if (dati.length === 0) continue;

            const colore = def.color ?? nodo.style?.color ?? meta?.defaultColor ?? "#62d4ff";
            const tipo = def.chart === "bar" ? HistogramSeries : LineSeries;
            const opzioni = def.chart === "bar"
                ? { color: colore, priceFormat: { type: "volume" } }
                : { color: colore, lineWidth: nodo.style?.strokeWidth ?? 1.5,
                    lineStyle: def.dash ? 2 : 0, priceLineVisible: false,
                    lastValueVisible: false };
            grafico.addSeries(tipo, opzioni).setData(dati);
        }
    }

    // Il grafico si ricostruisce quando cambiano i dati o la configurazione.
    // Distruggerlo e rifarlo costa meno che tenere in vita un albero di serie da
    // riconciliare a mano, e a ogni ricostruzione non resta niente dietro.
    $effect(() => {
        if (!contenitorePrezzo || candele.length === 0) return;

        const grafici = [];
        const prezzo = creaGrafico(contenitorePrezzo, altezza);
        const colori = coloriTema();
        prezzo.addSeries(CandlestickSeries, {
            upColor: colori.su, downColor: colori.giu, borderVisible: false,
            wickUpColor: colori.su, wickDownColor: colori.giu
        }).setData(candele);

        for (const nodo of sovrapposti) disegnaNodo(prezzo, nodo);
        grafici.push(prezzo);

        for (const pannello of pannelli) {
            const contenitore = contenitoriPannelli[pannello.id];
            if (!contenitore) continue;
            const sotto = creaGrafico(contenitore, ALTEZZA_PANNELLO);
            // Il proprietario del pannello, piu' gli overlay che gli stanno sopra:
            // una media mobile sul volume vive nel pannello del volume.
            disegnaNodo(sotto, pannello.owner);
            for (const figlio of pannello.children) disegnaNodo(sotto, figlio);
            grafici.push(sotto);
        }

        // Gli assi temporali si muovono insieme: due grafici sovrapposti che
        // scorrono per conto loro sono peggio di un grafico solo.
        for (const grafico of grafici) {
            grafico.timeScale().subscribeVisibleLogicalRangeChange((intervallo) => {
                if (!intervallo) return;
                for (const altro of grafici) {
                    if (altro !== grafico) altro.timeScale().setVisibleLogicalRange(intervallo);
                }
            });
            grafico.timeScale().fitContent();
        }

        return () => grafici.forEach((g) => g.remove());
    });
</script>

<div bind:this={contenitorePrezzo} class="grafico"></div>

{#each pannelli as pannello (pannello.id)}
    <div class="mt-2">
        <div class="small text-secondary">{etichettaPannello(pannello)}</div>
        <div bind:this={contenitoriPannelli[pannello.id]} class="grafico"></div>
    </div>
{/each}
