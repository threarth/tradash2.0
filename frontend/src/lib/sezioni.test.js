/**
 * sezioni.svelte.test.js — l'elenco delle sezioni non deve avvitarsi su se stesso.
 *
 * Il difetto che questo file esiste per impedire: registrarsi vuol dire leggere
 * l'elenco e riscriverlo, e la registrazione avviene dentro un effetto del
 * componente. Senza precauzioni quella lettura diventa una dipendenza — si
 * scrive, l'effetto riparte, si riscrive — e con dieci sezioni Svelte si arrende
 * con `effect_update_depth_exceeded`, dopo aver bruciato CPU a vuoto.
 *
 * A schermo si vedeva solo «la pagina e' lentissima»: il ciclo non si annuncia,
 * si sente.
 */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it } from "vitest";

import { sezioni } from "./sezioni.svelte.js";

const leggiSorgente = () =>
    readFile(fileURLToPath(new URL("./sezioni.svelte.js", import.meta.url)), "utf8");

beforeEach(() => sezioni.azzera());

describe("l'elenco delle sezioni", () => {
    it("tiene le sezioni nell'ordine in cui si registrano", () => {
        sezioni.registra("prezzo", "Prezzo");
        sezioni.registra("salute", "Salute");

        expect(sezioni.elenco.map((s) => s.id)).toEqual(["prezzo", "salute"]);
    });

    it("toglie la sezione quando sparisce", () => {
        const togli = sezioni.registra("prezzo", "Prezzo");
        sezioni.registra("salute", "Salute");

        togli();

        expect(sezioni.elenco.map((s) => s.id)).toEqual(["salute"]);
    });

    it("registrare due volte lo stesso id non lo duplica", () => {
        sezioni.registra("prezzo", "Prezzo");
        sezioni.registra("prezzo", "Prezzo, rinominato");

        expect(sezioni.elenco).toHaveLength(1);
        expect(sezioni.elenco[0].titolo).toBe("Prezzo, rinominato");
    });

    // --- la difesa contro il ciclo, verificata sul sorgente -----------------
    //
    // Il test che sarebbe giusto — dieci sezioni che si registrano dentro dieci
    // effetti, e contare quante volte girano — **non si puo' scrivere qui**:
    // vitest carica `svelte` nella sua build da server, dove `$effect` esiste
    // ma non esegue nulla. Un test cosi' passerebbe senza aver provato niente,
    // che e' il modo peggiore di avere un test. Provato: due condizioni di
    // risoluzione diverse, nessuna delle due lo fa girare.
    //
    // Allora si verifica la DIFESA invece del comportamento, e lo si dice.
    // E' la stessa scelta che il backend fa per i rami `if TESTING`: si legge
    // il sorgente. Non dimostra che il ciclo non c'e'; dimostra che chi lo
    // impediva e' ancora al suo posto.

    it("legge l'elenco senza tracciarlo, o il ciclo torna", async () => {
        const sorgente = await leggiSorgente();

        expect(sorgente).toContain("import { untrack }");
        // Ogni lettura di `this.elenco` e di `this.attiva` dentro i metodi che
        // poi li riscrivono deve passare da untrack.
        const letture = sorgente.match(/this\.(elenco|attiva)(?![\s]*=)/g) ?? [];
        const dentroUntrack = sorgente.match(/untrack\(\(\) => this\.(elenco|attiva)/g) ?? [];
        expect(letture.length).toBeGreaterThan(0);
        expect(dentroUntrack.length).toBe(letture.length);
    });
});
