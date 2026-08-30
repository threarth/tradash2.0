<!--
    Legenda.svelte — cosa vogliono dire Profilo e Maturity.
    feat (Blocco 4): testo copiato dal thematic-equity-monitor.

    Una scala con sei gradini serve a poco se i gradini non sono definiti: qui
    la definizione sta accanto ai dati, non nella testa di chi li ha inseriti.
-->
<script>
    import Testo from "./Testo.svelte";

    const PROFILI = [
        ["CORE", "business gia' provato, scala e visibilita' economica relativamente elevate."],
        ["EMERGING", "business commerciale reale ma ancora in accelerazione, concentrazione o " +
            "costruzione della scala."],
        ["OPTIONALITY", "gran parte del valore dipende da programmi futuri non ancora " +
            "economicamente provati."]
    ];

    const MATURITY = [
        ["CONCEPT", "idea o programma annunciato, senza ancora una prova tecnica."],
        ["DEVELOPMENT", "tecnologia o prodotto in sviluppo, senza validazione commerciale " +
            "sufficiente."],
        ["DEMONSTRATED", "prova tecnica o primi impieghi riusciti, ma modello non ancora scalato."],
        ["CONTRACTED", "contratti e ordini danno visibilita', ma l'esecuzione operativa e' " +
            "ancora da completare."],
        ["OPERATIONAL", "prodotto o impianto e' in servizio e genera attivita' reale."],
        ["SCALED", "attivita' consolidata su volumi ampi, piu' clienti e mercati, processi " +
            "ripetibili."]
    ];
</script>

<details class="mb-3">
    <summary class="text-secondary small">Come leggere Profilo e Maturity</summary>
    <div class="row g-4 mt-1">
        <div class="col-12 col-lg-6">
            <h3 class="h6">Profilo</h3>
            {#each PROFILI as [nome, significato] (nome)}
                <p class="small mb-1"><strong>{nome}</strong> — <Testo testo={significato} /></p>
            {/each}
        </div>
        <div class="col-12 col-lg-6">
            <h3 class="h6">Maturity</h3>
            {#each MATURITY as [nome, significato] (nome)}
                <p class="small mb-1"><strong>{nome}</strong> — <Testo testo={significato} /></p>
            {/each}
        </div>
    </div>
</details>
