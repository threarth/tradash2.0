<!--
    Freschezza.svelte — quali dati della watchlist sono ormai vecchi.
    feat: la regola 3 non aveva nessuna interfaccia.

    Il backend sa da sempre rispondere a «quali titoli hanno il prezzo vecchio»,
    categoria per categoria, e nessuna pagina lo chiedeva. Una guardia che
    nessuno puo' guardare protegge solo sulla carta.

    **Per categoria e non in blocco**, ed e' il punto: il prezzo di un titolo
    puo' essere da rinfrescare mentre il suo profilo va benissimo, e chiedere
    tutto insieme vorrebbe dire riscaricare ogni volta anche cio' che non serve.

    L'elenco delle categorie arriva dal backend. Quali riguardino un titolo e
    quali siano globali — l'universo, il rendimento del Tesoro — e' una
    proprieta' dei dati, non una scelta di chi disegna la pagina.
-->
<script>
    import Assente from "./Assente.svelte";
    import Errore from "./Errore.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    const SECONDI_PER_ORA = 3600;
    const SECONDI_PER_GIORNO = 86400;

    let scelta = $state("price");
    let inCorso = $state(false);
    let esito = $state(null);
    let errore = $state(null);

    const categorie = richiedi(() => api.categorieFreschezza());
    $effect(() => categorie.ricarica());

    /** Un'eta' in secondi detta come la direbbe una persona. */
    function eta(secondi) {
        if (secondi === null || secondi === undefined) return "mai preso";
        if (secondi < SECONDI_PER_ORA) return `${Math.round(secondi / 60)} minuti fa`;
        if (secondi < SECONDI_PER_GIORNO) return `${Math.round(secondi / SECONDI_PER_ORA)} ore fa`;
        return `${Math.round(secondi / SECONDI_PER_GIORNO)} giorni fa`;
    }

    const scadenza = (secondi) =>
        secondi >= SECONDI_PER_GIORNO
            ? `${Math.round(secondi / SECONDI_PER_GIORNO)} giorni`
            : `${Math.round(secondi / SECONDI_PER_ORA)} ore`;

    async function guarda() {
        inCorso = true;
        errore = null;
        try {
            esito = await api.daAggiornare(scelta);
        } catch (problema) {
            errore = problema;
            esito = null;
        } finally {
            inCorso = false;
        }
    }
</script>

<div class="d-flex align-items-end gap-2 flex-wrap mb-2">
    <div>
        <label class="form-label small mb-1" for="freschezza-categoria">Quale dato</label>
        <select id="freschezza-categoria" class="form-select form-select-sm"
                bind:value={scelta}>
            {#each categorie.dato?.categorie ?? [] as c (c.nome)}
                <option value={c.nome}>{c.nome} — scade dopo {scadenza(c.ttl_s)}</option>
            {/each}
        </select>
    </div>
    <button class="btn btn-sm btn-primary" disabled={inCorso} onclick={guarda}>
        {inCorso ? "guardo…" : "Guarda cosa e' vecchio"}
    </button>
</div>

{#if errore}
    <Errore {errore} riprova={guarda} />
{/if}

{#if esito}
    {#if esito.titoli.length === 0}
        <Assente titolo="Niente da rinfrescare"
                 motivo={`tutti i ${esito.osservati} titoli osservati hanno «${esito.categoria}» ancora buono`}
                 azione={null} />
    {:else}
        <p class="small mb-1">
            <strong>{esito.titoli.length}</strong> titoli su {esito.osservati} hanno
            «{esito.categoria}» da rinfrescare.
        </p>
        <!-- Il motivo accanto a ogni titolo, non solo l'elenco: «mai preso» e
             «vecchio di tre giorni» chiedono cose diverse. -->
        <div class="table-responsive" style="max-height: 18rem">
            <table class="table table-sm small mb-0">
                <tbody>
                    {#each esito.titoli as titolo (titolo.symbol)}
                        <tr>
                            <td class="numerico">
                                <a href={`/titolo/${titolo.symbol}`}>{titolo.symbol}</a>
                            </td>
                            <td class="numerico text-secondary">{eta(titolo.eta_s)}</td>
                            <td class="text-secondary"><Testo testo={titolo.motivo} /></td>
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>
    {/if}
{/if}
