# Lo scanner, e come non farsi ingannare da lui

Lo scanner fa una domanda sola a tutto l'universo: **quali titoli, oggi,
soddisfano queste condizioni?** Dieci criteri, che si combinano in AND — chi non
li soddisfa tutti non compare.

Non decide niente e non ordina per bonta'. Restituisce un elenco e, accanto a
ogni titolo, **perche'** e' finito li'. La spiegazione non e' un ornamento: uno
scanner che dice solo «sette titoli» costringe a fidarsi, e «basato su cosa?» e'
la domanda che nel vecchio sistema non aveva risposta.

---

## Prima di usarlo

Due derivazioni, dalla pagina **Universo**:

| pulsante | cosa serve | quanto costa |
|---|---|---|
| **Anagrafica** e **Prezzi** | i criteri di prezzo, e i filtri per settore e dimensione | 95 MB e 445 MB la prima volta |
| **Deriva i bilanci** | i quattro criteri di bilancio | ~65 s |
| **Deriva lo storico** | il rigioco, cioe' «ha mai funzionato?» | ~8 s |

Senza i bilanci i criteri di bilancio non trovano nessuno — e non perche' nessun
titolo li soddisfi: perche' il dato manca, e **un criterio su un dato che manca
non passa**. Fingere che un valore assente valga zero e' il modo piu' rapido di
riempire uno scanner di titoli che non c'entrano niente.

---

## I dieci criteri

### Sei sul prezzo

| criterio | chiede | note |
|---|---|---|
| **Sceso almeno del** | X% sotto il massimo storico | il drawdown, in valore assoluto |
| **Sceso non piu' del** | meno di X% sotto il massimo | il filtro opposto: esclude i disastri |
| **Recuperato almeno il** | X% di risalita dal fondo | si usa insieme al primo |
| **Cresciuto in un anno** | +X% sulle ultime 252 sedute | |
| **Sopra la media a 200 sedute** | prezzo almeno X% sopra | vuole 200 sedute di storia |
| **Volume medio almeno** | N azioni al giorno, su 21 sedute | numero di azioni, non controvalore |

### Quattro sul bilancio

| criterio | chiede | trimestri gia' depositati che servono |
|---|---|---|
| **Ricavi in crescita sull'anno** | +X% sullo stesso trimestre dell'anno prima | **5** |
| **Ricavi in crescita sul trimestre** | +X% sul trimestre precedente | 2 |
| **Margine lordo in crescita** | +X punti in un trimestre | 2 |
| **EPS dell'ultimo trimestre** | almeno X | 2 |

**I due sui ricavi non sono intercambiabili, e uno dei due e' peggiore.** Il
trimestre su trimestre misura anche il calendario: un trimestre di Natale batte
quello prima quasi sempre, quindi seleziona la stagionalita' e la chiama
crescita. Misurato: a sei mesi il trimestrale perde il 3,2% contro il
non-filtrare, l'annuale guadagna il 5,2%.

Usa l'annuale. Il trimestrale resta disponibile perche' su un titolo giovane —
che cinque trimestri non li ha — e' l'unica cosa misurabile, ma sappi cosa stai
misurando.

---

## I preset

Cinque combinazioni **gia' rigiocate**, ognuna con il proprio verdetto attaccato.
Premerne una riempie il modulo; la ricerca la lanci tu.

| preset | criteri | verdetto (3 / 6 / 12 mesi) | mesi giudicabili |
|---|---|---|---|
| **Forza confermata** | sopra la media 200 +5%, un anno +20% | **+0,7% / +2,6% / +1,9%** | 75 |
| **Cresce e guadagna** | ricavi anno +15%, EPS ≥ 0 | **+1,4% / +2,7% / +4,1%** | 34 |
| **Numeri che girano** | ricavi anno +20%, margine +2 punti | −0,9% / +0,9% / **+6,6%** | 32 |
| **Buon drawdown** | sceso 30%, recuperato 15% | −0,8% / −0,9% / −0,6% | 82 |
| **Crollo e ripresa** | sceso 50%, recuperato 20% | −2,3% / −3,1% / −3,1% | 76 |

