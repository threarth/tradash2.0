# Backlog

Cosa resta, al 06/09/2026. Sta in un file e non in una chat perche' una
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

## 2. I pesi del rilevatore spin-off vengono da un caso solo

I sei segnali e i loro pesi — volume 25, margine 20, ricavi 20, EPS 15, e i due
di prezzo a 10 — sono stati ricavati misurando **quando** ogni segnale e'
diventato visibile su SanDisk. Un caso. Un modello tarato su SanDisk che
descrive benissimo SanDisk non ha dimostrato niente, e si chiama
sovradattamento.

**Cosa fare, e costa poco perche' i dati ci sono gia':** rigiocare il punteggio a
ogni fine mese su tutti gli spin-off dell'elenco — 27 titoli, un paio d'anni di
mesi — e confrontarlo col rendimento dei sei mesi successivi. Non sara'
statistica: saranno venti o trenta casi. Ma e' la differenza fra pesi misurati e
pesi inventati, e oggi sono inventati con un aneddoto forte alle spalle.

Serve anche a rispondere alla domanda vera: **il punteggio anticipa qualcosa, o
descrive solo cio' che e' gia' successo?** Su SanDisk anticipava — 75 punti a
settembre 2025, con ancora tredici volte il capitale davanti — ma su un caso
solo anche questo e' un aneddoto.

---

## 3. Il taglio point-in-time del rilevatore e' stimato, non reale

`domain/spinoff_segnali.py` decide quali trimestri erano gia' pubblici con un
**ritardo fisso di 45 giorni** dalla fine del periodo. Il sistema pero' ha di
meglio: `domain/publication_dates.py` con le date di deposito VERE, che l'elenco
dei filing di Defeatbeta porta.

Non e' un dettaglio da pignoli: `DECISIONI.md` dice gia' che «il point-in-time ha
due tagli, e sono diversi», e un risultato costruito sul ritardo stimato e uno
costruito sulle date reali **non sono confrontabili**. Il giorno che si rigioca
il punteggio all'indietro (voce 2), la differenza fra i due tagli entra dritta
nel risultato.

**Cosa fare:** passare a `trimestri_utili()` i periodi gia' filtrati da chi ha le
date vere, che e' la forma per cui la funzione e' scritta — il ripiego a 45
giorni resta per i titoli di cui non si hanno i depositi, dichiarandolo.

---

## 4. Il punteggio di successo, tarato

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

## 5. Le analisi non sono state rigirate dopo il cambio dei prompt

Il 02/09 la regola sui consigli e' cambiata — da «non darne» a «dalli in tre
tempi, con la banda di rischio». Da allora e' stata rigirata **solo la lettura
tecnica, su KO**.

**Cosa fare:** rigirare fondamentale, earnings, forward e verdetto su un titolo,
e la qualitativa (che i consigli non li da', ma i cui prompt sono cambiati per
il controllo sui segnaposti). Costo stimato sulla base di quanto e' costato la
prima volta: circa 2 dollari.

---

## 6. Nessun test del frontend prende un difetto di reattivita'

In due giorni ne sono passati quattro: `structuredClone` su un proxy, il ciclo
infinito del registro delle sezioni, il punto fissato che ricostruiva il
grafico, e l'effetto di `SchedaTitolo` che converge solo per una guardia.

Adesso ce ne sono altri tre, tutti di genere nuovo e tutti senza rete di
protezione:

* **l'effetto di `Cinema.svelte` governa un `setInterval`**, e regge su una
  proprieta' che nessun test verifica — che le letture dentro allo scatto
  avvengano fuori dal giro di tracciamento, e quindi non siano dipendenze. Se lo
  diventassero, il timer si ricreerebbe a ogni fotogramma e la velocita' non
  sarebbe piu' quella chiesta: non e' un errore che si vede, e' un film che
  scorre storto;
* **`Ticker.svelte` calcola una posizione `fixed` leggendo il DOM** al momento
  dell'apertura. Nessun test puo' dire se la cartellina finisce dove deve,
  perche' sotto vitest il DOM non ha una geometria;
* **`Spinoff.svelte` aspetta la fine di un lavoro con un `setInterval`** che
  interroga `/api/ops/active`. Se il lavoro finisse fra due battiti senza mai
  comparire, quell'attesa non finirebbe mai.

**Il test giusto non si e' potuto scrivere:** vitest carica `svelte` nella build
da server, dove `$effect` esiste e non esegue niente — un test cosi' passa senza
aver provato nulla. Provate due condizioni di risoluzione diverse, nessuna lo fa
girare. Al suo posto c'e' un test che legge il sorgente e verifica la difesa.

