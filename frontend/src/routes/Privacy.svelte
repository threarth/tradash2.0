<!--
    Privacy.svelte — cosa viene salvato, e il tuo accesso.
    feat (Blocco 10): l'informativa non e' scritta a mano, la compone il backend.

    Due cose in una pagina perche' sono la stessa cosa vista da due lati: qui
    c'e' tutto quello che il sistema sa di TE — che e' pochissimo — e i due
    pulsanti con cui puoi cambiarlo.

    L'elenco di cosa si salva arriva da `/api/auth/stato`. Deve arrivare da li':
    una lista scritta a mano in questa pagina resterebbe indietro alla prima
    preferenza nuova, e un'informativa che dice il falso e' peggio di nessuna.
-->
<script>
    import Testo from "../components/Testo.svelte";
    import { api } from "../lib/api.js";
    import { sessione } from "../lib/sessione.svelte.js";

    let vecchia = $state("");
    let nuova = $state("");
    let esito = $state(null);
    let inCorso = $state(false);

    const cosa = $derived(sessione.cosaSiSalva);

    async function cambia(evento) {
        evento.preventDefault();
        esito = null;
        inCorso = true;
        try {
            await api.cambiaPassword(vecchia, nuova);
            // Il cambio fa scadere ogni sessione, compresa questa: si torna
            // all'accesso, ed e' la prova che il cambio ha avuto effetto.
            sessione.connesso = false;
            sessione.utente = null;
        } catch (problema) {
            esito = { errore: problema.message };
        } finally {
            vecchia = "";
            nuova = "";
            inCorso = false;
        }
    }
</script>

<h1 class="h4 mb-3">Privacy e accesso</h1>

<div class="row g-4">
    <div class="col-lg-7">
        <div class="card h-100"><div class="card-body">
            <h2 class="h6">Cosa resta nel tuo browser</h2>

            {#if cosa}
                <h3 class="small text-secondary text-uppercase mt-3 mb-2">Cookie</h3>
                {#each cosa.cookie as voce (voce.nome)}
                    <div class="border rounded p-3 mb-2">
                        <div class="fw-semibold numerico">{voce.nome}</div>
                        <div class="small text-secondary">{voce.tipo}</div>
                        <ul class="small mb-0 mt-2">
                            <li>Contiene: {voce.contiene}</li>
                            <li>Dura: {voce.dura}</li>
                            <li>
                                {voce.rifiutabile ? "Si puo' rifiutare" : "Non si puo' rifiutare"}
                                — {voce.perche}
                            </li>
                        </ul>
                    </div>
                {/each}

                <h3 class="small text-secondary text-uppercase mt-4 mb-2">
                    Preferenze — queste si possono rifiutare
                </h3>
                <ul class="small">
                    {#each cosa.preferenze as voce (voce.nome)}
                        <li><span class="numerico">{voce.nome}</span> — {voce.cosa}</li>
                    {/each}
                </ul>

                <p class="small text-secondary mb-0">
                    Terze parti: <strong>{cosa.terze_parti.length === 0
                        ? "nessuna" : cosa.terze_parti.join(", ")}</strong>.
                    Tracciamento: <strong>{cosa.tracciamento ? "si'" : "no"}</strong>.
                    Nessun servizio di statistiche, nessun font remoto, nessun
                    contenuto caricato da altri siti.
                </p>

                <hr />
                <p class="small mb-1">
                    <strong>La tua scelta adesso:</strong>
                    {#if sessione.consenso === null}
                        non hai ancora deciso — le preferenze non vengono salvate.
                    {:else if sessione.consenso.preferenze}
                        preferenze <strong>consentite</strong>, dal
                        {sessione.consenso.deciso_il}.
                    {:else}
                        preferenze <strong>rifiutate</strong>, dal
                        {sessione.consenso.deciso_il}. Funzionano finche' la pagina
                        resta aperta, e non vengono scritte su disco.
                    {/if}
                </p>
                <div class="d-flex gap-2 mt-2">
                    <button class="btn btn-sm btn-outline-secondary"
                            onclick={() => sessione.decidi(false)}>Rifiuta</button>
                    <button class="btn btn-sm btn-outline-primary"
                            onclick={() => sessione.decidi(true)}>Consenti</button>
                </div>
            {:else}
                <p class="small text-secondary mb-0">
                    <Testo testo="l'elenco non e' ancora arrivato dal server" />
                </p>
            {/if}
        </div></div>
    </div>

    <div class="col-lg-5">
        <div class="card h-100"><div class="card-body">
            <h2 class="h6">Il tuo accesso</h2>
            <p class="small text-secondary">
                Sei entrato come <strong>{sessione.utente}</strong>.
                Cambiare la password fa scadere <strong>tutte</strong> le sessioni
                aperte, compresa questa: dovrai rientrare, ed e' la prova che il
                cambio ha avuto effetto.
            </p>

            <form onsubmit={cambia}>
                <div class="mb-3">
                    <label class="form-label small" for="vecchia">Password attuale</label>
                    <input class="form-control form-control-sm" id="vecchia" type="password"
                           autocomplete="current-password" bind:value={vecchia}
                           disabled={inCorso} required />
                </div>
                <div class="mb-3">
                    <label class="form-label small" for="nuova">Password nuova</label>
                    <input class="form-control form-control-sm" id="nuova" type="password"
                           autocomplete="new-password" bind:value={nuova}
                           disabled={inCorso} required />
                </div>

                {#if esito?.errore}
                    <div class="alert alert-danger small py-2">{esito.errore}</div>
                {/if}

                <button class="btn btn-sm btn-primary" type="submit" disabled={inCorso}>
                    Cambia password
                </button>
            </form>
        </div></div>
    </div>
</div>
