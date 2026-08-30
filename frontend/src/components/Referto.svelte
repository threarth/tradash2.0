<!--
    Referto.svelte — un referto qualunque, mostrato per intero.
    feat (Blocco 8): il report qualitativo ha prosa, oggetti e citazioni; l'elenco no.

    Prima di questo componente il referto veniva mostrato scoprendone le
    sezioni, ma sapeva stampare **solo gli elenchi di stringhe**: la prosa non
    compariva affatto, e un elenco di oggetti — le menzioni dello spin-off, le
    citazioni, i vantaggi competitivi — finiva a schermo come "[object Object]".

    Le sezioni continuano a scoprirsi dal referto invece di essere elencate qui:
    ogni metodo ne ha di sue, e un elenco fisso ne perderebbe una a ogni metodo
    nuovo senza dirlo. Quello che cambia e' che ora si guarda anche di che
    FORMA e' la sezione, non solo che ci sia.
-->
<script>
    import Pillola from "./Pillola.svelte";
    import Testo from "./Testo.svelte";

    let { contenuto } = $props();

    // I dati su cui il referto poggia: stanno gia' nelle loro sezioni della
    // scheda, e ripeterli qui coprirebbe la prosa.
    const TECNICI = new Set([
        "segnali", "metriche", "misure", "metriche_mancanti", "confronto_industria",
        "call", "call_precedente", "testi_troncati", "caratteri_originali",
        "confidenza", "classificazione", "classificazione_scartata",
        "citations", "citazioni_scartate", "senza_riscontro", "copertura",
        "menzioni_trovate", "menzioni_notizie", "menzioni_call",
    ]);

    // L'ordine in cui si legge un report qualitativo. Le sezioni che non sono
    // qui vengono dopo, nell'ordine in cui il referto le porta: cosi' un metodo
    // nuovo non deve toccare questo elenco per mostrare le sue.
    const ORDINE = [
        "thesis", "lettura", "business_overview", "cost_structure",
        "customers_revenue_quality", "competitors", "competitive_advantages",
        "industry_outlook", "management_governance", "recent_developments",
        "five_year_narrative", "bull_case", "bear_case", "punti_di_forza",
        "punti_deboli", "key_risks", "da_sorvegliare", "dati_mancanti",
    ];

    const posizione = (chiave) => {
        const trovata = ORDINE.indexOf(chiave);
        return trovata < 0 ? ORDINE.length : trovata;
    };

    /** Le sezioni mostrabili, ordinate, quali che siano. */
    const sezioni = $derived(
        Object.entries(contenuto ?? {})
            .filter(([chiave, valore]) => !TECNICI.has(chiave) && !vuota(valore))
            .sort(([a], [b]) => posizione(a) - posizione(b))
    );

    function vuota(valore) {
        if (valore === null || valore === undefined) return true;
        if (typeof valore === "string") return valore.trim() === "";
        if (Array.isArray(valore)) return valore.length === 0;
        return false;
    }

    const etichetta = (chiave) =>
        chiave.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

    /** Un valore dentro un oggetto, ridotto a una riga leggibile. */
    const riga = (valore) =>
        Array.isArray(valore) ? valore.map(riga).join(" · ") : String(valore ?? "—");

    const classificazione = $derived(
        Object.entries(contenuto?.classificazione ?? {})
            .filter(([, dati]) => (dati?.etichette ?? []).length > 0)
    );

    const citazioni = $derived(contenuto?.citations ?? []);
    const copertura = $derived(contenuto?.copertura ?? null);
</script>

{#each sezioni as [chiave, valore] (chiave)}
    <div class="mt-2">
        <div class="fw-semibold">{etichetta(chiave)}</div>

        {#if typeof valore === "string"}
            <p class="mb-0"><Testo testo={valore} /></p>
        {:else if Array.isArray(valore)}
            <ul class="mb-0">
                {#each valore as voce, i (i)}
                    <li>
                        {#if voce !== null && typeof voce === "object"}
                            {#each Object.entries(voce) as [campo, dato] (campo)}
                                <div>
                                    <span class="text-secondary">{etichetta(campo)}:</span>
                                    <Testo testo={riga(dato)} />
                                </div>
                            {/each}
                        {:else}
                            <Testo testo={String(voce)} />
                        {/if}
                    </li>
                {/each}
            </ul>
        {:else}
            <p class="mb-0"><Testo testo={riga(valore)} /></p>
        {/if}
    </div>
{/each}

{#if classificazione.length}
    <div class="mt-3">
        <div class="fw-semibold">Come funziona questa azienda</div>
        {#each classificazione as [dimensione, dati] (dimensione)}
            <div class="mt-1">
                <span class="text-secondary small">{etichetta(dimensione)}:</span>
                {#each dati.etichette as nome (nome)}
                    <Pillola testo={nome} genere="tema" />
                {/each}
                {#if dati.confidenza}
                    <span class="small text-secondary">({dati.confidenza})</span>
                {/if}
                {#each dati.evidenze_documentali ?? [] as prova, i (i)}
                    <div class="small text-secondary ms-2">— <Testo testo={prova} /></div>
                {/each}
                {#each dati.evidenze_quantitative ?? [] as prova, i (i)}
                    <div class="small text-secondary ms-2">— <Testo testo={prova} /></div>
                {/each}
            </div>
        {/each}

        <!-- Un'etichetta fuori vocabolario non viene corretta d'ufficio:
             correggerla vorrebbe dire indovinare cosa intendeva il modello. -->
        {#each contenuto.classificazione_scartata ?? [] as scarto, i (i)}
            <div class="small text-warning">Non classificato — <Testo testo={scarto} /></div>
        {/each}
    </div>
{/if}

{#if citazioni.length}
    <details class="mt-3">
        <summary class="fw-semibold">
            {citazioni.length} citazioni verificate nel testo del documento
        </summary>
        {#each citazioni as citazione, i (i)}
            <div class="mt-2 small">
                <div><Testo testo={citazione.claim ?? ""} /></div>
                <div class="text-secondary fst-italic">«{citazione.quote}»</div>
                <div class="text-secondary numerico">{citazione.document_id}</div>
            </div>
        {/each}
    </details>
{/if}

{#if copertura}
    <div class="mt-3 small text-secondary">
        <div class="fw-semibold">Su cosa poggia questo referto</div>
        <div>Documenti letti: {copertura.documenti_letti.join(", ") || "nessuno"}</div>
        <div>Sezioni lette: {copertura.sezioni_lette.join(", ")}</div>

        <!-- Un testo troncato mostrato senza dirlo si legge come se quella
             fosse tutta la fonte. -->
        {#if copertura.sezioni_troncate.length}
            <div class="text-warning">
                Sezioni troncate prima di arrivare al modello:
                {copertura.sezioni_troncate.join(", ")}
            </div>
        {/if}
        {#each copertura.sezioni_non_lette ?? [] as avviso, i (i)}
            <div class="text-warning">Non letto — <Testo testo={avviso} /></div>
        {/each}
        {#if copertura.citazioni_scartate > 0}
            <div class="text-warning">
                {copertura.citazioni_scartate} citazioni scartate: non si trovano
                alla lettera nel documento indicato.
            </div>
        {/if}
        {#each copertura.fonti_non_disponibili ?? [] as fonte, i (i)}
            <div>Fonte non disponibile — <Testo testo={fonte} /></div>
        {/each}
    </div>
{/if}
