/**
 * tema.js — chiaro o scuro, ricordato fra una visita e l'altra.
 * feat (Blocco 4): `data-bs-theme` di Bootstrap 5.3 piu' localStorage.
 *
 * Niente `next-themes` e niente altra dipendenza: Bootstrap legge un attributo
 * sull'elemento radice, e ricordarselo sono quattro righe.
 *
 * Il tema iniziale viene applicato in `index.html`, prima che la pagina sia
 * disegnata: farlo qui, a componente montato, farebbe lampeggiare il chiaro
 * sullo scuro a ogni caricamento.
 */
const CHIAVE = "tradash-tema";
export const CHIARO = "light";
export const SCURO = "dark";

/** Il tema attivo adesso, letto dal documento (che e' la verita' a video). */
export function temaAttuale() {
    return document.documentElement.getAttribute("data-bs-theme") === CHIARO ? CHIARO : SCURO;
}

/**
 * Applica un tema e prova a ricordarlo.
 * Se `localStorage` e' negato il tema si applica lo stesso: non ricordarlo e'
 * un fastidio, non mostrarlo sarebbe un guasto.
 */
export function applicaTema(tema) {
    document.documentElement.setAttribute("data-bs-theme", tema);
    try {
        localStorage.setItem(CHIAVE, tema);
    } catch {
        // Finestra privata o permessi negati: si continua senza ricordare.
    }
    return tema;
}

/** Passa da chiaro a scuro e viceversa. Ritorna il tema nuovo. */
export function alternaTema() {
    return applicaTema(temaAttuale() === SCURO ? CHIARO : SCURO);
}
