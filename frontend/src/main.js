/**
 * main.js — l'avvio dell'applicazione.
 * feat (Blocco 4): monta e basta, nessun lavoro che parte da solo.
 */
import { mount } from "svelte";

import App from "./App.svelte";
import "./styles/app.css";

export default mount(App, { target: document.getElementById("app") });