**Due su cinque perdono, e restano in elenco per questo.** Un'idea scartata che
non sta scritta da nessuna parte torna da sola fra sei mesi.

E uno ha **cambiato verdetto** dopo la correzione del metro: «Numeri che girano»
risultava perdente e adesso e' **lento** — perde a breve e vince a lungo. Non e'
cambiato il criterio: era il paragone a essere storto.

**Questi numeri non sono scritti a mano.** Li produce `python manage.py preset`,
che rigioca tutti i preset e scrive `backend/data/preset_verdetti.json` — un file
che sta in git apposta, cosi' un verdetto che cambia si vede come diff invece di
sostituirsi in silenzio a quello di prima. Il file porta con se' **la data della
misura, le soglie e la finestra di dati** usate; se una delle tre non combacia
piu' con quelle di adesso, la pagina lo dice e ti chiede di rigiocare. Non lo fa
da sola: vedi «Niente si aggiorna da solo» qui sotto.

### Il criterio piu' solido non e' un preset, ed e' sulle azioni

`azioni_variazione_massima: -0.02` — almeno il 2% di riacquisto in un anno:

| | 3 mesi | 6 mesi | 12 mesi |
|---|---|---|---|
| mesi vinti | 83% | 89% | **96%** |
| vantaggio mediano | +1,8% | +3,3% | **+7,1%** |
| mesi giudicabili | 78 | 75 | 69 |

E' il risultato piu' forte e meglio campionato che abbiamo, e cresce con
l'orizzonte. **Ma non e' un avviso di crescita**: e' un filtro di qualita'. Dice
di evitare chi emette azioni — e chi emette azioni sono le societa' che bruciano
cassa. Il merito e' piu' di cio' che esclude che di cio' che trova.

Tre cose che questi numeri dicono, e che vale la pena leggere due volte:

**Il «buon drawdown» non funziona.** E' l'idea di partenza del progetto — il
vecchio *Good Drawdown Monitor* — e su ottantadue mesi giudicabili perde a tutti
e tre gli orizzonti. Non e' sfortuna su un campione piccolo.

**Irrigidire le soglie lo peggiora.** «Crollo e ripresa» e' lo stesso filtro con
soglie piu' severe, e va peggio: −3,0% invece di −0,9%. Quando stringere non
migliora, il difetto sta nell'idea e non nella taratura.

**Due filtri buoni non fanno un filtro migliore.** I ricavi anno su anno da soli
vincono (+5,2%); aggiungerci il margine in crescita li fa perdere (−1,8%) e
dimezza i mesi giudicabili. Ogni criterio in piu' restringe la popolazione, e
sotto una certa soglia non stai piu' misurando: stai guardando aneddoti.

---

## Il rigioco, e come si legge

Il pulsante **«Ha mai funzionato?»**, accanto a «Cerca». Rigioca gli stessi
criteri a ogni fine mese dal 2019, e per ognuno confronta i titoli che avrebbe
trovato con **il resto degli investibili** — capitalizzazione sopra i 300 M$ e
almeno 1 M$ al giorno di controvalore scambiato, misurati con i valori **di quel
mese**.

Il dettaglio di come funziona sta in `docs/DECISIONI.md`. Qui bastano le tre
regole per leggerlo senza ingannarsi.

### 1. Guarda i mesi giudicabili prima del vantaggio

Un mese entra nel conto solo se ci sono almeno cinque titoli **da una parte e
dall'altra**: la mediana di due titoli e' un aneddoto con l'aria di una misura.
**Un vantaggio grande su quattordici mesi vale meno di uno piccolo su
settantacinque.**

La soglia vale su entrambi i lati dal 17/09/2026, e la ragione e' misurata: con
la soglia sui soli trovati, un criterio larghissimo si confrontava con un resto
di due o tre titoli e vinceva di oltre il 50%. Non perche' fosse buono: perche'
l'avversario non esisteva.

### 1bis. Il paragone e' fra GIUDICABILI, e cambia i numeri piu' di quanto sembri

Chi non ha il dato non finisce fra i perdenti: esce da entrambe le popolazioni,
e quanti siano si dichiara (`non_giudicabili`).

