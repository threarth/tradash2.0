/**
 * rilevatore.test.js — il riconoscimento dei termini, verificato.
 * feat (Blocco 5): regola 24, la logica non banale ha il suo test.
 *
 * Il rilevatore e' il pezzo che si porta dietro piu' trappole: parole dentro
 * altre parole, sigle di due lettere, frasi che ne contengono di piu' corte,
 * espressioni regolari con stato. Ognuna qui ha il suo caso.
 */
import { describe, expect, it } from "vitest";

import { costruisciIndice, costruisciSchema, segmenta } from "./rilevatore.js";

const TERMINI = [
    { id: "rs", label: "Relative Strength (RS)", short: "forza relativa" },
    { id: "fcf", label: "Free Cash Flow (FCF)", short: "flusso di cassa libero" },
    { id: "cash", label: "Cash", short: "cassa" },
    { id: "volume-anomaly", label: "Volume Anomaly (Anomalia di Volume)", short: "anomalia" }
];

function prepara(termini = TERMINI) {
    const indice = costruisciIndice(termini);
    return { indice, schema: costruisciSchema([...indice.keys()]) };
}

describe("costruisciIndice", () => {
    it("ricava tre forme da un'etichetta con la sigla", () => {
        const indice = costruisciIndice([TERMINI[0]]);
        expect([...indice.keys()].sort()).toEqual(
            ["relative strength", "relative strength (rs)", "rs"]
        );
    });

    it("non prende come sigla una traduzione fra parentesi", () => {
        const indice = costruisciIndice([TERMINI[3]]);
        expect(indice.has("anomalia di volume")).toBe(false);
        expect(indice.has("volume anomaly")).toBe(true);
    });

    it("scarta le parole troppo corte, che aggancerebbero mezzo testo", () => {
        const indice = costruisciIndice([{ id: "p", label: "P" }]);
        expect(indice.size).toBe(0);
    });

    it("chi arriva prima tiene la parola", () => {
        const indice = costruisciIndice([
            { id: "primo", label: "Cash" },
            { id: "secondo", label: "Cash" }
        ]);
        expect(indice.get("cash")).toBe("primo");
    });
});

describe("segmenta", () => {
    it("riconosce un termine e lascia intatto il resto", () => {
        const { indice, schema } = prepara();
        const pezzi = segmenta("Guarda il Cash di questa societa'.", indice, schema);

        expect(pezzi.map((p) => p.testo)).toEqual(["Guarda il ", "Cash", " di questa societa'."]);
        expect(pezzi[1].id).toBe("cash");
        expect(pezzi[0].id).toBeUndefined();
    });

    it("le frasi lunghe vincono sulle parole corte che contengono", () => {
        const { indice, schema } = prepara();
        const pezzi = segmenta("Il Free Cash Flow cresce", indice, schema);

        const riconosciuti = pezzi.filter((p) => p.id);
        expect(riconosciuti).toHaveLength(1);
        expect(riconosciuti[0].testo).toBe("Free Cash Flow");
        expect(riconosciuti[0].id).toBe("fcf");
    });

    it("non aggancia una sigla dentro un'altra parola", () => {
        const { indice, schema } = prepara();
        expect(segmenta("La sonda MARS e' partita", indice, schema)).toBeNull();
    });

    it("riconosce a prescindere da maiuscole e minuscole", () => {
        const { indice, schema } = prepara();
        const pezzi = segmenta("il free cash flow", indice, schema);
        expect(pezzi.find((p) => p.id)?.id).toBe("fcf");
    });

    it("non salta pezzi alla seconda chiamata", () => {
        // Il difetto che questo caso chiude: `lastIndex` di un'espressione con
        // il flag globale e' stato mutabile. Riusando lo stesso oggetto fra due
        // chiamate, la seconda riparte da meta' testo e perde i termini prima.
        const { indice, schema } = prepara();
        const primo = segmenta("Cash oggi", indice, schema);
        const secondo = segmenta("Cash oggi", indice, schema);
        expect(secondo).toEqual(primo);
    });

    it("ritorna null quando non c'e' niente da sottolineare", () => {
        const { indice, schema } = prepara();
        expect(segmenta("una frase qualunque", indice, schema)).toBeNull();
        expect(segmenta("", indice, schema)).toBeNull();
    });

    it("regge un indice vuoto senza inventarsi uno schema", () => {
        expect(costruisciSchema([])).toBeNull();
        expect(segmenta("Cash", new Map(), null)).toBeNull();
    });
});
