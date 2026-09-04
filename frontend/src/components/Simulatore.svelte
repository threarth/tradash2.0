<!--
    Simulatore.svelte — cosa si sarebbe vissuto tenendo questo titolo.
    feat (Blocco 9, ripreso): il simulatore psicologico del vecchio tradash.

    Non e' un backtest di strategia: non c'e' nessuna strategia. C'e' una
    posizione sola, e la domanda non e' «quanto avrei guadagnato» ma **«cosa
    avrei passato»**. Sono due domande diverse, e la seconda si dimentica
    sempre: un titolo che ha fatto +622% si racconta come una buona idea, ma se
    nel mezzo e' sceso del 63% e ci ha messo 343 sedute a tornare sopra il
    prezzo pagato, quella buona idea l'avrebbero tenuta in pochi.

    Sopra alla tabella c'e' il film: la stessa corsa, ma un giorno alla volta.
    La tabella mostra tutto insieme, ed e' esattamente cio' che chi teneva il
    titolo non vedeva — una discesa del 60% a consuntivo e' una macchia rossa
    larga tre colonne, vissuta e' quattordici mesi in cui ogni mattina il numero
    e' ancora sotto.

    La tabella ha **i mesi in colonna e i giorni in riga**. Il giorno della
    settimana cambia da un mese all'altro — il 5 e' lunedi' a marzo e giovedi'
    ad aprile — quindi ogni cella se lo porta dietro: senza, si legge una
    griglia di numeri credendo che le righe siano settimane.

    Le celle vuote non sono zeri: sono giorni di borsa chiusa, o giorni che quel
    mese non ha. Un calendario che disegna lo zero dove non si e' contrattato fa
    sembrare piatti i fine settimana.

    Niente parte all'apertura della pagina: si preme, come per tutto il resto.
-->
<script>
    import Assente from "./Assente.svelte";
    import Cinema from "./Cinema.svelte";
    import Errore from "./Errore.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { percento, soldi } from "../lib/numeri.js";

    let { simbolo } = $props();

    const MESI = ["gen", "feb", "mar", "apr", "mag", "giu",
                  "lug", "ago", "set", "ott", "nov", "dic"];

    // Oltre questa variazione giornaliera il colore non si scurisce piu': senza
    // un tetto, un solo giorno da -17% spegnerebbe tutti gli altri.
    const VARIAZIONE_PIENA = 0.05;

    let capitale = $state(10000);
    let base = $state("giorno");
    let inCorso = $state(false);
    let esito = $state(null);
    let errore = $state(null);

    // Il cursore sceglie il MESE da cui si parte. I mesi disponibili si sanno
    // solo dopo la prima risposta, che dice qual e' la prima seduta del titolo.
    let mesiIndietro = $state(48);
    const oggi = new Date();

    /** Il primo giorno del mese scelto col cursore. */
    const daQuando = $derived(
        new Date(Date.UTC(oggi.getUTCFullYear(), oggi.getUTCMonth() - mesiIndietro, 1))
            .toISOString().slice(0, 10)
    );

    // Quanti mesi indietro si puo' andare: fino alla prima seduta che esiste.
    const mesiPossibili = $derived.by(() => {
        const prima = esito?.prima_seduta_disponibile;
        if (!prima) return 240;
        const inizio = new Date(prima);
        return Math.max(1, (oggi.getUTCFullYear() - inizio.getUTCFullYear()) * 12
                           + (oggi.getUTCMonth() - inizio.getUTCMonth()));
    });

    const nomeMese = (colonna) => `${MESI[colonna.mese - 1]} ${String(colonna.anno).slice(2)}`;

    const cella = (colonna, giorno) => esito?.griglia?.celle?.[colonna.chiave]?.[giorno] ?? null;

    /** Il colore di una cella: verde se sale, rosa se scende, tanto piu' pieno
        quanto piu' si e' mossa. */
    function tinta(variazione) {
        if (variazione === null || variazione === undefined) return "";
        const forza = Math.min(Math.abs(variazione) / VARIAZIONE_PIENA, 1);
        const colore = variazione >= 0 ? "var(--monitor-verde)" : "var(--monitor-rosa)";
        return `background: color-mix(in srgb, ${colore} ${(forza * 70).toFixed(0)}%, transparent);`;
    }

    async function simula() {
        inCorso = true;
        errore = null;
        try {
            esito = await api.simulatore(simbolo, daQuando, capitale, base);
        } catch (problema) {
            errore = problema;
            esito = null;
        } finally {
            inCorso = false;
        }
    }
</script>

