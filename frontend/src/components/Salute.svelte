<!--
    Salute.svelte — figure di bilancio e rapporti di solidita'. Nessun punteggio.
    feat (Blocco 8, ripreso): la sezione "salute" della pagina titolo del vecchio.

    **Qui non c'e' un voto, ed e' una decisione presa gia' nel vecchio sistema
    dopo averne subito le conseguenze.** Quella sezione produceva un Health
    Score 0-100 con etichetta OTTIMA/BUONA/DEBOLE/CRITICA: un secondo verdetto
    sulla stessa azienda, parallelo a quello della qualita' fondamentale e non
    riconciliato con esso. Due numeri diversi, e chi leggeva doveva scegliere a
    quale credere.

    Restano i dati. Il giudizio lo da' l'analisi fondamentale, ed e' uno solo.
-->
<script>
    import Assente from "./Assente.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import Valore from "./Valore.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";
    import { onMount } from "svelte";

    let { simbolo } = $props();

    const salute = richiedi(() => api.salute(simbolo));

    onMount(() => salute.ricarica());
    $effect(() => {
        simbolo;
        salute.ricarica();
    });

    const NOMI_FIGURE = {
        patrimonio_netto: "Patrimonio netto",
        debito_totale: "Debito totale",
        cassa: "Cassa e titoli a breve",
        debito_netto: "Debito netto",
        attivo_totale: "Attivo totale",
        passivo_totale: "Passivo totale",
        ebit_ttm: "EBIT (12 mesi)",
        ebitda_ttm: "EBITDA (12 mesi)",
        oneri_finanziari_ttm: "Oneri finanziari (12 mesi)",
    };

    // Cosa vuol dire ogni rapporto, in una riga. Un numero senza la sua domanda
    // e' un numero che si guarda e non si legge.
    const NOMI_RAPPORTI = {
        copertura_interessi: {
            nome: "Copertura degli interessi",
            spiega: "quante volte il reddito operativo copre gli oneri finanziari",
        },
        debito_su_patrimonio: {
            nome: "Debito su patrimonio",
            spiega: "quanto del capitale e' preso a prestito",
        },
        copertura_attivi: {
            nome: "Copertura degli attivi",
            spiega: "quante volte l'attivo copre il passivo",
        },
        debito_netto_su_ebitda: {
            nome: "Debito netto su EBITDA",
            spiega: "quanti anni di margine operativo lordo per ripagare il debito netto",
        },
    };

    const NOMI_PONTE = {
        utile: "Utile", ammortamenti: "Ammortamenti",
        azioni_ai_dipendenti: "Azioni ai dipendenti", circolante: "Circolante",
        altro: "Altro", cassa_libera: "Cassa libera",
    };

    const MILIARDO = 1_000_000_000;
    const MILIONE = 1_000_000;

    /** Un importo in forma leggibile: i bilanci si leggono in miliardi. */
    function importo(valore) {
        if (valore === null || valore === undefined) return null;
        const assoluto = Math.abs(valore);
        if (assoluto >= MILIARDO) return `${(valore / MILIARDO).toFixed(2)} mld`;
        if (assoluto >= MILIONE) return `${(valore / MILIONE).toFixed(0)} mln`;
        return valore.toFixed(0);
    }

    const conta = (valore) => (valore === null || valore === undefined
        ? null : `${valore.toFixed(2)}×`);
</script>

