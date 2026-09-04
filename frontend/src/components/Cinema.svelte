<!--
    Cinema.svelte — la stessa storia, ma un giorno alla volta.
    feat: torna la modalita' «cinema» del vecchio tradash, a velocita' regolabile.

    La tabella mostra tutto insieme — ed e' esattamente cio' che chi teneva il
    titolo non vedeva. Guardata a consuntivo, una discesa del 60% e' una macchia
    rossa larga tre colonne; vissuta un giorno alla volta e' quattordici mesi in
    cui ogni mattina il numero e' ancora sotto. Sono due informazioni diverse, e
    la seconda e' quella che decide se una posizione la si sarebbe tenuta.

    Per questo il grafico **non conosce il futuro**: la scala verticale si
    ricalcola sui soli giorni gia' scoperti. Con una scala fissa su tutta la
    corsa si vedrebbe dal primo fotogramma quanto in alto si arrivera', che e'
    precisamente l'informazione che chi lo viveva non aveva.

    Parte fermo. Come tutto il resto qui, si preme.
-->
<script>
    import { untrack } from "svelte";

    import Testo from "./Testo.svelte";
    import { percento, soldi } from "../lib/numeri.js";

    let { andamento = [], capitale = 0 } = $props();

    // Da mezza seduta al secondo — per rivivere lento un tratto brutto — fino a
    // centoventi, che su vent'anni di prezzi e' l'unica velocita' con cui si
    // arriva in fondo. I valori sono quelli del vecchio tradash, gia' tarati.
    const VELOCITA_MIN = 0.5;
    const VELOCITA_MAX = 120;
    const VELOCITA_PASSO = 0.5;
    const VELOCITA_INIZIALE = 30;

    // Oltre questa cadenza l'occhio non guadagna niente e il disegno comincia a
    // costare: sopra, invece di scattare piu' spesso, si avanza di piu' sedute
    // per scatto. La velocita' richiesta resta quella, cambia solo il passo.
    const FOTOGRAMMI_AL_SECONDO = 60;

    // Quanti punti si disegnano al massimo. La linea di cinquemila sedute non
    // ha cinquemila pixel a disposizione: sopra questa soglia si assottiglia,
    // e la pagina lo dichiara invece di lasciar credere che sia tutto li'.
    const MAX_PUNTI_DISEGNATI = 1200;

    // Il disegno lavora in un sistema di coordinate suo, e lo `viewBox` lo
    // adatta alla larghezza che trova.
    const LARGHEZZA = 1000;
    const ALTEZZA = 320;
    const MARGINE = 12;

    let cursore = $state(0);
    let inMovimento = $state(false);
    let velocita = $state(VELOCITA_INIZIALE);

    const ultimo = $derived(Math.max(0, andamento.length - 1));
    const oggi = $derived(andamento[Math.min(cursore, ultimo)] ?? null);
    const alTraguardo = $derived(cursore >= ultimo);

    /** Quale corsa stiamo guardando: cambia quando si rilancia il simulatore. */
    const firmaCorsa = $derived(
        andamento.length ? `${andamento[0].data}·${andamento.length}` : ""
    );

    let firmaAdottata = $state(null);

    // Una corsa nuova riparte dal primo giorno, e ferma. Se restasse dov'era, il
    // cursore indicherebbe una data che nella corsa nuova non c'e'.
    // `firmaAdottata` si legge senza tracciarla: la scrive questo stesso
    // effetto, e tracciarla lo farebbe ripartire per concludere che non c'e'
    // niente da fare.
    $effect(() => {
        if (firmaCorsa !== untrack(() => firmaAdottata)) {
            firmaAdottata = firmaCorsa;
            cursore = 0;
            inMovimento = false;
        }
    });

    // Il motore. Il conto del passo sta QUI e non dentro allo scatto: dipende
    // solo dalla velocita', e rifarlo sessanta volte al secondo sarebbe lavoro
    // per un numero che non cambia.
    $effect(() => {
        if (!inMovimento || andamento.length === 0) return;

        const passo = Math.max(1, Math.round(velocita / FOTOGRAMMI_AL_SECONDO));
        const attesa = (1000 * passo) / velocita;

        // Le letture qui dentro avvengono dopo, fuori dal giro di tracciamento:
        // non sono dipendenze, e l'effetto non riparte a ogni scatto.
        const battito = setInterval(() => {
            if (cursore >= ultimo) {
                inMovimento = false;
                return;
            }
            cursore = Math.min(cursore + passo, ultimo);
        }, attesa);

        return () => clearInterval(battito);
    });

    function avvia() {
        if (alTraguardo) cursore = 0;
        inMovimento = true;
    }

    /** I giorni gia' scoperti: il film si ferma qui, e oltre non si guarda. */
    const scoperti = $derived(andamento.slice(0, cursore + 1));

    /** Ogni quante sedute si prende un punto da disegnare. */
    const assottigliamento = $derived(Math.ceil(scoperti.length / MAX_PUNTI_DISEGNATI));

    /**
     * La linea, l'area sotto, e dove sta il segnaposto di oggi.
     *
     * Minimo e massimo si prendono sui soli giorni scoperti: e' la scelta che
     * tiene il futuro fuori dal grafico.
     */
    const disegno = $derived.by(() => {
        if (scoperti.length < 2) return null;

        const valori = scoperti.map((p) => p.valore);
        const minimo = Math.min(...valori);
        const massimo = Math.max(...valori);
        const ampiezza = massimo - minimo || 1;

        const ascissa = (indice) => (indice / (scoperti.length - 1)) * LARGHEZZA;
        const ordinata = (valore) =>
            ALTEZZA - MARGINE - ((valore - minimo) / ampiezza) * (ALTEZZA - 2 * MARGINE);

        const punti = [];
        for (let i = 0; i < scoperti.length; i += assottigliamento) {
            punti.push(`${ascissa(i).toFixed(2)},${ordinata(scoperti[i].valore).toFixed(2)}`);
        }
        // L'ultimo giorno c'e' sempre, anche quando il passo l'avrebbe saltato:
        // e' quello di cui i numeri qui sopra stanno parlando.
        punti.push(`${LARGHEZZA},${ordinata(valori[valori.length - 1]).toFixed(2)}`);

        return {
            linea: punti.join(" "),
            area: `0,${ALTEZZA} ${punti.join(" ")} ${LARGHEZZA},${ALTEZZA}`,
            pareggio: capitale >= minimo && capitale <= massimo ? ordinata(capitale) : null,
            fine: { x: LARGHEZZA, y: ordinata(valori[valori.length - 1]) },
            minimo,
            massimo,
        };
    });

    /** In guadagno o in perdita rispetto a quanto si e' messo: decide il colore. */
    const inGuadagno = $derived((oggi?.rendimento ?? 0) >= 0);
    const tinta = $derived(inGuadagno ? "var(--bs-success)" : "var(--bs-danger)");
