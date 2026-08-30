/**
 * router.js — le pagine, senza SvelteKit e senza dipendenze.
 * feat (Blocco 4): trenta righe al posto di un secondo servizio.
 *
 * SvelteKit porterebbe il suo router, ma anche un processo Node accanto a
 * Flask: contro la regola 1. Qui il percorso e' uno stato osservabile, i link
 * interni vengono intercettati e il tasto "indietro" del browser funziona.
 */
import { readable } from "svelte/store";

/** Il percorso corrente, aggiornato dalla navigazione e dal tasto indietro. */
export const percorso = readable(location.pathname, (imposta) => {
    const aggiorna = () => imposta(location.pathname);
    window.addEventListener("popstate", aggiorna);
    window.addEventListener("tradash:navigato", aggiorna);
    return () => {
        window.removeEventListener("popstate", aggiorna);
        window.removeEventListener("tradash:navigato", aggiorna);
    };
});

/** Va a una pagina senza ricaricare il documento. */
export function naviga(destinazione) {
    if (destinazione === location.pathname) return;
    history.pushState({}, "", destinazione);
    window.dispatchEvent(new CustomEvent("tradash:navigato"));
}

/**
 * Intercetta i click sui link interni.
 * Lascia passare tutto il resto — link esterni, tasto centrale, ctrl+click —
 * perche' un router che rompe l'apertura in una scheda nuova e' un router che
 * si mette in mezzo.
 */
export function intercettaClick(evento) {
    const link = evento.target.closest("a");
    if (!link || evento.defaultPrevented) return;
    if (evento.button !== 0 || evento.metaKey || evento.ctrlKey || evento.shiftKey) return;
    if (link.target === "_blank" || link.hasAttribute("download")) return;

    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin) return;

    evento.preventDefault();
    naviga(url.pathname);
}
