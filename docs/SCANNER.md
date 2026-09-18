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

## I quattordici criteri

### Sei sul prezzo

| criterio | chiede | note |
|---|---|---|
| **Sceso almeno del** | X% sotto il massimo storico | il drawdown, in valore assoluto |
| **Sceso non piu' del** | meno di X% sotto il massimo | il filtro opposto: esclude i disastri |
| **Recuperato almeno il** | X% di risalita dal fondo | si usa insieme al primo |
| **Cresciuto in un anno** | +X% sulle ultime 252 sedute | |
| **Sopra la media a 200 sedute** | prezzo almeno X% sopra | vuole 200 sedute di storia |
| **Volume medio almeno** | N azioni al giorno, su 21 sedute | numero di azioni, non controvalore |

### Cinque sul bilancio

| criterio | chiede | trimestri gia' depositati che servono |
|---|---|---|
| **Ricavi in crescita sull'anno** | +X% sullo stesso trimestre dell'anno prima | **5** |
| **Ricavi in crescita sul trimestre** | +X% sul trimestre precedente | 2 |
| **Ricavi in accelerazione** | la crescita annua di adesso meno quella di prima | **6** |
| **Margine lordo in crescita** | +X punti in un trimestre | 2 |
| **EPS dell'ultimo trimestre** | almeno X | 2 |

### Uno sul numero di azioni

| criterio | chiede | note |
|---|---|---|
| **Azioni variate non piu' di** | il conteggio, non la causa | a `0` chiede solo che non siano aumentate |

### Uno sui depositi alla SEC

| criterio | chiede | note |
|---|---|---|
| **Depositi 8-K non oltre** | N volte il suo solito | soglia MASSIMA: serve a togliere |

Si contano solo gli **8-K**, i moduli del fatto rilevante. Nell'indice dei
depositi i Form 4 — operazioni degli insider — sono il 45,9% del totale contro
il 16,3% degli 8-K: contare «i depositi» vorrebbe dire contare i Form 4 e
chiamarli altro. La scelta di cosa contare *e'* l'indicatore.

Il point-in-time qui viene gratis, ed e' l'unico caso in tutto il sistema:
`filing_date` e' la data in cui il documento e' stato depositato, quindi
contarli per mese di deposito da' esattamente cio' che si sapeva allora — senza
`publication_dates` e senza stimare nessun ritardo.

### Uno trasversale: la forza relativa al settore

| criterio | chiede | note |
|---|---|---|
| **Batte la mediana del settore di** | X punti in un anno | l'unico che guarda anche gli ALTRI titoli |

E' l'unico criterio che non si puo' calcolare guardando un titolo solo. Un +30%
non vuol dire la stessa cosa dappertutto: se il settore ha fatto +45%, quel +30%
sta perdendo terreno mentre sale.

Tre cose da sapere, tutte e tre spiacevoli:

1. **Entrambi i capi vengono dalla serie MENSILE**, anche nello scanner dal
   vivo, dove tutto il resto si misura sulle sedute. Non e' una svista: la
   mediana di un settore su sedute vorrebbe dire leggere i prezzi giornalieri di
   undicimila titoli a ogni scansione. Prendere la mediana dai mesi e
   confrontarci il numero giornaliero del titolo sarebbe peggio — a meta' mese i
   due capi non coincidono, e in un mercato che tira la differenza fra «da fine
   mese scorso» e «da oggi» diventa un vantaggio che non c'entra col settore.
2. **Il settore non ha storia.** L'anagrafica tiene quello di adesso, e il
   rigioco applica al 2019 la classificazione di oggi. E' un look-ahead su
   un'ETICHETTA, non su un risultato — il settore non dice come e' andato il
   titolo, dice con chi lo si paragona — ma c'e'.
3. **Il titolo entra nella propria mediana.** Toglierlo vorrebbe dire una
   mediana per titolo invece che una per settore: da mille a duecentomila.
   Col minimo di venti membri pesa al massimo un ventesimo, e sui numeri veri —
   il settore piu' magro di tutto lo storico e' Utilities nell'agosto 2019 con
   71 titoli investibili — meno dell'1,5%.

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

Sette combinazioni **gia' rigiocate**, ognuna con il proprio verdetto attaccato.
Premerne una riempie il modulo; la ricerca la lanci tu.

| preset | criteri | verdetto (3 / 6 / 12 mesi) | mesi giudicabili |
|---|---|---|---|
| **Evita i guai** | azioni ≤ 0%, raffica 8-K ≤ 3x | **+1,7% / +3,1% / +8,4%** | 75 |
| **Numeri che girano** | ricavi anno +20%, margine +2 punti | −0,9% / +0,9% / **+6,6%** | 32 |
| **Cresce e guadagna** | ricavi anno +15%, EPS ≥ 0 | **+1,3% / +2,7% / +4,1%** | 34 |
| **Forza confermata** | sopra la media 200 +5%, un anno +20% | **+0,7% / +2,6% / +1,9%** | 75 |
| **Batte i suoi pari** | sopra la mediana del suo settore | **+1,0% / +1,7% / +1,6%** | 75 |
| **Buon drawdown** | sceso 30%, recuperato 15% | −0,8% / −0,9% / −0,6% | 82 |
| **Crollo e ripresa** | sceso 50%, recuperato 20% | −2,3% / −3,1% / −2,9% | 76 |

