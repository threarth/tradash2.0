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
    PEZZI non stanno sullo stesso asse.

    ## Base 100 non e' una scala logaritmica

    Sono due cose diverse e vale la pena tenerle distinte:

    - **Base 100** cambia i NUMERI: ogni serie viene divisa per il proprio primo
      valore, cosi' partono tutte dallo stesso punto e si confronta quanto sono
      cresciute *da li'*. Dipende da dove comincia il periodo: cambiando la data
      d'inizio, cambia il disegno.
    - **La scala logaritmica** lascia i numeri come sono e cambia l'ASSE, in modo
      che due raddoppi occupino la stessa altezza. Non dipende da dove si
      comincia, ma non sa disegnare valori negativi o nulli — e nei bilanci ce ne
      sono parecchi: variazioni di circolante, poste straordinarie, utili in
      perdita. Per questo qui c'e' la prima e non la seconda.

    ## Il segno, che e' il punto delicato

    Dividere per un primo valore **negativo ribalta la serie**: una voce che
    peggiora sembrerebbe salire. Misurato su NVDA, `change_in_working_capital`
    parte da -1,65 miliardi. Quindi si porta a base 100 solo cio' che parte
    POSITIVO; il resto resta coi valori veri, e la pagina dice quali e perche'.
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

    // Cosa dice il suggerimento del pulsante. Sta in una costante perche' e' la
    // risposta a una domanda che si fa chiunque la prima volta.
    const SPIEGAZIONE =
        "Base 100: ogni voce viene divisa per il proprio primo valore, cosi' "
        + "partono tutte dallo stesso punto e si vede quanto sono cresciute da "
        + "li'. NON e' una scala logaritmica: quella lascia i numeri come sono e "
        + "cambia l'asse, ma non disegna i valori negativi.";

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

        // Base 100 sul primo periodo disponibile, ma SOLO se parte positivo.
        // Dividere per zero non da' un rapporto; dividere per un negativo ne da'
        // uno ribaltato, che e' peggio — la serie sembrerebbe salire mentre
        // peggiora, e nessuno se ne accorgerebbe guardando il disegno.
        const primo = punti[0].valore;
        if (!(primo > 0)) return punti.map((p) => ({ time: p.time, value: p.valore }));
        return punti.map((p) => ({ time: p.time, value: (p.valore / primo) * BASE_COMUNE }));
    }

    /** Le voci che non si possono portare a base 100, e perche'. */
    const nonConfrontabili = $derived(
        !comune ? [] : scelte.map((nome) => {
            const valori = voci[nome] ?? {};
            const primo = ordinati.map((p) => valori[p]).find((v) => v !== null && v !== undefined);
            if (primo > 0) return null;
            return {
                nome,
                motivo: primo < 0 ? "parte da un valore negativo" : "parte da zero",
            };
        }).filter(Boolean)
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
            onclick={() => (comune = !comune)} title={SPIEGAZIONE}>
        {comune ? "Confronta la forma (base 100)" : "Valori veri"}
    </button>
</div>

<p class="small text-secondary mb-1">
    {#if comune}
        <Testo testo="Ogni voce e' divisa per il proprio primo valore e parte da 100: si confronta quanto sono cresciute DA LI'. Non e' una scala logaritmica — quella lascerebbe i numeri come sono e cambierebbe l'asse, ma non saprebbe disegnare i valori negativi, che nei bilanci abbondano." />
    {:else}
        <Testo testo="I numeri come sono. Con grandezze di scala diversa la serie piu' piccola diventa una riga piatta sul fondo: non e' ferma, e' schiacciata. Per confrontarle premi il pulsante." />
    {/if}
</p>

{#if nonConfrontabili.length}
    <p class="small text-warning mb-1">
        Mostrate coi valori veri, perche' dividere per il primo valore le
        ribalterebbe o non si puo':
        {#each nonConfrontabili as voce, i (voce.nome)}
            {i > 0 ? "; " : ""}<Testo testo={`${etichetta(voce.nome)} ${voce.motivo}`} />
        {/each}.
    </p>
{/if}

<div bind:this={contenitore} class="grafico"></div>
