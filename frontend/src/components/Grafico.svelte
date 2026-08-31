<!--
    Grafico.svelte — il prezzo e i suoi indicatori, con lightweight-charts.
    feat (Blocco 6, ripreso): i controlli che aveva il vecchio tradash.

    Il disegno e' pilotato dai NODI: `resolvePanels` dice quanti pannelli
    servono e cosa ci va dentro, e questo componente si limita a creare le serie
    e a riempirle. Aggiungere un indicatore non tocca questo file — tocca
    `indicators.ts`, che e' la tabella condivisa col pannello laterale.

    lightweight-charts e' JavaScript puro e crea il proprio DOM dentro un
    contenitore che gli diamo noi: Svelte non lo considera suo, quindi non c'e'
    il conflitto che tiene fuori il JavaScript di Bootstrap. In compenso va
    distrutto a mano, ed e' quello che fa il ritorno di `$effect`.

    ## Cosa e' tornato dal vecchio grafico, e perche'

    - **La lettura OHLC sotto il cursore.** Un grafico senza numeri si guarda,
      non si legge: «quel giorno ha chiuso a quanto?» e' la domanda piu'
      frequente, e senza questa riga si risponde a occhio.
    - **Il punto fissato con ctrl+click.** Serve a rispondere a «quanto ha fatto
      DA LI'», che a occhio non si risponde affatto. Il vecchio usava
      shift+click; qui e' ctrl+click perche' shift+trascina e' gia' lo zoom
      della libreria.
    - **Lo zoom non si perde** quando si cambia tipo di grafico o si accende la
      griglia: l'intervallo visibile viene salvato e rimesso. Un grafico che
      torna al punto di partenza a ogni tocco costringe a rifare la strada.
-->
<script>
    import {
        CandlestickSeries, HistogramSeries, LineSeries, createChart, createSeriesMarkers
    } from "lightweight-charts";

    import Testo from "./Testo.svelte";
    import { KIND_META, priceOverlays, resolvePanels, seriesKeys } from "../lib/indicators.ts";

    let { barre = [], serie = {}, configurazione = { nodes: [] }, altezza = 420 } = $props();

    // Quanto spazio prende ogni pannello sotto il prezzo, in pixel.
    const ALTEZZA_PANNELLO = 130;

    const TIPI = { candele: "Candele", linea: "Linea" };

    let contenitorePrezzo;
    let contenitoriPannelli = $state({});

    let tipo = $state("candele");
    let griglia = $state(true);

    // Il punto fissato e la barra sotto il cursore. Non sono dipendenze
    // dell'effetto che costruisce il grafico: se lo fossero, ogni movimento del
    // mouse lo ricostruirebbe.
    let fissato = $state(null);
    let sottoIlCursore = $state(null);

    // Riferimenti vivi al grafico, tenuti FUORI dallo stato reattivo apposta.
    let serieCandele = null;
    let segnaposti = null;
    let ultimoIntervallo = null;
    let graficiVivi = [];

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

    const inSecondi = (iso) => Math.floor(new Date(iso).getTime() / 1000);

    /** Le candele, dalle barre grezze, indicizzate anche per tempo. */
    const candele = $derived(
        barre.map((b) => ({
            time: inSecondi(b.timestamp),
            open: b.open, high: b.high, low: b.low, close: b.close
        }))
    );

    const perTempo = $derived(new Map(barre.map((b) => [inSecondi(b.timestamp), b])));

    /** La barra da mostrare nella riga di lettura: quella sotto il cursore, o l'ultima. */
    const letta = $derived(sottoIlCursore ?? barre[barre.length - 1] ?? null);
    const barraFissata = $derived(fissato === null ? null : (perTempo.get(fissato) ?? null));

    /** Di quanto si e' mosso il prezzo dal punto fissato a quello letto. */
    const dalPunto = $derived(
        barraFissata && letta && barraFissata.close
            ? letta.close / barraFissata.close - 1
            : null
    );

    const percento = (frazione) =>
        frazione === null ? "—" : `${frazione >= 0 ? "+" : ""}${(frazione * 100).toFixed(2)}%`;

    const soldi = (valore) =>
        valore === null || valore === undefined ? "—" : Number(valore).toFixed(2);

    const giorno = (iso) => (iso ?? "").slice(0, 10);

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
        const linee = griglia ? { color: colori.griglia } : { visible: false };
        return createChart(contenitore, {
            height: altezzaGrafico,
            layout: { background: { color: "transparent" }, textColor: colori.testo,
                      attributionLogo: false },
            grid: { vertLines: linee, horzLines: linee },
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
            const tipoSerie = def.chart === "bar" ? HistogramSeries : LineSeries;
            const opzioni = def.chart === "bar"
                ? { color: colore, priceFormat: { type: "volume" } }
                : { color: colore, lineWidth: nodo.style?.strokeWidth ?? 1.5,
                    lineStyle: def.dash ? 2 : 0, priceLineVisible: false,
                    lastValueVisible: false };
            grafico.addSeries(tipoSerie, opzioni).setData(dati);
        }
    }

    /** Il segnaposto del punto fissato. Si aggiorna senza rifare il grafico. */
    function aggiornaSegnaposto() {
        if (!segnaposti) return;
        segnaposti.setMarkers(fissato === null ? [] : [{
            time: fissato, position: "belowBar", shape: "arrowUp",
            color: coloriTema().testo, text: "fissato"
        }]);
    }

    function fissa(tempo) {
        fissato = fissato === tempo ? null : tempo;
        aggiornaSegnaposto();
    }

    function togliIlPunto() {
        fissato = null;
        aggiornaSegnaposto();
    }

    /** Rimette tutta la storia dentro la finestra, e dimentica lo zoom salvato. */
    function adatta() {
        ultimoIntervallo = null;
        for (const grafico of graficiVivi) grafico.timeScale().fitContent();
    }

    // Il grafico si ricostruisce quando cambiano i dati, la configurazione, il
    // tipo o la griglia. Distruggerlo e rifarlo costa meno che riconciliare a
    // mano un albero di serie, e non lascia niente dietro.
    $effect(() => {
        if (!contenitorePrezzo || candele.length === 0) return;

        const grafici = [];
        graficiVivi = grafici;
        const prezzo = creaGrafico(contenitorePrezzo, altezza);
        const colori = coloriTema();

        serieCandele = tipo === "linea"
            ? prezzo.addSeries(LineSeries, { color: colori.su, lineWidth: 2 })
            : prezzo.addSeries(CandlestickSeries, {
                upColor: colori.su, downColor: colori.giu, borderVisible: false,
                wickUpColor: colori.su, wickDownColor: colori.giu
            });
        serieCandele.setData(tipo === "linea"
            ? candele.map((c) => ({ time: c.time, value: c.close }))
            : candele);

        segnaposti = createSeriesMarkers(serieCandele, []);
        aggiornaSegnaposto();

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

        // La lettura sotto il cursore. Fuori dal grafico si torna all'ultima
        // barra invece di svuotare la riga: una riga che sparisce fa saltare il
        // contenuto sotto.
        prezzo.subscribeCrosshairMove((evento) => {
            sottoIlCursore = evento?.time ? (perTempo.get(evento.time) ?? null) : null;
        });

        // Ctrl+click fissa il punto. Ctrl e non shift: shift+trascina e' gia' lo
        // zoom della libreria, e sovrapporli farebbe fissare punti per sbaglio.
        prezzo.subscribeClick((evento) => {
            const originale = evento?.sourceEvent;
            if (evento?.time && (originale?.ctrlKey || originale?.metaKey)) {
                fissa(evento.time);
            }
        });

        // Gli assi temporali si muovono insieme: due grafici sovrapposti che
        // scorrono per conto loro sono peggio di un grafico solo. E l'intervallo
        // visibile si conserva fra una ricostruzione e l'altra.
        for (const grafico of grafici) {
            grafico.timeScale().subscribeVisibleLogicalRangeChange((intervallo) => {
                if (!intervallo) return;
                ultimoIntervallo = intervallo;
                for (const altro of grafici) {
                    if (altro !== grafico) altro.timeScale().setVisibleLogicalRange(intervallo);
                }
            });
        }
        for (const grafico of grafici) {
            if (ultimoIntervallo) grafico.timeScale().setVisibleLogicalRange(ultimoIntervallo);
            else grafico.timeScale().fitContent();
        }

        return () => {
            serieCandele = null;
            segnaposti = null;
            graficiVivi = [];
            grafici.forEach((g) => g.remove());
        };
    });