**Due su sette perdono, e restano in elenco per questo.** Un'idea scartata che
non sta scritta da nessuna parte torna da sola fra sei mesi. Fra le due c'e'
«Buon drawdown», che e' l'idea fondativa del vecchio tradash.

E uno ha **cambiato verdetto** dopo la correzione del metro: «Numeri che girano»
risultava perdente e adesso e' **lento** — perde a breve e vince a lungo. Non e'
cambiato il criterio: era il paragone a essere storto.

### Il preset migliore non cerca niente: toglie soltanto

«Evita i guai» e' fatto di **sole esclusioni** — non emette azioni, non deposita
8-K a raffica — e a dodici mesi da' **+8,4%**, piu' di ogni altro preset, su 75
mesi giudicabili che sono anche il campione piu' largo insieme a «Forza
confermata».

Non e' un caso ed e' il riassunto di tutto: dei quattro indicatori costruiti per
**avvertire di una crescita in arrivo**, i due che misurano meglio dicono
entrambi chi EVITARE. Nessuno dei quattro anticipa niente. Metterli insieme e'
l'unico modo onesto di usarli.

Va pero' combinato con un criterio che CERCA: da solo lascia passare 2.312
titoli al mese, che non e' una lista da guardare — e' l'universo meno i guai.

**Questi numeri non sono scritti a mano.** Li produce `python manage.py preset`,
che rigioca tutti i preset e scrive `backend/data/preset_verdetti.json` — un file
che sta in git apposta, cosi' un verdetto che cambia si vede come diff invece di
sostituirsi in silenzio a quello di prima. Il file porta con se' **la data della
misura, le soglie e la finestra di dati** usate; se una delle tre non combacia
piu' con quelle di adesso, la pagina lo dice e ti chiede di rigiocare. Non lo fa
da sola: vedi «Niente si aggiorna da solo» qui sotto.

### Il criterio piu' solido non e' un preset: e' il NUMERO DI AZIONI

`azioni_variazione_massima` misura di quanto e' cambiato il **conteggio** delle
azioni in circolazione in un anno. Non la causa: un calo puo' venire da un
riacquisto o da un annullamento, un aumento da un aumento di capitale, da
compensi in azioni o da azioni emesse per pagare un'acquisizione.

Gli split non la sporcano, ed e' verificato: NVDA ha fatto uno split 10:1 nel
giugno 2024 e nello storico risultano ~24,6 miliardi di azioni sia prima sia
dopo. Defeatbeta rettifica il conteggio all'indietro, come i prezzi.

| soglia | trovati/mese | 3 mesi | 6 mesi | 12 mesi |
|---|---|---|---|---|
| **azioni che non aumentano** (≤ 0%) | 1.187 | +2,1% | +3,4% | **+8,1%** |
| calate almeno del 2% | 588 | +1,8% | +3,3% | +7,1% |
| calate almeno del 5% | 248 | +1,5% | +3,2% | +5,4% |

Su 69-78 mesi giudicabili, con l'88-96% dei mesi vinti: il risultato piu' forte
e meglio campionato che abbiamo, e cresce con l'orizzonte.

**Il merito e' tutto sulla soglia dello zero.** Stringere verso chi riduce di
piu' PEGGIORA il risultato. Quindi non e' «chi riduce le azioni va bene»: e'
**«chi le aumenta va male»**, e il resto e' indifferente.

E non e' un avviso di crescita: e' un filtro di qualita'. Dice di evitare chi
emette azioni — che sono, in larga parte, le societa' che bruciano cassa. Vale
piu' per cio' che esclude che per cio' che trova.

### La raffica di 8-K: nata per anticipare, misurata al contrario

`depositi_raffica_massima` chiede che il titolo **non** stia depositando 8-K
molto piu' del suo solito — «il suo solito» sono i due anni precedenti, «molto
piu'» sono gli ultimi tre mesi contro quella media.

Era il quarto dei quattro indicatori chiesti per avvertire di una crescita in
arrivo. L'ipotesi era che una pila di documenti nuovi segnalasse qualcosa in
movimento. E' vero che segnala qualcosa in movimento; solo che va nell'altra
direzione. Misurato prima di costruire niente, sul gruppo IN raffica:

| chi e' in raffica | 3 mesi | 6 mesi | 12 mesi |
|---|---|---|---|
| almeno 2x il suo solito | −1,1% (38%) | −1,7% (39%) | −2,0% (32%) |
| almeno 3x il suo solito | −0,5% (44%) | −4,2% (31%) | −5,1% (30%) |

Peggiora con l'orizzonte **e** con l'intensita': non e' lento, e' rovesciato.

La lettura e' che **le buone notizie arrivano nella trimestrale e le cattive
arrivano in pila**: ristrutturazioni, cause, dirigenti che se ne vanno,
finanziamenti diluitivi, avvisi di delisting. Un'acquisizione felice e' un 8-K;
una societa' che va a pezzi ne deposita otto.