**Cosa fare:** o si trova la configurazione che fa girare gli effetti sotto
vitest (jsdom + condizioni browser, da provare), oppure si accetta e si estende
il controllo sul sorgente a tutti i componenti — oggi copre solo
`sezioni.svelte.js`.

---

## 7. Quello che non e' mai stato visto girare

Su questa macchina **non c'e' un browser headless** — niente playwright, niente
chromium — quindi ogni correzione di interfaccia degli ultimi giorni e'
ragionata, non vista. Il codice c'e', i test passano, il build compila; il
giudizio a occhio manca.

Cosa aspetta uno sguardo, in ordine di quanto e' probabile che sia storto:

* **il cinema del simulatore.** Se a 120 sedute al secondo la linea scatta, se
  il cursore trascinato mentre e' in movimento fa quello che sembra, se la scala
  che si ricalcola a ogni fotogramma da' l'effetto voluto o fa solo ballare il
  disegno. *Cosa fare:* un titolo con una storia brutta — salita, crollo,
  risalita — e premere play;
* **il pannello dei lavori e la scia, durante un'analisi vera.** Le righe
  «chiedo a gpt-5.5» e «ha risposto: N token» non sono mai state viste arrivare:
  costano soldi, e la prima analisi che lanci e' anche la loro verifica;
* **l'anteprima al passaggio sul ticker**, corretta due volte a occhio chiuso —
  prima veniva tagliata dal bordo della tabella, poi restava lontana dal
  simbolo;
* **le due caselle delle note in watchlist**, provate solo dai test;
* **il tema chiaro.** Quello scuro e' stato rifatto cinque volte e misurato ogni
  volta; il chiaro e' rimasto quello di prima. I suoi accenti misurano fra 5,1 e
  6,4 — accettabili — ma nessuno l'ha guardato dopo il cambio del corpo del
  testo a 15px e dopo che il tema scuro ha cambiato famiglia.

---

## 8. Cose piccole, se capita

- **`before` su `get_recent_filings`** (dal PIANO): qui il taglio dei filing e'
  esatto e usato. Resta come lezione — un parametro esposto e mai passato e' un
  controllo che sembra esserci — non come lavoro da fare.
- **`point_in_time_service`, `capm`, `technical_features`, `feature_engine`** del
  vecchio sistema: mai portati. Il PIANO diceva «vanno col Blocco 8». Oggi il
  Blocco 8 c'e', e sono probabilmente **superati**: il WACC arriva dal DCF di
  Defeatbeta, gli indicatori dal motore a nodi, le misure dello scanner da
  `domain/scansione.py`, e il confronto point-in-time e' fatto. Prima di
  portarli, verificare se serve ancora qualcosa.
- **Il prompt di revisione non vede il perche'**. Adesso che le note esistono,
  chi rivede la watchlist con occhi freschi potrebbe leggerle: giudicherebbe se
  la classificazione regge *e* se il motivo scritto sei mesi fa vale ancora. Non
  fatto perche' non era la richiesta, e perche' allunga un prompt che oggi e'
  volutamente magro.
- **GLIBR non ha prezzi in Defeatbeta**: e' l'unico dei 27 spin-off che il
  rilevatore non puo' misurare affatto. Dichiarato nella riga («senza dati»), da
  ricontrollare quando l'universo si ricostruisce — potrebbe essere un simbolo
  che il dataset non ha mai avuto, o uno arrivato dopo l'ultima costruzione.
- **Il tetto delle citazioni**: se ne chiedono 24 e ne sono arrivate 25. Il
  tetto e' una richiesta nel prompt, non un limite del codice. Si dichiarano
  entrambe le cifre; troncare la venticinquesima nasconderebbe che il modello
  non ha rispettato il tetto.

---

## Quello che NON e' nel backlog, e perche'

- **Un secondo fornitore di dati.** Scelta dell'utente: fonte unica Defeatbeta.
- **Chiamate a sec.gov.** Il sistema dice quali documenti servono e dove
  salvarli; a sec.gov non chiede niente. Verificato in ricognizione il 01/09.
- **Automatismi verso l'esterno.** Niente parte da solo: i tre thread che
  esistono — universo, scanner, segnali degli spin-off — partono da una POST e
  stanno nel registro dei lavori. L'unico fetch verso un sito esterno, l'elenco
  degli spin-off da stockanalysis, parte anche lui solo da un pulsante.
- **Aggiustare i colori a mano.** Cinque palette hanno insegnato che non
  funziona: adesso i grigi sono la scala `stone` di Tailwind e l'accento e'
  l'arancio di Claude, e ogni gradino e' un valore ufficiale. Se un colore non
  va, si cambia gradino o si cambia palette — non si mescola.
