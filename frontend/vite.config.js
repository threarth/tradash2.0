/**
 * vite.config.js — come si costruisce la SPA e come si parla col backend.
 * feat (Blocco 4): build in `dist/`, che Flask serve come statici.
 *
 * In sviluppo girano due processi: Vite qui e Flask sulla sua porta. Il proxy
 * manda `/api` a Flask, cosi' il codice del frontend chiama sempre percorsi
 * relativi e non deve sapere dove sta il backend — ne' adesso ne' in uso reale,
 * dove i due coincidono perche' Flask serve anche il build.
 *
 * ## La porta, e perche' non e' quella predefinita
 *
 * Era la 5173, cioe' quella che Vite usa dappertutto: sulla stessa macchina c'e'
 * un altro progetto che ce l'ha gia', e Vite in quel caso **si sposta in
 * silenzio** su 5174 scrivendolo in una riga del log. Chi apre 5173 come al
 * solito trova l'altro progetto e conclude che `npm run dev` non funziona.
 *
 * Adesso la porta e' una sola, ricavata da quella del backend — 5001 -> 5101 —
 * e `strictPort` dice a Vite di fermarsi con un errore invece di cercarne
 * un'altra: una porta diversa da quella attesa e' un guasto da dichiarare, non
 * un problema da aggirare da soli.
 */
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

// La porta del server Flask di sviluppo, la stessa dichiarata in backend/config.py.
const PORTA_BACKEND = 5001;

// La porta del server di sviluppo. Non la 5173 predefinita: e' occupata da un
// altro progetto su questa macchina, e due progetti che si contendono la stessa
// porta sono due progetti in cui uno dei due apre la pagina sbagliata.
const PORTA_SVILUPPO = 5101;

export default defineConfig({
    plugins: [svelte()],
    server: {
        port: PORTA_SVILUPPO,
        // Se la porta e' occupata, si ferma e lo dice. Spostarsi da soli
        // significa servire la pagina a un indirizzo che nessuno guardera'.
        strictPort: true,
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
