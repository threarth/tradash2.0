<!--
    Sezione.svelte — una sezione della pagina: si richiude, e si sa dove sta.
    feat: le card lunghe non devono costringere a scorrerle per arrivare dopo.

    Fa due cose insieme perche' sono la stessa cosa vista da due lati: la
    sezione **si annuncia** all'elenco condiviso (e il navigatore laterale la
    mostra) e **si puo' chiudere** (e la pagina si accorcia). Tenerle separate
    vorrebbe dire mantenere due elenchi che devono combaciare.

    Chi si apre e chi resta chiuso: le sezioni lunghe e di consultazione — i
    depositi SEC, le notizie — partono chiuse, perche' altrimenti spingono in
    fondo alla pagina tutto quello che viene dopo. Le altre partono aperte.

    Lo stato di apertura si ricorda nel browser: chi chiude i depositi SEC li
    vuole chiusi anche domani, e riaprirli a ogni visita e' una piccola noia
    ripetuta molte volte.
-->
<script>
    import Testo from "./Testo.svelte";
    import { sezioni } from "../lib/sezioni.svelte.js";

    let { id, titolo, descrizione = null, aperta = true, children } = $props();

    const CHIAVE = "tradash-sezioni";

    /** Le sezioni che l'utente ha chiuso, ricordate fra una visita e l'altra. */
    function chiuse() {
        try {
            return new Set(JSON.parse(localStorage.getItem(CHIAVE) ?? "[]"));
        } catch {
            return new Set();
        }
    }

    function ricorda(chiusa) {
        try {
            const elenco = chiuse();
            if (chiusa) elenco.add(id);
            else elenco.delete(id);
            localStorage.setItem(CHIAVE, JSON.stringify([...elenco]));
        } catch {
            // Un browser che non lascia scrivere non deve rompere la pagina:
            // si perde solo il ricordo, non la sezione.
        }
    }

    let apertaOra = $state(chiuse().has(id) ? false : aperta);

    function cambia() {
        apertaOra = !apertaOra;
        ricorda(!apertaOra);
    }

    // La sezione si annuncia al navigatore quando compare, e si toglie quando
    // sparisce: cosi' l'indice non nomina mai una sezione che non c'e'.
    $effect(() => sezioni.registra(id, titolo));

    // Quale sezione si sta guardando: la piu' alta fra quelle visibili.
    $effect(() => {
        const elemento = document.getElementById(id);
        if (!elemento || typeof IntersectionObserver === "undefined") return;

        const osservatore = new IntersectionObserver(
            (voci) => voci.forEach((v) => v.isIntersecting && sezioni.guarda(id)),
            { rootMargin: "-20% 0px -70% 0px" }
        );
        osservatore.observe(elemento);
        return () => osservatore.disconnect();
    });
</script>

<section {id} class="mb-4">
    <div class="d-flex justify-content-between align-items-start gap-2">
        <div>
            <h2 class="h6 mb-1">
                <button class="btn btn-link p-0 text-reset text-decoration-none fw-semibold"
                        onclick={cambia} aria-expanded={apertaOra} aria-controls={`${id}-corpo`}>
                    <span class="text-secondary me-1">{apertaOra ? "▾" : "▸"}</span>
                    <Testo testo={titolo} />
                </button>
            </h2>
            {#if descrizione && apertaOra}
                <p class="small text-secondary mb-2"><Testo testo={descrizione} /></p>
            {/if}
        </div>
    </div>

    <div id={`${id}-corpo`} hidden={!apertaOra}>
        {@render children?.()}
    </div>

    {#if !apertaOra}
        <p class="small text-secondary mb-0">chiusa — premi il titolo per aprirla</p>
    {/if}
</section>
