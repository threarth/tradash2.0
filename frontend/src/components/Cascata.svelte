<!--
    Cascata.svelte — dall'utile alla cassa, passo per passo.
    feat: il ponte c'era come tabella di numeri; la domanda che pone e' una forma.

    ## Perche' una cascata e non una tabella

    La domanda e' «dove se n'e' andato l'utile», e ha una forma: si parte da un
    numero, si aggiunge e si toglie, si arriva a un altro. Una tabella di sei
    colonne la costringe a fare la sottrazione a mente; una cascata la mostra.

    La tabella resta sotto, perche' la forma si guarda e i numeri esatti si
    leggono, e sono due gesti diversi.

    ## L'«altro» e' calcolato per differenza, e si vede

    Investimenti, imposte e tutto cio' che non sta nelle tre voci esplicite
    finisce li'. Non e' un residuo da nascondere: se e' grande e' proprio quello
    da guardare, e in una cascata un blocco grosso senza nome si nota subito —
    che e' esattamente il comportamento voluto.

    ## Niente libreria

    Sei barre e un asse: `lightweight-charts` non fa cascate e farne una con le
    sue primitive costerebbe piu' di venti righe di SVG. Qui l'SVG e' il modo
    semplice, non la scorciatoia.
-->
<script>
    import Testo from "./Testo.svelte";
    import Valore from "./Valore.svelte";

    let { ponte = [] } = $props();

    // Geometria del disegno, in unita' dell'SVG. La larghezza e' fissa e il
    // contenitore la scala: cosi' il testo non cambia corpo al variare della
    // finestra.
    const LARGHEZZA = 720;
    const ALTEZZA = 260;
    const MARGINE_ALTO = 18;
    const MARGINE_BASSO = 46;
    const SPAZIO_FRA_BARRE = 10;

    // Le soglie della conversione, dalla voce di glossario «Conversione in cassa».
    const CONVERSIONE_ECCELLENTE = 1.2;
    const CONVERSIONE_BUONA = 0.8;
    const CONVERSIONE_ATTENZIONE = 0.5;

    // I passi, nell'ordine in cui si sommano. Le etichette sono quelle del
    // glossario: e' cosi' che il rilevatore le riconosce e le sottolinea.
    const PASSI = [
        { chiave: "utile", nome: "Utile netto", totale: true },
        { chiave: "ammortamenti", nome: "Ammortamenti", totale: false },
        { chiave: "azioni_ai_dipendenti", nome: "Azioni ai dipendenti", totale: false },
        { chiave: "circolante", nome: "Capitale circolante", totale: false },
        { chiave: "altro", nome: "Altro", totale: false },
        { chiave: "cassa_libera", nome: "Cassa libera", totale: true }
    ];

    let scelto = $state(null);

    const riga = $derived(
        ponte.find((r) => r.periodo === scelto) ?? ponte[ponte.length - 1] ?? null
    );

    /** I blocchi della cascata: dove comincia, dove finisce, di che segno e'. */
    const blocchi = $derived.by(() => {
        if (!riga) return [];
        let cumulato = 0;
        return PASSI.map((passo) => {
            const valore = riga[passo.chiave] ?? 0;
            if (passo.totale) {
                // I due totali partono da zero: sono altezze, non variazioni.
                const blocco = { ...passo, valore, da: 0, a: valore };
                cumulato = valore;
                return blocco;
            }
            const da = cumulato;
            cumulato += valore;
            return { ...passo, valore, da, a: cumulato };
        });
    });

    const estremi = $derived.by(() => {
        const tutti = blocchi.flatMap((b) => [b.da, b.a]).concat(0);
        return { min: Math.min(...tutti), max: Math.max(...tutti) };
    });

    const larghezzaBarra = $derived(
        (LARGHEZZA - SPAZIO_FRA_BARRE * (PASSI.length + 1)) / PASSI.length
    );

    /** Dal valore alla coordinata verticale dell'SVG. */
    function y(valore) {
        const { min, max } = estremi;
        const campo = max - min || 1;
        const utile = ALTEZZA - MARGINE_ALTO - MARGINE_BASSO;
        return MARGINE_ALTO + utile * (1 - (valore - min) / campo);
    }

    const x = (indice) => SPAZIO_FRA_BARRE + indice * (larghezzaBarra + SPAZIO_FRA_BARRE);

    /** Il colore di un blocco: i totali neutri, le variazioni col loro segno. */
    function colore(blocco) {
        if (blocco.totale) return "var(--bs-secondary-color)";
        return blocco.valore >= 0 ? "var(--bs-success)" : "var(--bs-danger)";
    }

    const milioni = (valore) =>
        valore === null || valore === undefined
            ? "—"
            : `${(valore / 1e6).toLocaleString("it", { maximumFractionDigits: 0 })}M`;

    /** Quanti trimestri di fila stanno sotto la soglia bassa.
     *
     *  Serve a non gridare per un trimestre solo. Misurato su NVDA al
     *  31/07/2026: conversione 36%, e non e' un guaio — e' una societa' che
     *  cresce cosi' in fretta che crediti e magazzino assorbono trenta miliardi
     *  di circolante in un trimestre. Un cartellino rosso li' insegnerebbe a
     *  ignorare il cartellino.
     *
     *  Il glossario dice «per piu' trimestri di fila»: questo lo conta. */
    const bassiDiFila = $derived.by(() => {
        let quanti = 0;
        for (let i = ponte.length - 1; i >= 0; i -= 1) {
            const c = ponte[i].conversione;
            if (c === null || c === undefined || c >= CONVERSIONE_ATTENZIONE) break;
            quanti += 1;
        }
        return quanti;
    });

    // Sotto quante volte di fila una conversione bassa smette di essere un caso.
    const TRIMESTRI_PER_PREOCCUPARSI = 3;

    /** Come sta la conversione, con le soglie della voce di glossario.
     *
     *  Il giudizio guarda il trimestre mostrato, ma la voce PIU' severa la da'
     *  solo alla ripetizione: un trimestre sotto il 50% capita a chiunque
     *  cresca in fretta, tre di fila sono un'altra cosa. */
    const giudizio = $derived.by(() => {
        const c = riga?.conversione;
        if (c === null || c === undefined) {
            return { testo: "non calcolabile con un utile nullo o negativo",
                     classe: "text-secondary" };
        }
        if (c >= CONVERSIONE_ECCELLENTE) {
            return { testo: "eccellente: ogni euro dichiarato ne diventa piu' di uno in cassa",
                     classe: "text-success" };
        }
        if (c >= CONVERSIONE_BUONA) return { testo: "normale", classe: "text-body" };
        if (c >= CONVERSIONE_ATTENZIONE) {
            return { testo: "da guardare: buona parte dell'utile non arriva in cassa",
                     classe: "text-warning" };
        }
        if (bassiDiFila >= TRIMESTRI_PER_PREOCCUPARSI) {
            return { testo: `bassa da ${bassiDiFila} trimestri di fila: non e' un caso`,
                     classe: "text-danger" };
        }
        return { testo: "bassa in questo trimestre — normale per chi cresce in "
                        + "fretta, da seguire se si ripete",
                 classe: "text-warning" };
    });
