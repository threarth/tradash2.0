<!--
    Spinoff.svelte — chi si e' separato da chi, e quando l'abbiamo saputo.
    feat: l'unico elenco che non viene da Defeatbeta.

    Serve a una domanda che i nostri dati non sanno rispondere: **quali titoli
    sono nati da uno spin-off recente**. Defeatbeta non lo sa — l'indice dei
    filing e' recente-only, verificato su SNDK: 182 depositi, il piu' vecchio di
    otto mesi fa, nessun modulo 10-12B — e senza sapere chi si e' separato non
    c'e' niente da cercare.

    **Si scarica solo premendo.** Nessun aggiornamento all'avvio, a scadenza o
    «se il file e' vecchio»: la pagina si prende quando lo chiedi tu, e l'elenco
    resta com'e' finche' non lo richiedi. Per questo in cima c'e' scritto quando
    e' stato preso: un elenco di tre mesi fa non e' sbagliato, e' incompleto, e
    chi lo guarda deve poterlo sapere senza indovinare.

    I mesi dallo spin li conta il browser sulla data della separazione: e' una
    sottrazione fra due date, e farla fare al backend vorrebbe dire una risposta
    che invecchia da sola.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "./Assente.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";

    const GIORNI_PER_MESE = 30.44;

    // Oltre questa eta' uno spin-off non e' piu' «recente»: la separazione l'ha
    // gia' digerita il mercato. Si mostra lo stesso, ma smorzato.
    const MESI_RECENTE = 18;

    let dati = $state(null);
    let errore = $state(null);
    let inCorso = $state(false);

    async function carica() {
        try {
            dati = await api.spinoff();
            errore = null;
        } catch (problema) {
            errore = problema.message;
        }
    }

    onMount(carica);

    async function aggiorna() {
        inCorso = true;
        errore = null;
        try {
            await api.spinoffAggiorna();
            await carica();
        } catch (problema) {
            errore = problema.message;
        } finally {
            inCorso = false;
        }
    }

    /** Quanti mesi sono passati dalla separazione. */
    const mesi = (quando) =>
        (Date.now() - new Date(quando).getTime()) / (GIORNI_PER_MESE * 86400000);

    const quando = (iso) => (iso ? new Date(iso).toLocaleString("it") : "mai");
</script>

<div class="card mb-3">
    <div class="card-body">
        <div class="d-flex flex-wrap justify-content-between align-items-start gap-2 mb-2">
            <div>
                <h2 class="h6 mb-1">Spin-off recenti</h2>
                <p class="small text-secondary mb-0">
                    <Testo testo="L'unico elenco che non viene da Defeatbeta, che non sa dire chi e' nato da una separazione. Si scarica da stockanalysis.com solo quando premi." />
                </p>
            </div>
            <button class="btn btn-sm btn-primary" disabled={inCorso} onclick={aggiorna}>
                {inCorso ? "scarico…" : "Aggiorna l'elenco"}
            </button>
        </div>

        <p class="small text-secondary numerico">
            Preso il {quando(dati?.preso_il)}
            {#if dati?.righe?.length}· {dati.righe.length} separazioni{/if}
        </p>

        {#if errore}
            <div class="alert alert-warning py-2 small mb-0">
                {errore}
                <!-- L'elenco di prima non e' stato toccato: va detto, altrimenti
                     un errore si legge come «ho perso tutto». -->
                {#if dati?.righe?.length}
                    L'elenco qui sotto e' ancora quello di prima.
                {/if}
            </div>
        {/if}

        {#if dati && !dati.disponibile && !errore}
            <Assente titolo="Nessun elenco" motivo={dati.motivo} azione={dati.azione} />
        {/if}

        {#if dati?.righe?.length}
            <div class="table-responsive mt-2" style="max-height: 26rem">
                <table class="table table-sm small mb-0">
                    <thead class="sticky-top">
                        <tr>
                            <th>Nata</th>
                            <th>Da</th>
                            <th class="text-end">Separata il</th>
                            <th class="text-end">Mesi fa</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each dati.righe as riga (riga.symbol + riga.data)}
                            {@const eta = mesi(riga.data)}
                            <tr class:text-secondary={eta > MESI_RECENTE}>
                                <td>
                                    <a class="numerico" href="/titolo/{riga.symbol}">
                                        {riga.symbol}
                                    </a>
                                    {#if riga.nome}
                                        <div class="text-secondary">{riga.nome}</div>
                                    {/if}
                                </td>
                                <td>
                                    {#if riga.parent}
                                        <a class="numerico" href="/titolo/{riga.parent}">
                                            {riga.parent}
                                        </a>
                                    {:else}—{/if}
                                </td>
                                <td class="text-end numerico">{riga.data}</td>
                                <td class="text-end numerico">{eta.toFixed(0)}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    </div>
</div>