Quindi il criterio e' stato acceso al contrario, come ESCLUSIONE. Rigiocato:

| soglia (passa chi sta sotto) | trovati/mese | 3 mesi | 6 mesi | 12 mesi |
|---|---|---|---|---|
| 1,2x | 1.598 | +0,2% (57%) | +0,5% (59%) | +0,9% (65%) |
| 1,5x | 1.916 | +0,4% (63%) | +1,3% (62%) | +2,3% (70%) |
| 2,0x | 2.184 | +0,9% (67%) | +1,8% (64%) | +2,8% (68%) |
| **3,0x** | 2.312 | +0,6% (54%) | **+4,3% (68%)** | **+6,1% (72%)** |

**Escludere di piu' non e' meglio.** A 1,2x il vantaggio quasi sparisce: quella
soglia butta fuori anche chi ha depositato un 8-K in piu' del solito, che non
vuol dire niente. Il danno sta nelle raffiche ESTREME, e basta togliere quelle.

Il controllo nullo e' stato fatto — soglia a un miliardo, cioe' «passa chiunque
si possa misurare» — e risponde **nessun mese giudicabile**: il vantaggio non e'
l'artefatto di avere il dato.

Una cautela onesta: 3,0x e' il migliore di quattro valori provati. L'effetto e'
solido a 1,5x, 2x e 3x — quindi c'e' — ma che il massimo cada proprio a 3
e' anche un po' fortuna, e non va letto come «la soglia giusta e' tre».

### La forza relativa al settore: il merito e' alla meta', non in cima

`forza_settore_minima` chiede di aver battuto la **mediana** del proprio settore
nell'ultimo anno. Rigiocata il 18/09/2026:

| soglia | trovati/mese | 3 mesi | 6 mesi | 12 mesi |
|---|---|---|---|---|
| **sopra la mediana** (≥ 0) | 1.458 | +1,0% (59%) | **+1,7% (64%)** | +1,6% (61%) |
| almeno +10 punti | 1.098 | +0,6% (58%) | +0,8% (57%) | +0,8% (56%) |
| almeno +25 punti | 717 | +0,2% (51%) | +0,3% (51%) | −0,4% (48%) |
| almeno +50 punti | 393 | −0,8% (45%) | −2,4% (35%) | **−4,4% (36%)** |

Fra parentesi la quota di mesi vinti, su 69-78 mesi giudicabili.

**Ha la stessa forma del criterio sul numero di azioni: il merito e' tutto alla
soglia zero, e stringere peggiora.** Ma qui e' piu' netto — a +50 punti il
criterio non e' soltanto inutile, e' **dannoso**: perde nel 64% dei mesi e costa
il 4,4% a dodici mesi. Chi ha corso di piu' nell'ultimo anno tende a restituire.

Quindi la lettura e': **stai sopra la meta' del tuo settore, non in cima.**

**E non e' un avviso di crescita in arrivo — e' il contrario.** Dice chi sta
GIA' correndo. Fra i quattro indicatori chiesti per anticipare una crescita,
questo e' quello che guarda piu' indietro di tutti.

Il controllo nullo e' stato fatto e ha risposto bene: con la soglia a −10 —
cioe' «passa chiunque si possa misurare» — il rigioco dice **nessun mese
giudicabile**, perche' «il resto» resta vuoto e la guardia sui due minimi si
rifiuta di emettere un verdetto. Il vantaggio alla soglia zero non e' quindi
l'artefatto di «chi ha il dato»: e' lo stesso difetto che il 17/09 aveva
gonfiato i ricavi e le azioni, ed e' stato ricontrollato apposta.

### L'accelerazione dei ricavi non funziona, e la ragione e' aritmetica

`ricavi_accelerazione_minima` — la crescita anno su anno di adesso meno quella
del trimestre prima — da' 39% / 40% / 58% dei mesi vinti e −0,7% / −1,0% /
+0,5%. Non e' sfortuna, e il perche' e' misurabile:

**La correlazione fra l'accelerazione di un trimestre e quella del successivo e'
−0,499**, su 42.456 coppie e 6.923 titoli. Negativa, e quel numero non e'
casuale: l'accelerazione e' `YoY(t) − YoY(t−1)` e quella dopo e'
`YoY(t+1) − YoY(t)`, che condividono `YoY(t)` **con segno opposto**. Se i valori
anno su anno fossero rumore indipendente, la correlazione verrebbe esattamente
−0,5.

In pratica: chi accelera di piu' di 5 punti, il trimestre dopo accelera ancora
nel **44%** dei casi — meno del 52% di chiunque altro. Selezionare
sull'accelerazione vuol dire prendere i titoli al picco locale della loro curva
di crescita, subito prima che rientri.

**La lezione generale**: una misura costruita come differenza di due misure
consecutive eredita una correlazione di −0,5 anche quando sotto non c'e' niente.
Prima di credere a una derivata seconda, va confrontata con quel numero.

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