</script>

{#if andamento.length >= 2 && oggi}
    <div class="cinema mb-3">
        <!-- Il «presente» del film: cosa si sarebbe letto quella mattina. -->
        <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-2">
            <div>
                <div class="small text-secondary numerico">{oggi.data}</div>
                <div class="fs-4 numerico">{soldi(oggi.valore)}</div>
            </div>
            <div class="text-end small">
                <div class="fs-5 numerico" style="color: {tinta}">
                    {percento(oggi.rendimento)}
                    <span class="text-secondary fs-6">da {soldi(capitale)}</span>
                </div>
                <div class="numerico text-secondary">
                    giorno {percento(oggi.variazione)} · sotto il massimo
                    {percento(oggi.discesa)}
                    {#if oggi.giorni_dal_massimo > 0}
                        da {oggi.giorni_dal_massimo} sedute
                    {/if}
                </div>
            </div>
        </div>

        <div class="tela" style="--tinta: {tinta}">
            {#if disegno}
                <svg viewBox="0 0 {LARGHEZZA} {ALTEZZA}" preserveAspectRatio="none"
                     role="img" aria-label="Valore della posizione fino al {oggi.data}">
                    <polygon points={disegno.area} fill="var(--tinta)" opacity="0.15" />
                    {#if disegno.pareggio !== null}
                        <!-- Quanto si e' messo: sopra questa riga si e' in
                             guadagno, sotto si e' sotto. E' l'unica linea che
                             si conosce dal primo giorno. -->
                        <line x1="0" y1={disegno.pareggio} x2={LARGHEZZA} y2={disegno.pareggio}
                              stroke="currentColor" stroke-dasharray="6 6" opacity="0.4"
                              vector-effect="non-scaling-stroke" />
                    {/if}
                    <polyline points={disegno.linea} fill="none" stroke="var(--tinta)"
                              stroke-width="2" vector-effect="non-scaling-stroke" />
                    <circle cx={disegno.fine.x} cy={disegno.fine.y} r="4" fill="var(--tinta)"
                            vector-effect="non-scaling-stroke" />
                </svg>
                <div class="scala small text-secondary numerico">
                    <span>{soldi(disegno.massimo)}</span>
                    <span>{soldi(disegno.minimo)}</span>
                </div>
            {:else}
                <p class="small text-secondary p-3 mb-0">
                    Premi play: la linea si disegna man mano che i giorni passano.
                </p>
            {/if}
        </div>

        <div class="d-flex justify-content-between small text-secondary numerico mt-1">
            <span>{andamento[0].data}</span>
            <span>{andamento[ultimo].data} · {andamento.length} sedute</span>
        </div>

        <!-- Il cursore e' anche la barra di avanzamento: due controlli per la
             stessa cosa sarebbero due cose da tenere allineate. Trascinarlo
             serve a tornare su un tratto senza rivedere tutto il resto. -->
        <label class="form-label small mb-1 mt-2" for="cinema-cursore">
            Seduta <strong class="numerico">{cursore + 1}</strong> di {andamento.length}
        </label>
        <input id="cinema-cursore" type="range" class="form-range" min="0" max={ultimo}
               bind:value={cursore} oninput={() => (inMovimento = false)} />

        <div class="d-flex flex-wrap align-items-center gap-3">
            <div class="btn-group btn-group-sm" role="group">
                <button type="button" class="btn btn-outline-secondary" title="Da capo"
                        onclick={() => { cursore = 0; inMovimento = false; }}>
                    <i class="bi bi-skip-backward-fill"></i>
                </button>
                <button type="button" class="btn btn-primary"
                        title={inMovimento ? "Pausa" : "Vivi"}
                        onclick={() => (inMovimento ? (inMovimento = false) : avvia())}>
                    <i class="bi {inMovimento ? 'bi-pause-fill' : 'bi-play-fill'}"></i>
                </button>
                <button type="button" class="btn btn-outline-secondary" title="Salta alla fine"
                        onclick={() => { inMovimento = false; cursore = ultimo; }}>
                    <i class="bi bi-skip-forward-fill"></i>
                </button>
            </div>

            <div class="flex-grow-1" style="min-width: 14rem">
                <label class="form-label small mb-1" for="cinema-velocita">
                    Velocita' <span class="numerico">{velocita}</span> sedute al secondo
                </label>
                <input id="cinema-velocita" type="range" class="form-range"
                       min={VELOCITA_MIN} max={VELOCITA_MAX} step={VELOCITA_PASSO}
                       bind:value={velocita} />
            </div>
        </div>

        {#if assottigliamento > 1}
            <p class="small text-secondary mt-2 mb-0">
                <Testo testo="La linea e' assottigliata: un punto ogni {assottigliamento} sedute, perche' non ci sono abbastanza pixel per disegnarle tutte. I numeri qui sopra sono quelli esatti del giorno." />
            </p>
        {/if}
    </div>
{/if}

<style>
    .tela {
        position: relative;
        border: 1px solid var(--bs-border-color);
        border-radius: 0.375rem;
        overflow: hidden;
        min-height: 8rem;
    }

    .tela svg {
        display: block;
        width: 100%;
        height: 16rem;
    }

    /* I due estremi della scala verticale, appoggiati sopra al disegno: un asse
       vero ruberebbe larghezza alla linea, che e' la cosa da guardare. */
    .scala {
        position: absolute;
        top: 0.25rem;
        right: 0.5rem;
        bottom: 0.25rem;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        pointer-events: none;
    }
</style>
