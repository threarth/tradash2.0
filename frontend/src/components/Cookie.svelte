<!--
    Cookie.svelte — cosa resta nel tuo browser, e cosa puoi rifiutare.
    feat (Blocco 10): un «Rifiuta» che rifiuta qualcosa di vero.

    ## Perche' il banner distingue due cose

    I cookie tecnici strettamente necessari non richiedono consenso (ePrivacy
    art. 5(3), art. 122 del Codice Privacy, linee guida del Garante del
    10/06/2021). Qui ce n'e' uno solo, ed e' quello della sessione: senza, non
    si resta connessi. Offrire un «Rifiuta» per QUELLO sarebbe una scelta finta.

    Le quattro preferenze salvate nel browser invece si possono rifiutare
    davvero, e rifiutandole vengono cancellate subito e smettono di essere
    scritte — vivono in memoria per la durata della pagina. Il codice che lo fa
    sta in `lib/preferenze.js`.

    L'elenco di cosa viene salvato arriva dal BACKEND. Scritto a mano qui
    dentro, invecchierebbe da solo alla prima preferenza nuova.
-->
<script>
    import { sessione } from "../lib/sessione.svelte.js";

    let inCorso = $state(false);

    async function decidi(preferenze) {
        inCorso = true;
        try {
            await sessione.decidi(preferenze);
        } finally {
            inCorso = false;
        }
    }

    const cookie = $derived(sessione.cosaSiSalva?.cookie ?? []);
    const preferenze = $derived(sessione.cosaSiSalva?.preferenze ?? []);
</script>

<div class="banner-cookie border-top bg-body-tertiary">
    <div class="container-fluid contenuto py-3">
        <div class="row g-3 align-items-center">
            <div class="col-lg-8">
                <h2 class="h6 mb-2">Cosa resta nel tuo browser</h2>

                {#each cookie as voce (voce.nome)}
                    <p class="small mb-1">
                        <strong>{voce.nome}</strong> — {voce.tipo}.
                        Contiene {voce.contiene}, e dura {voce.dura}.
                        <span class="text-warning">{voce.perche}.</span>
                    </p>
                {/each}

                <p class="small mb-1">
                    <strong>{preferenze.length} preferenze</strong> —
                    {preferenze.map((p) => p.cosa).join("; ")}.
                    Queste si possono rifiutare: se lo fai vengono cancellate subito
                    e valgono solo finche' la pagina resta aperta.
                </p>

                <p class="small text-secondary mb-0">
                    Nessun tracciamento, nessuna terza parte, niente che esca da questa
                    macchina. <a href="/privacy">Tutti i dettagli</a>.
                </p>
            </div>

            <div class="col-lg-4 d-flex gap-2 justify-content-lg-end">
                <button class="btn btn-outline-secondary" disabled={inCorso}
                        onclick={() => decidi(false)}>
                    Rifiuta le preferenze
                </button>
                <button class="btn btn-primary" disabled={inCorso}
                        onclick={() => decidi(true)}>
                    Consenti
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .banner-cookie {
        position: sticky;
        bottom: 0;
        z-index: 1030;
    }
</style>
