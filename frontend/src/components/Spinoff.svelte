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
    che invecchia da sola. **Dalla data, non dalla prima seduta**: contati dai
    prezzi, NVRI dava 381 mesi e ANGI 178, perche' quei ticker non sono nuovi —
    hanno ereditato la storia della madre, e la riga lo dichiara.

    ## Il secondo pulsante

    L'elenco sono nomi. I **segnali** sono la misura: sei numeri per candidato,
    letti dai nostri dati. Anche quelli partono solo se li premi — sono decine
    di letture da Defeatbeta, lente la prima volta — e il calcolo e' un lavoro
    del registro: si vede nel pannello in alto mentre avanza, e si ferma.

    Il punteggio si legge **su quanti punti erano disponibili**, non su cento:
    un segnale che non si puo' misurare esce dal denominatore invece di valere
    zero. Ed e' la ragione per cui accanto c'e' sempre scritto su quanti
    segnali e' stato calcolato.
-->
<script>
    import { onMount } from "svelte";

    import Assente from "./Assente.svelte";
    import Testo from "./Testo.svelte";
    import Ticker from "./Ticker.svelte";
    import { api } from "../lib/api.js";

    const GIORNI_PER_MESE = 30.44;

    // Ogni quanto si chiede se il calcolo e' finito. Il pannello in alto ha il
    // suo battito e mostra i dettagli: qui basta sapere quando ricaricare.
    const RITMO_ATTESA_MS = 2000;

    // Oltre questa eta' uno spin-off non e' piu' «recente»: la separazione l'ha
    // gia' digerita il mercato. Si mostra lo stesso, ma smorzato.
    const MESI_RECENTE = 18;

    // Gli stati che il backend puo' dare a un candidato, con il colore che
    // dicono. L'ordine e' quello del racconto: prima chi non si puo' ancora
    // giudicare, poi chi si muove, poi chi ha confermato.
    const STATI = {
        "troppo presto": "text-bg-secondary",
        "niente ancora": "text-bg-light",
        "in movimento": "text-bg-warning",
        "numeri girati": "text-bg-success",
        "in raffreddamento": "text-bg-info",
        "non piu' scambiato": "text-bg-dark"
    };

    // I sei segnali nell'ordine in cui si leggono, col peso che hanno.
    const SEGNALI = ["volume", "margine", "ricavi", "eps", "forza", "media50"];

    let dati = $state(null);
    let errore = $state(null);
    let inCorso = $state(false);
    let calcolando = $state(false);

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

    /** Avvia il calcolo e aspetta che il lavoro sparisca dai vivi.

        Il backend torna subito col run_id — sono minuti di letture — e il
        pannello in alto mostra a che punto e'. Qui si guarda solo quando ha
        finito, per ricaricare la tabella una volta sola invece di ridisegnarla
        a ogni titolo. */
    async function calcola() {
        calcolando = true;
        errore = null;
        try {
            const avviato = await api.spinoffCalcola();
            await attendi(avviato.run_id);
            await carica();
        } catch (problema) {
            errore = problema.message;
        } finally {
            calcolando = false;
        }
    }

    function attendi(runId) {
        return new Promise((finito) => {
            const battito = setInterval(async () => {
                const vivi = await api.lavoriAttivi().catch(() => []);
                if (!vivi.some((l) => l.run_id === runId)) {
                    clearInterval(battito);
                    finito();
                }
            }, RITMO_ATTESA_MS);
        });
    }

    /** Quanti mesi sono passati dalla separazione. */
    const mesi = (quando) =>
        (Date.now() - new Date(quando).getTime()) / (GIORNI_PER_MESE * 86400000);

    const quando = (iso) => (iso ? new Date(iso).toLocaleString("it") : "mai");

    /** Le righe nell'ordine giusto: per punti quando ci sono, per data prima.

        Si ordina per punti PRESI e non per la loro quota: un candidato con due
        soli segnali calcolabili, entrambi pieni, farebbe quota 1 e finirebbe in
        cima davanti a chi ha sei segnali su sei — che e' il contrario di cio'
        che si vuole leggere. I punti assoluti tengono conto da soli di quanto
        poco si e' potuto misurare. */
    const righe = $derived.by(() => {
        const elenco = dati?.righe ?? [];
        if (!dati?.calcolato_il) return elenco;
        return [...elenco].sort((a, b) =>
            (b.misura?.punteggio?.presi ?? -1) - (a.misura?.punteggio?.presi ?? -1));
    });
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
            <div class="d-flex gap-2">
                <button class="btn btn-sm btn-outline-primary"
                        disabled={inCorso || calcolando} onclick={aggiorna}>
                    {inCorso ? "scarico…" : "Aggiorna l'elenco"}
                </button>
                <!-- Il secondo pulsante: l'elenco sono nomi, questo e' la
                     misura. Senza elenco non ha niente da misurare. -->
                <button class="btn btn-sm btn-primary"
                        disabled={calcolando || inCorso || !dati?.righe?.length}
                        onclick={calcola}>
                    {calcolando ? "calcolo…" : "Calcola i segnali"}
                </button>
            </div>
        </div>

        <p class="small text-secondary numerico">
            Elenco preso il {quando(dati?.preso_il)}
            {#if dati?.righe?.length}· {dati.righe.length} separazioni{/if}
            {#if dati?.calcolato_il}· segnali calcolati il {quando(dati.calcolato_il)}{/if}
        </p>

        {#if calcolando}
            <p class="small text-secondary mb-2">
                <Testo testo="Sto leggendo prezzi e bilanci di ogni candidato: la prima lettura di un titolo e' lenta. Il pannello in alto a destra dice a che punto e', e da li' si ferma." />
            </p>
        {/if}

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

        {#if dati?.calcolato_il}
            <p class="small text-secondary mb-1">
                <Testo testo="In ordine di punti presi. Due punteggi con denominatori diversi non sono la stessa misura: accanto c'e' scritto su quanti segnali e' stato calcolato, e «troppo presto» vuol dire che i trimestri dopo la separazione non bastano ancora." />
            </p>
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
                            {#if dati.calcolato_il}
                                <th class="text-end">Punti</th>
                                <th>A che punto</th>
                                {#each SEGNALI as nome (nome)}
                                    <th class="text-end" title="pesa {dati.pesi[nome]}">
                                        {nome}
                                    </th>
                                {/each}
                            {/if}
                        </tr>
                    </thead>
                    <tbody>
                        {#each righe as riga (riga.symbol + riga.data)}
                            {@const eta = mesi(riga.data)}
                            <tr class:text-secondary={eta > MESI_RECENTE}>
                                <td>
                                    <Ticker simbolo={riga.symbol} grassetto />
                                    {#if riga.nome}
                                        <div class="text-secondary">{riga.nome}</div>
                                    {/if}
                                </td>
                                <td>
                                    {#if riga.parent}
                                        <Ticker simbolo={riga.parent} />
                                    {:else}—{/if}
                                </td>
                                <td class="text-end numerico">{riga.data}</td>
                                <td class="text-end numerico">
                                    {eta.toFixed(0)}
                                    {#if riga.misura?.storia_precedente}
                                        <!-- Il ticker non e' nuovo: ha ereditato
                                             la storia della madre, e li' il
                                             ragionamento «quotato da poco» non vale. -->
                                        <i class="bi bi-clock-history text-warning"
                                           title="quotato gia' prima della separazione"
                                        ></i>
                                    {/if}
                                </td>

                                {#if dati.calcolato_il}
                                    {@const m = riga.misura}
                                    {#if !m}
                                        <td colspan={2 + SEGNALI.length}
                                            class="text-secondary">non misurato</td>
                                    {:else if !m.disponibile}
                                        <td class="text-end">—</td>
                                        <td colspan={1 + SEGNALI.length}
                                            class="text-secondary">
                                            {#if m.stato}<Testo testo={m.stato} /> · {/if}
                                            {m.motivo}
                                        </td>
                                    {:else}
                                        <td class="text-end numerico">
                                            <strong>{m.punteggio.presi}</strong>
                                            <span class="text-secondary">
                                                /{m.punteggio.disponibili}
                                            </span>
                                            <div class="text-secondary">
                                                {m.punteggio.calcolabili} segnali
                                                su {m.punteggio.totali}
                                            </div>
                                        </td>
                                        <td>
                                            <span class="badge {STATI[m.stato] ?? 'text-bg-light'}">
                                                <Testo testo={m.stato} />
                                            </span>
                                        </td>
                                        {#each SEGNALI as nome (nome)}
                                            {@const s = m.segnali[nome]}
                                            <td class="text-end numerico"
                                                class:text-success={s.quota === 1}
                                                class:text-secondary={s.quota === null}
                                                title={s.nota}>
                                                {s.quota === null ? "—" : s.nota}
                                            </td>
                                        {/each}
                                    {/if}
                                {/if}
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>

            {#if righe.some((r) => r.misura?.storia_precedente)}
                <p class="small text-secondary mt-2 mb-0">
                    <i class="bi bi-clock-history text-warning"></i>
                    <Testo testo="L'orologio segna un ticker non nuovo: i suoi prezzi cominciano molto prima della separazione, quindi non e' una quotazione recente." />
                </p>
            {/if}
        {/if}
    </div>
</div>
