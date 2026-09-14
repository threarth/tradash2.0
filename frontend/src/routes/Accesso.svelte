<!--
    Accesso.svelte — la porta, vista da chi sta fuori.
    feat (Blocco 10): un utente solo, e un messaggio che non aiuta chi prova.

    Il messaggio di errore e' quello che manda il backend, ed e' lo STESSO per
    nome sbagliato e password sbagliata. Non e' pigrizia: distinguerli direbbe a
    chi sta provando quali nomi esistono.
-->
<script>
    import { sessione } from "../lib/sessione.svelte.js";

    let nome = $state("");
    let password = $state("");
    let errore = $state(null);
    let inCorso = $state(false);

    async function entra(evento) {
        evento.preventDefault();
        errore = null;
        inCorso = true;
        try {
            await sessione.entra(nome, password);
        } catch (problema) {
            errore = problema.message;
            password = "";
        } finally {
            inCorso = false;
        }
    }
</script>

<div class="d-flex align-items-center justify-content-center min-vh-100 px-3">
    <div class="card shadow-sm accesso">
        <div class="card-body p-4">
            <h1 class="h4 mb-1">tradash</h1>
            <p class="text-secondary small mb-4">
                Strumento personale di analisi. Serve l'accesso.
            </p>

            {#if !sessione.configurato}
                <!-- Regola 5: l'assenza si dichiara col motivo E con l'azione.
                     Senza questo, chi installa il sistema su una macchina nuova
                     vedrebbe una schermata che rifiuta qualunque password senza
                     dire che l'utente non e' ancora stato creato. -->
                <div class="alert alert-warning small">
                    <strong>Nessun utente configurato.</strong>
                    Sul server, dalla cartella <code>backend/</code>:
                    <div class="mt-2"><code>python manage.py utente</code></div>
                </div>
            {:else}
                <form onsubmit={entra}>
                    <div class="mb-3">
                        <label class="form-label small" for="nome">Nome utente</label>
                        <input class="form-control" id="nome" type="text"
                               autocomplete="username" bind:value={nome}
                               disabled={inCorso} required />
                    </div>
                    <div class="mb-3">
                        <label class="form-label small" for="password">Password</label>
                        <input class="form-control" id="password" type="password"
                               autocomplete="current-password" bind:value={password}
                               disabled={inCorso} required />
                    </div>

                    {#if errore}
                        <div class="alert alert-danger small py-2">{errore}</div>
                    {/if}

                    <button class="btn btn-primary w-100" type="submit" disabled={inCorso}>
                        {inCorso ? "controllo…" : "Entra"}
                    </button>
                </form>
            {/if}
        </div>
    </div>
</div>

<style>
    .accesso {
        width: 100%;
        max-width: 22rem;
    }
</style>
