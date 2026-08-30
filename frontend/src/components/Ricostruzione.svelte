<!--
    Ricostruzione.svelte — cosa si sapeva a una data passata, e cosa e' successo dopo.
    feat (Blocco 7, chiuso col Blocco 8): il confronto point-in-time.

    Una lettura scritta oggi si potra' giudicare fra un anno. Ricostruita a una
    data passata si giudica subito, perche' il dopo e' gia' successo.

    Niente parte aprendo la pagina: si sceglie una data e si chiede. Il calcolo
    legge tutta la storia dei prezzi e la mappa dei depositi, e farlo a ogni
    apertura della scheda sarebbe lavoro pesante non chiesto da nessuno.
-->
<script>
    import Assente from "./Assente.svelte";
    import Errore from "./Errore.svelte";
    import Testo from "./Testo.svelte";
    import Valore from "./Valore.svelte";
    import { api } from "../lib/api.js";

    let { simbolo } = $props();

    // Un anno fa: la data che rende il confronto gia' leggibile su tutti gli
    // orizzonti. Resta modificabile, ovviamente.
    const unAnnoFa = new Date(Date.now() - 365 * 24 * 3600 * 1000)
        .toISOString()
        .slice(0, 10);

    let quando = $state(unAnnoFa);
    let inCorso = $state(false);
    let esito = $state(null);
    let errore = $state(null);

    const ETICHETTE = {
        "30g": "un mese dopo",
        "90g": "tre mesi dopo",
        "180g": "sei mesi dopo",
        "365g": "un anno dopo",
    };

    const percento = (frazione) =>
        frazione === null || frazione === undefined
            ? null
            : `${frazione >= 0 ? "+" : ""}${(frazione * 100).toFixed(1)}%`;

    // Un orizzonte senza numero ha due motivi opposti, e vanno distinti: il
    // giorno non e' ancora arrivato, oppure e' arrivato e la seduta non c'era.
    const motivoDelVuoto = (chiave) =>
        (esito?.orizzonti_maturati ?? []).includes(chiave)
            ? "nessuna seduta abbastanza vicina a quella data"
            : "non e' ancora passato abbastanza tempo";

    async function ricostruisci() {
        inCorso = true;
        errore = null;
        esito = null;
        try {
            esito = await api.ricostruzione(simbolo, quando);
        } catch (problema) {
            errore = problema;
        } finally {
            inCorso = false;
        }
    }
</script>

<div class="d-flex align-items-end gap-2 flex-wrap mb-3">
    <div>
        <label class="form-label small mb-1" for="ricostruzione-data">
            Ricostruisci al giorno
        </label>
        <input id="ricostruzione-data" type="date" class="form-control form-control-sm"
               bind:value={quando} max={unAnnoFa} />
    </div>
    <button class="btn btn-sm btn-primary" disabled={inCorso || !quando}
            onclick={ricostruisci}>
        {inCorso ? "ricostruisco…" : "Ricostruisci"}
    </button>
</div>

{#if errore}
    <Errore {errore} riprova={ricostruisci} />
{/if}

{#if esito}
    {@const tecnica = esito.allora.tecnica}
    {@const fondamentale = esito.allora.fondamentale}

    <p class="small text-secondary mb-3">
        <Testo testo={esito.reason} />. Il prezzo di chiusura del
        {esito.ultima_seduta_utile} era
        <strong class="numerico">{esito.prezzo_alla_data}</strong>.
    </p>

    <div class="row g-3">
        <div class="col-12 col-lg-6">
            <h3 class="h6">Cosa si sapeva</h3>

            {#if tecnica.available}
                <div class="small">
                    <div>
                        Un mese prima:
                        <Valore valore={percento(tecnica.variazione_1m)} />
                    </div>
                    <div>
                        Tre mesi prima:
                        <Valore valore={percento(tecnica.variazione_3m)} />
                    </div>
                    <div>
                        Un anno prima:
                        <Valore valore={percento(tecnica.variazione_1a)} />
                    </div>
                    <div class="text-secondary"><Testo testo={tecnica.reason} /></div>
                </div>
            {:else}
                <Assente titolo="Lettura tecnica" motivo={tecnica.reason}
                         azione={tecnica.action} />
            {/if}

            {#if fondamentale.available}
                <div class="small mt-2">
                    <div>
                        Bilanci gia' depositati a quella data:
                        <strong class="numerico">{fondamentale.periodi_visibili}</strong>
                        su {fondamentale.periodi_totali}.
                    </div>

                    <!-- Il taglio su date di deposito vere e quello su un ritardo
                         stimato non sono confrontabili, e chi legge deve saperlo
                         senza andare a indovinare. -->
                    {#if fondamentale.base_del_taglio}
                        <div class="text-secondary">
                            <Testo testo={fondamentale.base_del_taglio.note} />
                            {#if fondamentale.base_del_taglio.estimated_periods > 0}
                                <span class="text-warning">
                                    — {fondamentale.base_del_taglio.estimated_periods}
                                    periodi poggiano su una stima del ritardo.
                                </span>
                            {/if}
                        </div>
                    {/if}
                </div>
            {:else}
                <Assente titolo="Segnali fondamentali" motivo={fondamentale.reason}
                         azione={fondamentale.action} />
            {/if}
        </div>

        <div class="col-12 col-lg-6">
            <h3 class="h6">Cosa e' successo dopo</h3>

            {#if esito.dopo.motivo}
                <Assente titolo="Non ancora confrontabile" motivo={esito.dopo.motivo}
                         azione="scegli una data piu' lontana nel tempo" />
            {:else}
                <div class="small">
                    {#each Object.entries(esito.dopo.rendimenti) as [chiave, valore] (chiave)}
                        <div>
                            {ETICHETTE[chiave] ?? chiave}:
                            {#if valore === null}
                                <span class="text-secondary">
                                    — {motivoDelVuoto(chiave)}
                                </span>
                            {:else}
                                <Valore valore={percento(valore)} />
                            {/if}
                        </div>
                    {/each}
                    <div class="mt-2">
                        Nel frattempo e' sceso fino a
                        <Valore valore={percento(esito.dopo.discesa_massima)} />
                        ed e' salito fino a
                        <Valore valore={percento(esito.dopo.salita_massima)} />.
                    </div>
                    <div class="text-secondary">
                        {esito.dopo.sedute_dopo} sedute fino al {esito.dopo.ultima_data}.
                    </div>
                </div>
            {/if}
        </div>
    </div>
{/if}
