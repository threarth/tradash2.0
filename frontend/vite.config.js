/**
 * vite.config.js — come si costruisce la SPA e come si parla col backend.
 * feat (Blocco 4): build in `dist/`, che Flask serve come statici.
 *
 * In sviluppo girano due processi: Vite qui e Flask sulla sua porta. Il proxy
 * manda `/api` a Flask, cosi' il codice del frontend chiama sempre percorsi
 * relativi e non deve sapere dove sta il backend — ne' adesso ne' in uso reale,
 * dove i due coincidono perche' Flask serve anche il build.
 */
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

// La porta del server Flask di sviluppo, la stessa dichiarata in backend/config.py.
const PORTA_BACKEND = 5001;

// La porta del server di sviluppo di Vite.
const PORTA_SVILUPPO = 5173;

export default defineConfig({
    plugins: [svelte()],
    server: {
        port: PORTA_SVILUPPO,
        proxy: {
            "/api": {
                target: `http://127.0.0.1:${PORTA_BACKEND}`,
                changeOrigin: false
            }
        }
    },
    build: {
        outDir: "dist",
        emptyOutDir: true
    }
});
