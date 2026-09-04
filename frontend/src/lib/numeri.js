/**
 * numeri.js — le due forme in cui si scrivono i numeri di una posizione.
 * feat: una percentuale col segno, e una cifra in dollari.
 *
 * Stanno qui e non dentro a un componente perche' il riassunto, la tabella e il
 * film raccontano gli stessi giorni: se una delle tre arrotondasse in modo
 * diverso, la stessa giornata comparirebbe con due numeri diversi nella stessa
 * schermata.
 *
 * I dollari sono dollari e basta: non abbiamo una fonte per i cambi, quindi
 * l'effetto valuta qui non c'e' e non viene stimato — e' scritto anche nella
 * pagina, perche' un numero senza valuta si legge nella propria.
 */

/** Una frazione come percentuale, col segno davanti. `null` diventa un trattino. */
export function percento(frazione, cifre = 1) {
    if (frazione === null || frazione === undefined) return "—";
    return `${frazione >= 0 ? "+" : ""}${(frazione * 100).toFixed(cifre)}%`;
}

/** Una cifra in dollari, senza centesimi: qui i centesimi non decidono niente. */
export function soldi(valore) {
    if (valore === null || valore === undefined) return "—";
    return `$${Number(valore).toLocaleString("it", { maximumFractionDigits: 0 })}`;
}