</script>

{#if riga}
    <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
        <label class="form-label small mb-0 text-secondary" for="cascata-periodo">
            Trimestre
        </label>
        <select id="cascata-periodo" class="form-select form-select-sm"
                style="width: auto" bind:value={scelto}>
            {#each ponte as r (r.periodo)}
                <option value={r.periodo}>{r.periodo}</option>
            {/each}
        </select>

        <span class="small ms-auto">
            <Testo testo="Conversione in cassa" />:
            <strong class="numerico">
                {riga.conversione === null ? "n/d" : `${(riga.conversione * 100).toFixed(0)}%`}
            </strong>
            <span class={giudizio.classe}>· {giudizio.testo}</span>
        </span>
    </div>

    <svg viewBox="0 0 {LARGHEZZA} {ALTEZZA}" class="cascata" role="img"
         aria-label="Dall'utile netto alla cassa libera, passo per passo">
        <!-- Lo zero: senza, un blocco che scende sotto non si distingue da uno
             piccolo, e il segno e' proprio cio' che si vuole leggere. -->
        <line x1="0" x2={LARGHEZZA} y1={y(0)} y2={y(0)}
              stroke="var(--bs-border-color)" stroke-dasharray="3 3" />

        {#each blocchi as blocco, indice (blocco.chiave)}
            {@const alto = Math.max(y(blocco.da), y(blocco.a))}
            {@const basso = Math.min(y(blocco.da), y(blocco.a))}
            <rect x={x(indice)} y={basso} width={larghezzaBarra}
                  height={Math.max(2, alto - basso)} fill={colore(blocco)}
                  opacity={blocco.totale ? 0.55 : 0.85} rx="2" />

            <!-- Il valore sopra il blocco, il nome sotto: il nome e' lungo e in
                 mezzo alle barre si sovrapporrebbe. -->
            <text x={x(indice) + larghezzaBarra / 2} y={basso - 4}
                  text-anchor="middle" class="valore">
                {blocco.valore >= 0 && !blocco.totale ? "+" : ""}{milioni(blocco.valore)}
            </text>
            <text x={x(indice) + larghezzaBarra / 2} y={ALTEZZA - MARGINE_BASSO + 16}
                  text-anchor="middle" class="nome">{blocco.nome}</text>
        {/each}
    </svg>

    <p class="small text-secondary mb-0">
        <Testo testo="I due blocchi grigi sono i totali: si parte dall'utile netto e si arriva alla cassa libera. Quelli in mezzo sono le variazioni, verdi se aggiungono cassa e rosse se la tolgono. «Altro» e' calcolato per differenza — investimenti, imposte e il resto — e se e' grande e' proprio quello da guardare." />
    </p>
{/if}

<style>
    .cascata {
        width: 100%;
        height: auto;
    }

    .valore {
        font-size: 11px;
        fill: var(--bs-body-color);
        font-variant-numeric: tabular-nums;
    }

    .nome {
        font-size: 11px;
        fill: var(--bs-secondary-color);
    }
</style>
