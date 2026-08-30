<!--
    Segnali.svelte — i cinque segnali di rischio fondamentale.
    feat (Blocco 8): deterministici, e ognuno porta i numeri su cui poggia.

    Nessun modello linguistico qui dentro: sono calcoli sui bilanci. La
    distinzione che l'interfaccia deve rendere visibile e' fra "spento" e
    "ignoto": il primo dice che l'azienda sta bene su quel fronte, il secondo
    che il dato non c'e'. Confonderli farebbe leggere una copertura mancante
    come un via libera.
-->
<script>
    import Assente from "./Assente.svelte";
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo, asOf = "" } = $props();

    const ASPETTO = {
        acceso: { classe: "text-bg-danger", icona: "bi-exclamation-octagon", testo: "acceso" },
        attenzione: { classe: "text-bg-warning", icona: "bi-exclamation-triangle",
                      testo: "attenzione" },
        spento: { classe: "text-bg-success", icona: "bi-check2", testo: "spento" },
        ignoto: { classe: "text-bg-secondary", icona: "bi-question", testo: "dato assente" }
    };

    const dati = richiedi(() => api.segnali(simbolo, asOf));

    $effect(() => {
        simbolo;
        asOf;
        dati.ricarica();
    });
</script>

<Riquadro richiesta={dati} testoCaricamento="calcolo i segnali…">
    {#snippet children(d)}
        <div class="d-flex flex-wrap gap-3 align-items-center mb-3 small">
            <span>
                <strong>{d.copertura.calcolati}</strong> segnali su {d.copertura.totali}
                calcolabili
            </span>
            {#if d.copertura.ignoti.length}
                <span class="text-secondary">
                    dato assente per {d.copertura.ignoti.join(", ")}
                </span>
            {/if}
            {#if d.accesi.length}
                <span class="badge text-bg-danger">{d.accesi.length} accesi</span>
            {/if}
        </div>

        {#if d.copertura.calcolati === 0}
            <Assente titolo="Nessun segnale calcolabile"
                     motivo="i bilanci non bastano a calcolarne nemmeno uno"
                     azione="verifica che il titolo abbia una storia di bilanci" />
        {:else}
            <div class="list-group">
                {#each Object.entries(d.segnali) as [chiave, segnale] (chiave)}
                    {@const aspetto = ASPETTO[segnale.stato]}
                    <div class="list-group-item">
                        <div class="d-flex gap-2 align-items-start">
                            <span class="badge {aspetto.classe}" title={aspetto.testo}>
                                <i class="bi {aspetto.icona}"></i> {chiave}
                            </span>
                            <div class="flex-grow-1">
                                <div class="small fw-semibold">
                                    <Testo testo={segnale.nome} />
                                </div>
                                <div class="small text-secondary">
                                    <Testo testo={segnale.perche} />
                                </div>
                                {#if Object.keys(segnale.misure).length}
                                    <div class="small text-secondary mt-1">
                                        {#each Object.entries(segnale.misure) as [nome, valore] (nome)}
                                            <span class="me-3">
                                                {nome.replaceAll("_", " ")}:
                                                <span class="numerico">{
                                                    typeof valore === "number"
                                                        ? valore.toLocaleString("it",
                                                            { maximumFractionDigits: 2 })
                                                        : valore
                                                }</span>
                                            </span>
                                        {/each}
                                    </div>
                                {/if}
                            </div>
                        </div>
                    </div>
                {/each}
            </div>
        {/if}
    {/snippet}
</Riquadro>
