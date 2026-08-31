<!--
    Titolo.svelte — la scheda di un titolo: il guscio, e le sezioni che verranno.
    feat (Blocco 6): intestazione, grafico, e le sezioni che dichiarano di mancare.

    Il precedente da non ripetere sono le 1.342 righe della pagina omonima nel
    vecchio tradash, che montava una ventina di componenti sapendo tutto. Qui
    e' un guscio: i blocchi 7 e 8 aggiungono le loro sezioni senza toccare le
    altre, e finche' non ci sono la pagina lo DICE — con dentro quale blocco le
    portera' — invece di far finta che quel dato non esista.
-->
<script>
    import Assente from "../components/Assente.svelte";
    import Caricamento from "../components/Caricamento.svelte";
    import Errore from "../components/Errore.svelte";
    import Analisi from "../components/Analisi.svelte";
    import Documenti from "../components/Documenti.svelte";
    import FilingDaSalvare from "../components/FilingDaSalvare.svelte";
    import Fondamentali from "../components/Fondamentali.svelte";
    import Grafico from "../components/Grafico.svelte";
    import Metriche from "../components/Metriche.svelte";
    import NavigatoreSezioni from "../components/NavigatoreSezioni.svelte";
    import PannelloIndicatori from "../components/PannelloIndicatori.svelte";
    import Ricostruzione from "../components/Ricostruzione.svelte";
    import Salute from "../components/Salute.svelte";
    import Segnali from "../components/Segnali.svelte";
    import Sezione from "../components/Sezione.svelte";
    import Simulatore from "../components/Simulatore.svelte";
    import Testo from "../components/Testo.svelte";
    import Valore from "../components/Valore.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";
    import { sezioni } from "../lib/sezioni.svelte.js";

    let { simbolo } = $props();

    let intervallo = $state("1A");

    const scheda = richiedi(() => api.titolo(simbolo));
    const grafico = richiedi(() => api.titoloPrezzi(simbolo, intervallo));

    // La scheda si ricarica quando cambia il simbolo, il grafico anche quando
    // cambia l'intervallo. Leggerli qui li rende dipendenze dell'effetto.
    $effect(() => {
        simbolo;
        scheda.ricarica();
        // Cambiando titolo l'indice riparte: le sezioni si riregistrano da sole
        // quando si rimontano, e un elenco che non si azzera mostrerebbe per un
        // istante quelle del titolo di prima.
        return () => sezioni.azzera();
    });

    $effect(() => {
        simbolo;
        intervallo;
        grafico.ricarica();
    });
</script>

