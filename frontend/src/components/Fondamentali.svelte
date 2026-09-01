<!--
    Fondamentali.svelte — i bilanci, e la data a cui li stai guardando.
    feat (Blocco 7): il taglio `as_of` con dichiarata la base su cui poggia.

    La casella della data non e' un filtro di comodo: scegliendo un giorno del
    passato si vedono solo i periodi che a quel giorno erano gia' DEPOSITATI.
    Troncare sulla fine del trimestre invece che sul deposito farebbe vedere,
    al 15 luglio, un bilancio chiuso il 30 giugno e depositato ad agosto —
    quaranta giorni di futuro che non danno nessun errore, solo un backtest che
    sembra bravissimo.

    E la base del taglio si mostra sempre: reale o stimata non sono la stessa
    cosa, e due risultati costruiti sulle due basi non sono confrontabili.

    ## Dalla tabella al grafico

    Ottantadue voci per venti trimestri sono un archivio, non una lettura: la
    domanda «questa voce sta salendo?» si risponde a occhio solo se le cifre
    sono poche e vicine. Si scelgono le righe e si vede la forma.

    Due modi di scegliere, perche' rispondono a due gesti diversi: il **click**
    su una riga la aggiunge o la toglie — e' il gesto di chi sta gia' leggendo
    la tabella; il **tasto destro** apre un menu, che e' il gesto di chi ha in
    mente una voce e vuole vederla subito da sola.
-->
<script>
    import Assente from "./Assente.svelte";
    import GraficoVoci from "./GraficoVoci.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    let asOf = $state("");
    let periodicita = $state("quarterly");
    let prospettoScelto = $state("income_statement");

    const NOMI = {
        income_statement: "Conto economico",
        balance_sheet: "Stato patrimoniale",
        cash_flow: "Rendiconto finanziario"
    };

    // Come si legge la base del taglio. Il colore non e' decorazione: dice se
    // ti puoi fidare della ricostruzione o se poggia su una nostra assunzione.
    const BASE = {
        filing_index: { classe: "text-bg-success", testo: "date di deposito reali" },
        mixed: { classe: "text-bg-warning", testo: "in parte stimate" },
        estimated: { classe: "text-bg-danger", testo: "tutte stimate" }
    };

    const dati = richiedi(() => api.fondamentali(simbolo, asOf, periodicita));

    $effect(() => {
        simbolo;
        asOf;
        periodicita;
        dati.ricarica();
    });

    // Le voci da graficare, e il menu del tasto destro. Le scelte sono per
    // prospetto: passando dal conto economico allo stato patrimoniale le voci
    // scelte non hanno piu' senso, e tenerle vorrebbe dire mostrare un grafico
    // di righe che non sono nella tabella che si sta guardando.
    let scelte = $state([]);
    let menu = $state(null);

    $effect(() => {
        prospettoScelto;
        scelte = [];
        menu = null;
    });

    function segna(voce) {
        scelte = scelte.includes(voce)
            ? scelte.filter((v) => v !== voce)
            : [...scelte, voce];
    }

    function apriMenu(evento, voce) {
        evento.preventDefault();
        menu = { voce, x: evento.clientX, y: evento.clientY };
    }

    function soloQuesta(voce) {
        scelte = [voce];
        menu = null;
    }

    function aggiungi(voce) {
        if (!scelte.includes(voce)) scelte = [...scelte, voce];
        menu = null;
    }

    /** I numeri grandi in forma leggibile, senza perdere il segno. */
    function breve(valore) {
        if (valore === null || valore === undefined) return "";
        const assoluto = Math.abs(valore);
        if (assoluto >= 1e9) return `${(valore / 1e9).toLocaleString("it", { maximumFractionDigits: 2 })} mld`;
        if (assoluto >= 1e6) return `${(valore / 1e6).toLocaleString("it", { maximumFractionDigits: 1 })} mln`;
        return valore.toLocaleString("it", { maximumFractionDigits: 2 });
    }
</script>