</script>

<div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
    <div class="btn-group btn-group-sm" role="group">
        {#each Object.entries(TIPI) as [chiave, nome] (chiave)}
            <button type="button" class="btn btn-outline-secondary"
                    class:active={tipo === chiave} onclick={() => (tipo = chiave)}>
                {nome}
            </button>
        {/each}
    </div>

    <div class="d-flex align-items-center gap-2">
        <button type="button" class="btn btn-sm btn-outline-secondary"
                class:active={griglia} onclick={() => (griglia = !griglia)}>
            Griglia
        </button>
        <button type="button" class="btn btn-sm btn-outline-secondary" onclick={adatta}>
            Adatta
        </button>
        {#if fissato !== null}
            <button type="button" class="btn btn-sm btn-outline-secondary"
                    onclick={togliIlPunto}>
                Togli il punto fissato
            </button>
        {/if}
    </div>
</div>

<!-- La lettura sotto il cursore. Un grafico senza numeri si guarda, non si
     legge: «quel giorno ha chiuso a quanto?» e' la domanda piu' frequente. -->
{#if letta}
    <div class="small numerico d-flex flex-wrap gap-3 mb-1">
        <span class="text-secondary">{giorno(letta.timestamp)}</span>
        <span>A <strong>{soldi(letta.open)}</strong></span>
        <span>M <strong>{soldi(letta.high)}</strong></span>
        <span>m <strong>{soldi(letta.low)}</strong></span>
        <span>C <strong>{soldi(letta.close)}</strong></span>
        {#if letta.volume}
            <span class="text-secondary">vol {Number(letta.volume).toLocaleString("it")}</span>
        {/if}
        {#if barraFissata}
            <span class:text-success={dalPunto > 0} class:text-danger={dalPunto < 0}>
                dal {giorno(barraFissata.timestamp)}: {percento(dalPunto)}
            </span>
        {/if}
    </div>
{/if}

<div bind:this={contenitorePrezzo} class="grafico"></div>

{#if fissato === null}
    <p class="small text-secondary mt-1 mb-0">
        <Testo testo="Ctrl+click su un giorno per fissarlo: da li' in poi la riga sopra dice di quanto si e' mosso il prezzo." />
    </p>
{/if}

{#each pannelli as pannello (pannello.id)}
    <div class="mt-2">
        <div class="small text-secondary">{etichettaPannello(pannello)}</div>
        <div bind:this={contenitoriPannelli[pannello.id]} class="grafico"></div>
    </div>
{/each}
