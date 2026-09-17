/**
 * lineaVerticale.js — una riga verticale sul grafico, al punto fissato.
 * feat: il ctrl+click si vede, invece di lasciare solo una freccetta.
 *
 * ## Perche' serve una «primitive» e non un div sopra il grafico
 *
 * Un elemento HTML posizionato a mano andrebbe rimesso a posto a ogni scorrimento,
 * a ogni zoom e a ogni ridimensionamento — cioe' a ogni fotogramma di un
 * trascinamento — e resterebbe comunque mezzo passo indietro rispetto alla tela.
 * Una primitive disegna DENTRO il ciclo di disegno della libreria: si ridisegna
 * quando si ridisegna il grafico, ed e' allineata al pixel per costruzione.
 *
 * `lightweight-charts` la prevede: `series.attachPrimitive(...)`.
 *
 * ## Si disegna in spazio MEDIA, non bitmap
 *
 * `timeScale().timeToCoordinate()` risponde in pixel CSS. Disegnare in spazio
 * bitmap vorrebbe dire moltiplicare a mano per il rapporto dei pixel, e
 * sbagliarlo su uno schermo Retina sposterebbe la riga di meta' larghezza senza
 * che si veda su un monitor normale.
 */

// Quanto e' spessa e come e' fatta. Piena e spessa due: una riga tratteggiata e
// sottile, su un grafico a candele, si confonde con la griglia — ed e' proprio
// cio' che questa riga NON deve fare.
const SPESSORE_PX = 2;

// Il cappuccio in cima, che rende la riga riconoscibile a colpo d'occhio anche
// quando cade in mezzo a una zona fitta di candele.
const CAPPUCCIO_ALTEZZA_PX = 6;
const CAPPUCCIO_LARGHEZZA_PX = 10;

/**
 * Crea la primitive. Ritorna l'oggetto da passare a `attachPrimitive`, con in
 * piu' `muovi(tempo)` per spostarla senza ricostruire il grafico.
 *
 * @param {() => string} colore  letto a ogni disegno, non catturato: il tema
 *                               puo' cambiare mentre il grafico e' vivo.
 */
export function creaLineaVerticale(colore) {
    let tempo = null;
    let grafico = null;
    let chiediAggiornamento = () => {};

    const disegna = (target) => {
        const x = grafico?.timeScale().timeToCoordinate(tempo);
        // `null` quando il punto fissato e' fuori dalla finestra visibile:
        // non si disegna niente, invece di appiccicare la riga al bordo.
        if (x === null || x === undefined) return;

        target.useMediaCoordinateSpace(({ context, mediaSize }) => {
            context.save();
            context.strokeStyle = colore();
            context.fillStyle = colore();
            context.lineWidth = SPESSORE_PX;

            context.beginPath();
            context.moveTo(x, 0);
            context.lineTo(x, mediaSize.height);
            context.stroke();

            context.fillRect(x - CAPPUCCIO_LARGHEZZA_PX / 2, 0,
                             CAPPUCCIO_LARGHEZZA_PX, CAPPUCCIO_ALTEZZA_PX);
            context.restore();
        });
    };

    // La vista e il suo contenitore si tengono fermi: la libreria mette in
    // cache sul riferimento dell'array, e restituirne uno nuovo a ogni giro
    // vanificherebbe la cache.
    const vista = {
        zOrder: () => "top",
        renderer: () => (tempo === null || grafico === null ? null : { draw: disegna })
    };
    const viste = [vista];

    return {
        attached({ chart, requestUpdate }) {
            grafico = chart;
            chiediAggiornamento = requestUpdate;
        },
        detached() {
            grafico = null;
            chiediAggiornamento = () => {};
        },
        paneViews: () => viste,

        /** Sposta la riga, o la toglie con `null`. */
        muovi(nuovo) {
            tempo = nuovo;
            chiediAggiornamento();
        }
    };
}
