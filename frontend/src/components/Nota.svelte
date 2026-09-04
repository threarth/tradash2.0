<!--
    Nota.svelte — una nota in testo libero, col suo tetto sempre in vista.
    feat (Blocco 4): il perche' di un titolo, e cosa lo distingue.

    Le note nella scheda sono due e si comportano allo stesso modo: stesso
    controllo, stesso conteggio, stesso tetto. Sono un componente solo perche'
    due caselle che devono restare uguali e stanno in due punti diversi del
    file, prima o poi uguali non restano.

    Il conteggio si mostra **sempre**, non solo quando si sfora: il backend un
    testo troppo lungo lo rifiuta invece di tagliarlo — un taglio silenzioso fa
    credere di aver salvato tutto — e chi scrive deve poter vedere quanto
    spazio gli resta mentre lo sta usando, non dopo aver premuto Salva.
-->
<script>
    let { id, etichetta, segnaposto = "", massimo, valore = $bindable("") } = $props();

    // Si conta il testo ripulito perche' e' quello che viene salvato: gli spazi
    // in fondo li toglie chi salva, e contarli qui direbbe un numero diverso da
    // quello su cui decide il backend.
    const lunghezza = $derived(valore.trim().length);
</script>

<label class="form-label small" for={id}>{etichetta}</label>
<textarea {id} class="form-control form-control-sm" rows="3"
          placeholder={segnaposto} bind:value={valore}></textarea>
<div class="form-text small" class:text-danger={lunghezza > massimo}>
    {lunghezza} / {massimo} caratteri
</div>
