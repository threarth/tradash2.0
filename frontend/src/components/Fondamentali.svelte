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
-->
<script>
    import Assente from "./Assente.svelte";
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
                            <tr>
                                <td><Testo testo={voce.replaceAll("_", " ")} /></td>
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
