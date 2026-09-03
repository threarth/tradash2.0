<!--
    Rischio.svelte — quanto si puo' perdere, e per quale ragione.
    feat: il punteggio deterministico, mostrato coi numeri che l'hanno deciso.

    **Non viene dopo un'analisi: viene prima.** Tutti i suoi ingredienti sono
    calcolati da codice che non parla con nessun modello, e le analisi lo
    ricevono gia' fatto invece di inventarsene uno.

    La banda complessiva e' il PEGGIORE dei componenti, non la media, ed e'
    scritto a schermo: senza, un «alto» accanto a tre «basso» sembra un errore.
    E cio' che non si e' potuto calcolare non abbassa il rischio — abbassa la
    confidenza, che sta accanto e non dentro.
-->
<script>
    import Riquadro from "./Riquadro.svelte";
    import Testo from "./Testo.svelte";
    import { api } from "../lib/api.js";
    import { richiedi } from "../lib/carica.svelte.js";

    let { simbolo } = $props();

    const rischio = richiedi(() => api.rischio(simbolo));
    $effect(() => {
        simbolo;
        rischio.ricarica();
    });

    const CLASSE = {
        alto: "text-danger",
        medio: "text-warning",
        basso: "text-success",
        "non calcolabile": "text-secondary",
    };

    const percento = (v) =>
        typeof v === "number" ? `${(v * 100).toFixed(0)}%` : null;
</script>

<Riquadro richiesta={rischio} testoCaricamento="calcolo il rischio…">
    {#snippet children(d)}
        <div class="d-flex align-items-baseline gap-3 flex-wrap mb-2">
            <span class="fs-4 text-uppercase {CLASSE[d.banda] ?? ''}">{d.banda}</span>
            {#if d.deciso_da}
                <span class="small text-secondary">
                    deciso da <strong>{d.deciso_da}</strong>
                </span>
            {/if}
            <span class="small text-secondary">
                confidenza {d.confidenza}
                {#if d.calcolati !== undefined}
                    ({d.calcolati} componenti su {d.su})
                {/if}
            </span>
        </div>

        {#if d.perche}
            <p class="small mb-3"><Testo testo={d.perche} /></p>
        {/if}

        <table class="table table-sm small mb-2">
            <tbody>
                {#each d.componenti as componente (componente.nome)}
                    <tr>
                        <td class="text-uppercase numerico {CLASSE[componente.banda] ?? ''}"
                            style="width: 8rem">{componente.banda}</td>
                        <td style="width: 14rem"><Testo testo={componente.nome} /></td>
                        <td class="text-secondary"><Testo testo={componente.perche} /></td>
                        <td class="numerico text-secondary" style="width: 5rem">
                            {percento(componente.misura) ?? ""}
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>

        <p class="small text-secondary mb-0">
            <Testo testo="La banda complessiva e' il PEGGIORE dei componenti, non la media: un rischio alto non si annulla con quattro bassi. Quello che non si e' potuto calcolare non abbassa il rischio, abbassa la confidenza." />
            <Testo testo={d.natura} />
        </p>
    {/snippet}
</Riquadro>