<Riquadro richiesta={salute} testoCaricamento="leggo i bilanci…">
    {#snippet children(d)}
        <div class="row g-3">
            <div class="col-12 col-lg-6">
                <div class="fw-semibold small mb-2">Le grandezze di bilancio</div>
                <table class="table table-sm small mb-0">
                    <tbody>
                        {#each Object.entries(NOMI_FIGURE) as [chiave, nome] (chiave)}
                            <tr>
                                <td class="text-secondary">{nome}</td>
                                <td class="text-end numerico">
                                    <Valore valore={importo(d.figure[chiave])} />
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>

            <div class="col-12 col-lg-6">
                <div class="fw-semibold small mb-2">I rapporti di solidita'</div>
                {#each Object.entries(NOMI_RAPPORTI) as [chiave, meta] (chiave)}
                    {@const r = d.rapporti[chiave]}
                    <div class="mb-2 small">
                        <div class="d-flex justify-content-between">
                            <span>{meta.nome}</span>
                            <!-- Un rapporto che non si puo' fare porta il motivo:
                                 un denominatore a zero non da' un numero enorme,
                                 da' un rapporto che non esiste. -->
                            <strong class="numerico">
                                {#if r.valore === null}
                                    <span class="assente" title={r.reason}>n/d</span>
                                {:else}
                                    {conta(r.valore)}
                                {/if}
                            </strong>
                        </div>
                        <div class="text-secondary"><Testo testo={meta.spiega} /></div>
                        {#if r.valore === null && r.reason}
                            <div class="text-warning"><Testo testo={r.reason} /></div>
                        {/if}
                    </div>
                {/each}
            </div>
        </div>

        {#if d.storia_del_debito.length}
            <div class="mt-3">
                <div class="fw-semibold small mb-1">Come si e' mosso il debito</div>
                <p class="small text-secondary">
                    <Testo testo="Il rapporto da solo non basta: puo' scendere perche' il debito cala o perche' il patrimonio sale, e sono due storie diverse." />
                </p>
                <div class="table-responsive">
                    <table class="table table-sm small mb-0">
                        <thead>
                            <tr>
                                <th class="text-secondary">trimestre</th>
                                <th class="text-secondary text-end">debito</th>
                                <th class="text-secondary text-end">patrimonio</th>
                                <th class="text-secondary text-end">D/E</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each d.storia_del_debito as riga (riga.periodo)}
                                <tr>
                                    <td class="numerico">{riga.periodo}</td>
                                    <td class="text-end numerico">{importo(riga.debito)}</td>
                                    <td class="text-end numerico">{importo(riga.patrimonio)}</td>
                                    <td class="text-end numerico">
                                        <Valore valore={conta(riga.debito_su_patrimonio)} />
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            </div>
        {/if}

        {#if d.dall_utile_alla_cassa.length}
            <div class="mt-3">
                <div class="fw-semibold small mb-1">Dall'utile alla cassa</div>
                <p class="small text-secondary">
                    <Testo testo="L'utile e la cassa non sono la stessa cosa. «Altro» e' il residuo — investimenti, imposte, il resto: se e' grande, e' proprio quello da guardare." />
                </p>
                <div class="table-responsive">
                    <table class="table table-sm small mb-0">
                        <thead>
                            <tr>
                                <th class="text-secondary">trimestre</th>
                                {#each Object.values(NOMI_PONTE) as nome (nome)}
                                    <th class="text-secondary text-end">{nome}</th>
                                {/each}
                                <th class="text-secondary text-end">conversione</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each d.dall_utile_alla_cassa as riga (riga.periodo)}
                                <tr>
                                    <td class="numerico">{riga.periodo}</td>
                                    {#each Object.keys(NOMI_PONTE) as chiave (chiave)}
                                        <td class="text-end numerico">
                                            <Valore valore={importo(riga[chiave])} />
                                        </td>
                                    {/each}
                                    <td class="text-end numerico">
                                        <Valore valore={riga.conversione === null
                                            ? null : `${(riga.conversione * 100).toFixed(0)}%`} />
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            </div>
        {/if}

        {#if d.figure_mancanti.length}
            <Assente titolo="Grandezze che non ci sono"
                     motivo={`nei bilanci di Defeatbeta mancano: ${d.figure_mancanti.join(", ")}`}
                     azione="i rapporti che le usano risultano non calcolabili, non zero" />
        {/if}

        <p class="small text-secondary mt-3 mb-0"><Testo testo={d.nota} /></p>
    {/snippet}
</Riquadro>