{#if scheda.primoCaricamento}
    <Caricamento testo={`carico ${simbolo}…`} />
{:else if scheda.errore}
    <Errore errore={scheda.errore} riprova={scheda.ricarica} />
{:else if scheda.dato}
    {@const profilo = scheda.dato.profilo}

    <div class="d-flex justify-content-between align-items-start gap-3 mb-3">
        <div>
            <h1 class="h3 mb-1">
                {scheda.dato.symbol}
                {#if scheda.dato.name}
                    <span class="fs-5 text-secondary">{scheda.dato.name}</span>
                {/if}
            </h1>
            {#if profilo.available}
                <div class="text-secondary">
                    <Valore valore={profilo.sector} mancante="settore non classificato" />
                    ·
                    <Valore valore={profilo.industry} mancante="industria non classificata" />
                    {#if profilo.country}· {profilo.country}{/if}
                </div>
            {/if}
        </div>
        <a class="btn btn-sm btn-outline-secondary" href="/watchlist">← Watchlist</a>
    </div>

    {#if !profilo.available}
        <Assente titolo="Questo titolo non ha un profilo"
                 motivo={profilo.reason} azione={profilo.action} />
    {:else}
    <!-- La scheda e' lunga: l'indice sta a destra e segue dove sei. Su schermi
         stretti sparisce, perche' li' ruberebbe piu' spazio di quanto ne
         faccia risparmiare. -->
    <div class="row g-4">
    <div class="col-12 col-xl-10">
        {#if profilo.long_business_summary}
            <details class="mb-3">
                <summary class="text-secondary small">Cosa fa questa societa'</summary>
                <p class="small mt-2 mb-0"><Testo testo={profilo.long_business_summary} /></p>
            </details>
        {/if}

        <div class="d-flex justify-content-between align-items-center mb-2">
            <h2 class="h6 mb-0">Prezzo</h2>
            <div class="btn-group btn-group-sm">
                {#each (grafico.dato?.intervalli ?? []) as nome (nome)}
                    <button class="btn {intervallo === nome
                                ? 'btn-primary' : 'btn-outline-secondary'}"
                            onclick={() => (intervallo = nome)}>{nome}</button>
                {/each}
            </div>
        </div>

        {#if grafico.primoCaricamento}
            <Caricamento testo="carico i prezzi…" />
        {:else if grafico.errore}
            <Errore errore={grafico.errore} riprova={grafico.ricarica} />
        {:else if grafico.dato}
            <!-- Il grafico e il pannello degli indicatori stanno accanto: il
                 pannello serve MENTRE si guarda il grafico, e in fondo alla
                 pagina costringerebbe a scorrere avanti e indietro per vedere
                 l'effetto di ogni modifica. -->
            <div class="row g-3">
                <div class="col-12 col-xl-9">
                    <Grafico barre={grafico.dato.barre} serie={grafico.dato.serie}
                             configurazione={grafico.dato.configurazione} />
                    <p class="small text-secondary mt-2">
                        {grafico.dato.barre.length} sedute mostrate ·
                        {grafico.dato.sedute_calcolate} usate per calcolare gli
                        indicatori · dati arrivati da {grafico.dato.source}
                    </p>
                </div>
                <div class="col-12 col-xl-3">
                    <PannelloIndicatori {simbolo}
                                        configurazione={grafico.dato.configurazione}
                                        salvata={grafico.ricarica} />
                </div>
            </div>
        {/if}

        <hr class="my-4" />

        <Sezione id="salute" titolo="Salute finanziaria"
                 descrizione="Le grandezze di bilancio e i rapporti di solidita'. Nessun punteggio di sintesi: il giudizio lo da' l'analisi fondamentale, ed e' uno solo.">
            <Salute {simbolo} />
        </Sezione>

        <Sezione id="segnali" titolo="Segnali di rischio fondamentale"
                 descrizione="Deterministici: calcolati dai bilanci, senza modelli linguistici.">
            <Segnali {simbolo} />
        </Sezione>

        <Sezione id="metriche" titolo="Metriche"
                 descrizione="Calcolate dalla libreria di Defeatbeta, lette attraverso il registro. Nessuna parte aprendo la pagina: si chiedono una alla volta.">
            <Metriche {simbolo} />
        </Sezione>

        <Sezione id="fondamentali" titolo="Fondamentali" aperta={false}>
            <Fondamentali {simbolo} />
        </Sezione>

        <Sezione id="notizie" titolo="Notizie e documenti" aperta={false}>
            <Documenti {simbolo} />
        </Sezione>

        <!-- Chiusa di default: e' un elenco di consultazione, e aperto spinge
             in fondo alla pagina tutto quello che viene dopo. -->
        <Sezione id="filing" titolo="Documenti SEC per l'analisi qualitativa" aperta={false}
                 descrizione="Defeatbeta porta l'indice dei depositi, non il loro testo — e il testo e' la fonte primaria della qualitativa. Questi sono i documenti che servono: aprili, salvali nella cartella, e il sistema li riconosce.">
            <FilingDaSalvare {simbolo} />
        </Sezione>

        <Sezione id="analisi" titolo="Analisi">
            <Analisi {simbolo} />
        </Sezione>

        <Sezione id="simulatore" titolo="Cosa si sarebbe vissuto tenendolo" aperta={false}
                 descrizione="Non e' un backtest di strategia: e' una posizione sola, comprata un giorno e tenuta fino a oggi. La domanda non e' quanto si sarebbe guadagnato — quello lo dice il grafico — ma cosa si sarebbe passato nel mezzo. In dollari: non abbiamo una fonte per i cambi, quindi l'effetto valuta qui non c'e' e non viene stimato.">
            <Simulatore {simbolo} />
        </Sezione>

        <Sezione id="ricostruzione" titolo="Come si vedeva a una data passata" aperta={false}
                 descrizione="Le misure di allora, ricostruite sui soli dati che a quella data erano pubblici — i prezzi fino a quel giorno, i bilanci gia' depositati — e accanto cosa e' successo dopo. Nessun modello: il giudizio su come e' andata lo fai tu.">
            <Ricostruzione {simbolo} />
        </Sezione>

        {#each Object.entries(scheda.dato.sezioni_future) as [nome, sezione] (nome)}
            <Sezione id={`futura-${nome}`} titolo={nome}>
                <Assente titolo="Non ancora costruita"
                         motivo={sezione.reason} azione={sezione.action} />
            </Sezione>
        {/each}
    </div>

    <div class="col-12 col-xl-2">
        <NavigatoreSezioni />
    </div>
    </div>
    {/if}
{/if}