<div class="d-flex flex-wrap align-items-end gap-3 mb-3">
    <div>
        <label class="form-label small mb-1" for="sim-capitale">Capitale investito</label>
        <input id="sim-capitale" type="number" min="1" step="100"
               class="form-control form-control-sm" style="width: 9rem" bind:value={capitale} />
    </div>

    <div class="flex-grow-1" style="min-width: 16rem">
        <label class="form-label small mb-1" for="sim-quando">
            Comprato il <strong class="numerico">{daQuando}</strong>
            <span class="text-secondary">— {mesiIndietro} mesi fa</span>
        </label>
        <input id="sim-quando" type="range" class="form-range"
               min="1" max={mesiPossibili} bind:value={mesiIndietro} />
    </div>

    <div class="btn-group btn-group-sm" role="group">
        <button type="button" class="btn btn-outline-secondary" class:active={base === "giorno"}
                onclick={() => (base = "giorno")}>Giorno su giorno</button>
        <button type="button" class="btn btn-outline-secondary" class:active={base === "periodo"}
                onclick={() => (base = "periodo")}>Dal giorno d'acquisto</button>
    </div>

    <button class="btn btn-sm btn-primary" disabled={inCorso} onclick={simula}>
        {inCorso ? "calcolo…" : "Rivivi"}
    </button>
</div>

<p class="small text-secondary">
    <Testo testo="Giorno su giorno e' quello che si sarebbe sentito; dal giorno d'acquisto e' quello che si sarebbe ricordato. Il cursore sposta il giorno d'acquisto, e con lui tutte le variazioni." />
</p>

{#if errore}
    <Errore {errore} riprova={simula} />
{/if}

{#if esito}
    {@const e = esito.esperienza}

    {#if !e.available}
        <Assente titolo="Troppo poco tempo" motivo={e.reason} azione={e.action} />
    {:else}
        <div class="row g-3 mb-3 small">
            <div class="col-6 col-lg-3">
                <div class="text-secondary">Valore oggi</div>
                <div class="numerico fs-5">{soldi(e.valore_oggi)}</div>
                <div class:text-success={e.rendimento > 0} class:text-danger={e.rendimento < 0}>
                    {percento(e.rendimento)} da {soldi(e.capitale)}
                </div>
            </div>
            <div class="col-6 col-lg-3">
                <!-- Non e' la perdita finale: e' la discesa massima dal punto
                     piu' alto raggiunto, cioe' il numero che si guardava
                     mentre stava succedendo. -->
                <div class="text-secondary">Peggio attraversato</div>
                <div class="numerico fs-5 text-danger">{percento(e.discesa_peggiore)}</div>
                <div class="text-secondary">dal massimo raggiunto fino ad allora</div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="text-secondary">Tempo in perdita</div>
                <div class="numerico fs-5">{e.giorni_sotto_il_prezzo_pagato}</div>
                <div class="text-secondary">
                    sedute sotto il prezzo pagato, il
                    {percento(e.quota_del_tempo_in_perdita, 0)} del tempo
                </div>
            </div>
            <div class="col-6 col-lg-3">
                <div class="text-secondary">Giorni estremi</div>
                <div class="numerico">
                    <span class="text-success">{percento(e.giorno_migliore?.variazione)}</span>
                    il {e.giorno_migliore?.data}
                </div>
                <div class="numerico">
                    <span class="text-danger">{percento(e.giorno_peggiore?.variazione)}</span>
                    il {e.giorno_peggiore?.data}
                </div>
            </div>
        </div>

        <Cinema andamento={esito.andamento ?? []} capitale={e.capitale} />

        <!-- Larga quanto i mesi che ha: scorre dentro il suo contenitore invece
             di far scorrere la pagina. -->
        <div class="table-responsive" style="max-height: 32rem">
            <table class="table table-sm table-bordered small mb-0 calendario">
                <thead class="sticky-top">
                    <tr>
                        <th class="text-secondary">g</th>
                        {#each esito.griglia.mesi as colonna (colonna.chiave)}
                            <th class="text-secondary text-center">{nomeMese(colonna)}</th>
                        {/each}
                    </tr>
                </thead>
                <tbody>
                    {#each esito.griglia.giorni as giorno (giorno)}
                        <tr>
                            <th class="text-secondary numerico">{giorno}</th>
                            {#each esito.griglia.mesi as colonna (colonna.chiave)}
                                {@const c = cella(colonna, giorno)}
                                <td class="text-center numerico" style={tinta(c?.variazione)}
                                    title={c ? `${c.data} · chiusura ${c.chiusura}` : ""}>
                                    {#if c}
                                        <span class="text-secondary">{c.giorno_settimana}</span>
                                        {percento(c.variazione)}
                                    {/if}
                                </td>
                            {/each}
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>

        <p class="small text-secondary mt-2 mb-0">
            <Testo testo={e.reason} />. Le celle vuote sono giorni di borsa chiusa,
            o giorni che quel mese non ha: non sono variazioni pari a zero.
        </p>
    {/if}
{/if}

<style>
    /* Le colonne restano leggibili anche con cinquanta mesi: una larghezza
       minima, e il contenitore scorre. */
    .calendario td, .calendario th {
        min-width: 4.6rem;
        white-space: nowrap;
        padding: 0.15rem 0.3rem;
    }
</style>