<div class="d-flex flex-wrap gap-2 align-items-end mb-3">
    <div>
        <label class="form-label small mb-0" for="as-of">Ricostruisci al giorno</label>
        <input id="as-of" type="date" class="form-control form-control-sm" bind:value={asOf} />
    </div>
    <div>
        <label class="form-label small mb-0" for="periodicita">Periodicita'</label>
        <select id="periodicita" class="form-select form-select-sm" bind:value={periodicita}>
            <option value="quarterly">trimestrale</option>
            <option value="annual">annuale</option>
        </select>
    </div>
    {#if asOf}
        <button class="btn btn-sm btn-outline-secondary" onclick={() => (asOf = "")}>
            torna a oggi
        </button>
    {/if}
</div>

<Riquadro richiesta={dati} testoCaricamento="carico i bilanci…">
    {#snippet children(d)}
        {@const base = BASE[d.base_del_taglio.source] ?? null}

        <div class="d-flex flex-wrap gap-3 align-items-center mb-3 small">
            <span>
                <strong>{d.periodi_visibili}</strong> periodi
                {#if d.as_of}visibili al {d.as_of} (su {d.periodi_totali}){/if}
            </span>
            {#if base}
                <span class="badge {base.classe}">{base.testo}</span>
                <span class="text-secondary">
                    {d.base_del_taglio.real_periods} reali ·
                    {d.base_del_taglio.estimated_periods} stimati
                </span>
            {/if}
        </div>

        {#if d.base_del_taglio.source && d.base_del_taglio.source !== "filing_index"}
            <div class="alert alert-warning py-2 small">
                <Testo testo={d.base_del_taglio.note} /> — un risultato costruito su date
                stimate non e' confrontabile con uno costruito su date reali.
            </div>
        {/if}

        <ul class="nav nav-tabs mb-3">
            {#each Object.entries(NOMI) as [chiave, nome] (chiave)}
                <li class="nav-item">
                    <button class="nav-link" class:active={prospettoScelto === chiave}
                            onclick={() => (prospettoScelto = chiave)}>{nome}</button>
                </li>
            {/each}
        </ul>

        {@const prospetto = d.prospetti[prospettoScelto]}
        {#if prospetto.periodi.length === 0}
            <Assente titolo="Nessun periodo da mostrare"
                     motivo={d.as_of
                         ? `al ${d.as_of} non era stato depositato nessun ${NOMI[prospettoScelto].toLowerCase()}`
                         : "Defeatbeta non ha questo prospetto per il titolo"}
                     azione={d.as_of ? "prova una data piu' recente" : null} />
        {:else}
            {#if scelte.length}
                <div class="mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="small fw-semibold">
                            {scelte.length} voci sul grafico
                        </span>
                        <button class="btn btn-sm btn-link p-0"
                                onclick={() => (scelte = [])}>togli tutte</button>
                    </div>
                    <GraficoVoci voci={prospetto.voci} periodi={prospetto.periodi}
                                 {scelte} />
                </div>
            {:else}
                <p class="small text-secondary">
                    <Testo testo="Premi una riga per metterla sul grafico, o tasto destro per il menu. Piu' righe si confrontano fra loro." />
                </p>
            {/if}

            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>Voce</th>
                            {#each prospetto.periodi.slice(0, 8) as periodo (periodo)}
                                <th class="text-end">{periodo}</th>
                            {/each}
                        </tr>
                    </thead>
                    <tbody>
                        {#each Object.entries(prospetto.voci) as [voce, valori] (voce)}
                            <tr class="riga" class:table-active={scelte.includes(voce)}
                                onclick={() => segna(voce)}
                                oncontextmenu={(e) => apriMenu(e, voce)}>
                                <td>
                                    <span class="text-secondary me-1">
                                        {scelte.includes(voce) ? "◉" : "○"}
                                    </span>
                                    <Testo testo={voce.replaceAll("_", " ")} />
                                </td>
                                {#each prospetto.periodi.slice(0, 8) as periodo (periodo)}
                                    <td class="numerico">{breve(valori[periodo])}</td>
                                {/each}
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    {/snippet}
</Riquadro>

<!-- Il menu del tasto destro. Si chiude a qualunque click o tasto: un menu che
     resta aperto dopo che hai guardato altrove e' un menu che devi chiudere. -->
{#if menu}
    <div class="menu-voce shadow" style={`left: ${menu.x}px; top: ${menu.y}px`}>
        <div class="small text-secondary px-2 pt-1">
            <Testo testo={menu.voce.replaceAll("_", " ")} />
        </div>
        <button class="dropdown-item small" onclick={() => soloQuesta(menu.voce)}>
            Grafica solo questa
        </button>
        <button class="dropdown-item small" onclick={() => aggiungi(menu.voce)}>
            Aggiungi al grafico
        </button>
    </div>
{/if}

<svelte:window onclick={() => (menu = null)} onkeydown={() => (menu = null)} />

<style>
    .riga {
        cursor: pointer;
    }

    .menu-voce {
        position: fixed;
        z-index: 1080;
        min-width: 12rem;
        background: var(--bs-tertiary-bg);
        border: 1px solid var(--bs-border-color);
        border-radius: 0.25rem;
        padding-bottom: 0.25rem;
    }
</style>
