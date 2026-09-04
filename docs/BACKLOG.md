# Backlog

Cosa resta, al 04/09/2026. Sta in un file e non in una chat perche' una
conversazione si azzera e questo elenco no.

L'ordine e' per valore, non per fatica. Ogni voce dice **perche'** vale, cosi'
fra un mese si puo' decidere di buttarla senza doverla ricostruire.

---

## 1. I token letti dalla cache — il costo che mostriamo puo' essere una sovrastima

Il vecchio tradash registrava `cache_read_tokens` e `cache_write_tokens`. Noi no.
Se il fornitore serve parte dell'ingresso dalla cache, la fattura e' piu' bassa
del nostro conto, che li paga tutti a prezzo pieno.

Misurato su una chiamata da 1.221 token: **la cache non si attiva**. Sulle fasi
qualitative, da 44.000 token, potrebbe.

**Perche' e' diventato fattibile:** serviva una colonna nuova in `llm_calls`,
quindi un rebuild, quindi perdere i referti pagati. Adesso i referti stanno in
un file e `manage.py referti` li rimette: il rebuild non costa piu' niente.

**Cosa fare:** due colonne in `llm_calls`, il campo letto da
`usage.input_tokens_details.cached_tokens` (OpenAI) e dall'equivalente
Anthropic, e il costo che ne tiene conto. Poi `manage.py costi` ricalcola.

---

## 2. Il punteggio di successo, tarato

Deciso il 02/09: **prima il rischio, il successo dopo averlo tarato.** Il rischio
c'e' ed e' deterministico. Il successo no, e oggi non si puo' fare onestamente:
non abbiamo un solo esito storico delle nostre analisi.

**Il substrato adesso c'e':** i referti stanno in un file append-only e non si
perdono piu', e `domain/ricostruzione.py` sa gia' dire cosa e' successo dopo una
certa data. Manca il giro che li mette insieme.

**Cosa fare:** per ogni referto conservato, ricostruire le misure alla sua data e
misurare cosa e' successo dopo (30/90/180/365 giorni). Quando i casi sono
abbastanza, un punteggio di successo nasce **calibrato** invece che inventato.
Finche' non lo e', non si mostra: sarebbe il terzo verdetto sintetico che questo
progetto ha gia' tolto due volte.

---

## 3. Le analisi non sono state rigirate dopo il cambio dei prompt

Il 02/09 la regola sui consigli e' cambiata — da «non darne» a «dalli in tre
tempi, con la banda di rischio». Da allora e' stata rigirata **solo la lettura
tecnica, su KO**.

**Cosa fare:** rigirare fondamentale, earnings, forward e verdetto su un titolo,
e la qualitativa (che i consigli non li da', ma i cui prompt sono cambiati per
il controllo sui segnaposti). Costo stimato sulla base di quanto e' costato la
prima volta: circa 2 dollari.

---

## 4. Nessun test del frontend prende un difetto di reattivita'

In due giorni ne sono passati quattro: `structuredClone` su un proxy, il ciclo
infinito del registro delle sezioni, il punto fissato che ricostruiva il
grafico, e l'effetto di `SchedaTitolo` che converge solo per una guardia.

**Il test giusto non si e' potuto scrivere:** vitest carica `svelte` nella build
da server, dove `$effect` esiste e non esegue niente — un test cosi' passa senza
aver provato nulla. Provate due condizioni di risoluzione diverse, nessuna lo fa
girare. Al suo posto c'e' un test che legge il sorgente e verifica la difesa.

**Cosa fare:** o si trova la configurazione che fa girare gli effetti sotto
vitest (jsdom + condizioni browser, da provare), oppure si accetta e si estende
il controllo sul sorgente a tutti i componenti — oggi copre solo
`sezioni.svelte.js`.

---

## 5. Cose piccole, se capita

- **`before` su `get_recent_filings`** (dal PIANO): qui il taglio dei filing e'
  esatto e usato. Resta come lezione — un parametro esposto e mai passato e' un
  controllo che sembra esserci — non come lavoro da fare.
- **`point_in_time_service`, `capm`, `technical_features`, `feature_engine`** del
  vecchio sistema: mai portati. Il PIANO diceva «vanno col Blocco 8». Oggi il
  Blocco 8 c'e', e sono probabilmente **superati**: il WACC arriva dal DCF di
  Defeatbeta, gli indicatori dal motore a nodi, le misure dello scanner da
  `domain/scansione.py`, e il confronto point-in-time e' fatto. Prima di
  portarli, verificare se serve ancora qualcosa.
- **Il tetto delle citazioni**: se ne chiedono 24 e ne sono arrivate 25. Il
  tetto e' una richiesta nel prompt, non un limite del codice. Si dichiarano
  entrambe le cifre; troncare la venticinquesima nasconderebbe che il modello
  non ha rispettato il tetto.

---

## Quello che NON e' nel backlog, e perche'

- **Un secondo fornitore di dati.** Scelta dell'utente: fonte unica Defeatbeta.
- **Chiamate a sec.gov.** Il sistema dice quali documenti servono e dove
  salvarli; a sec.gov non chiede niente. Verificato in ricognizione il 01/09.
- **Automatismi verso l'esterno.** Niente parte da solo: i due thread che
  esistono partono da una POST e stanno nel registro dei lavori.