Sembra un dettaglio e non lo e'. **Misurato il 17/09/2026**: un criterio che
faceva passare chiunque avesse la misura, senza nessuna soglia vera, dava gia'
+2,0% a sei mesi sui ricavi anno su anno e +15,2% a dodici sulle azioni in
circolazione. Piu' del criterio stesso.

Il motivo e' che **avere il dato non e' neutro**: chi ha cinque trimestri
depositati e le azioni di un anno fa e' una societa' piu' vecchia, meglio
coperta e ancora viva. Il metro stava misurando se stesso.

Tutti i numeri di questo documento sono stati rifatti dopo quella correzione.

### 2. Confronta i tre orizzonti fra loro

| forma | significa |
|---|---|
| perde a 3, vince a 6 e 12 | il criterio e' **lento**: vede giusto prima che il prezzo lo segua |
| perde a tutti e tre | e' **sbagliato** |
| vince a tutti e tre | e' il caso buono, ed e' raro |

Con un orizzonte solo le prime due sembrano la stessa cosa. E' successo per
settimane.

### 3. Le misure di prezzo del rigioco NON sono quelle dello scanner

Il rigioco legge un punto per mese; lo scanner dal vivo legge le sedute. Quindi:

* la **variazione a un anno** e' fra due chiusure di fine mese;
* la **«media a 200 sedute»** e' la media di dieci chiusure mensili — un numero
  diverso, non un'approssimazione dello stesso;
* il **drawdown** non vede i minimi toccati dentro al mese, quindi **li
  sottostima**.

Sono numeri confrontabili fra loro nel tempo, non con quelli che vedi
nell'elenco dei risultati.

---

## Niente si aggiorna da solo

Non c'e' nessuno scheduler in tutto il sistema, e non e' una mancanza: e' una
scelta. Un sistema che si ricostruisce da solo spende la tua banda, la tua CPU
e — quando di mezzo c'e' un modello — i tuoi soldi, mentre tu guardi un'altra
pagina. Il vecchio tradash lo faceva, e il 28/08 ha scaricato ~500 ticker da
solo al riavvio del backend perche' una scheda del browser era rimasta aperta.

Al suo posto c'e' un **allarme**, nella barra in alto di ogni pagina: una
pastiglia col numero di cose invecchiate. Aprendola si vede cosa, da quanti
giorni, contro quale limite, e **cosa premere**:

| cosa | limite | dove si rifa' |
|---|---|---|
| Anagrafica dell'universo | 14 giorni | Universo → Anagrafica |
| Prezzi dell'universo | 1 giorno | Universo → Prezzi |
| Bilanci dell'universo | 1 giorno | Universo → Deriva i bilanci |
| Storico mensile | 1 giorno | Universo → Deriva lo storico |
| Verdetti dei preset | quando cambiano soglie o dati | `python manage.py preset` |

L'allarme legge SQLite e un file: non tocca la rete, e un test verifica che
chiederlo non produca **nemmeno una riga** nel registro delle chiamate — perche'
se ne producesse una vorrebbe dire che e' andato a prendere qualcosa.

## Gli errori da non fare

**Cercare le soglie che fanno vincere il criterio.** Il rigioco serve a chiedere
se un'idea funziona, non a tararla finche' funziona. Provare venti soglie e
tenere la migliore e' un altro modo di costruire il metro con la risposta: quella
soglia descrivera' benissimo il 2019-2026 e niente altro. E' lo stesso errore dei
sei pesi del rilevatore spin-off, nati da un caso solo.

**Leggere il rigioco come un backtest.** Non si compra e non si vende, non ci
sono costi, non c'e' uno stop, non ci sono pesi di portafoglio. E' la domanda
«cosa avresti trovato quel mese, e come sarebbe andata» — niente di piu'.

**Dimenticare che la finestra e' una sola.** 2019-2026: un regime di mercato, non
tre. A dodici mesi restano pochissimi mesi giudicabili per i criteri stretti, e
quella riga li' e' un indizio, non una misura.

**Aggiungere criteri per «essere piu' selettivi».** Vedi «Numeri che girano» qui
sopra: ogni filtro in piu' restringe la popolazione, e il punto in cui smetti di
misurare arriva prima di quanto sembri.
