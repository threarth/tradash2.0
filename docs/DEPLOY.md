# Mettere tradash2.0 online

La macchina: **Contabo Cloud VPS 4 — 8 GB di RAM, 100 GB SSD, Ubuntu 26.04 LTS**,
con **nginx** davanti e **gunicorn** dietro.

Questo documento si legge dall'alto: ogni sezione presuppone che la precedente
sia andata a buon fine. Dove c'e' un numero, e' misurato — e c'e' scritto dove.

---

## 0. Perche' 8 GB, e perche' un worker solo

Sono le due scelte che non si possono cambiare senza rompere qualcosa.

**8 GB di RAM.** L'operazione piu' pesante che il sistema sappia fare e' la
costruzione dei prezzi dell'universo: legge un parquet da 445 MB e ci costruisce
sopra una finestra ordinata su 36,7 milioni di righe. Misurata il 14/09/2026 sul
codice vero: **3.022 MB di picco**. DuckDB si concede per default l'80% della RAM
di sistema, quindi su questa macchina si dara' ~6,4 GB: il margine e' doppio. Su
una macchina da 4 GB il tetto sarebbe 3,2 GB, cioe' **il picco misurato** — e il
lavoro morirebbe per OOM a meta', senza un errore che spieghi cosa e' successo.

**Un worker solo.** `core/registry.py:43` tiene i lavori in un dizionario **in
memoria di processo**. Con quattro worker, `/api/ops/active` mostrerebbe solo i
lavori del worker che risponde, e il pulsante Stop cadrebbe tre volte su quattro
sul processo sbagliato: la regola 1 smetterebbe di valere **in silenzio**, che e'
il modo peggiore in cui una regola puo' smettere di valere.

Quindi: `--workers 1 --threads 8`. La concorrenza la danno i thread, che
condividono la memoria e quindi anche il registro.

**Il disco.** Servono ~10 GB: 3 di sistema, 0,5 di ambiente Python, 4 di cache
dei parquet, 0,3 di database, qualche centinaio di MB fra documenti SEC e log.
Dei 100 GB ne avanzano novanta.

---

## 1. La macchina

```bash
# Come utente con sudo, appena creata la macchina.
sudo apt update && sudo apt upgrade -y
sudo apt install -y nginx git curl

# Un utente che NON e' root, e che non avra' mai bisogno di esserlo.
sudo adduser --system --group --home /opt/tradash2 --shell /bin/bash tradash2
```

**Il firewall**, prima di qualunque altra cosa: tre porte, non una di piu'.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status verbose
```

---

## 2. Python 3.13 senza toccare quello di sistema

Ubuntu 26.04 porta il suo Python, e non e' detto sia la 3.13. Non si tocca: si
usa `uv`, che scarica l'interprete che serve e lo tiene per conto suo.

```bash
sudo -u tradash2 -i
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

git clone https://github.com/threarth/tradash2.0.git /opt/tradash2/app
cd /opt/tradash2/app/backend

uv python install 3.13
uv venv --python 3.13
uv pip install -r requirements.txt
```

**Prima di lanciare quell'ultimo comando**, controlla che la versione di
gunicorn scritta in `requirements.txt` esista ancora e sia l'ultima: e' pinnata
sulla 23.0.0, che era l'ultima conosciuta quando il file e' stato scritto.

---

## 3. Le chiavi, l'utente, il tetto di spesa

**Il `.env`** — non e' nel repo e non ci va mai:

```bash
cat > /opt/tradash2/app/backend/.env <<'EOF'
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
EOF
chmod 600 /opt/tradash2/app/backend/.env
```

**L'utente che potra' entrare.** La password si scrive a voce, cosi' non finisce
nella cronologia della shell:

```bash
cd /opt/tradash2/app/backend
.venv/bin/python manage.py utente
```

Crea `data/utente.json` con permessi `600`, fuori da git, e sopravvive a
`manage.py rebuild`. Dentro c'e' un hash scrypt, mai la password.

> **Una password di sei caratteri regge solo perche' i tentativi sono frenati**
> (cinque, poi un'attesa che raddoppia fino a quindici minuti). Su una macchina
> raggiungibile da internet vale la pena metterne una lunga: si cambia
> dall'applicazione, dalla voce «Privacy e accesso», e il cambio fa scadere
> tutte le sessioni aperte.

**Il build del frontend.** Serve Node solo per costruirlo; poi non gira:

```bash
sudo apt install -y nodejs npm && sudo npm install -g pnpm
cd /opt/tradash2/app/frontend && pnpm install && pnpm build
```

---

## 4. Il servizio

`/etc/systemd/system/tradash2.service`:

```ini
[Unit]
Description=tradash2.0
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=tradash2
Group=tradash2
WorkingDirectory=/opt/tradash2/app/backend

# UN worker, e i thread per la concorrenza: il registro dei lavori vive in
# memoria di processo, e con piu' worker lo Stop cadrebbe sul processo sbagliato.
#
# Il timeout e' alto apposta: alcune letture vanno a Defeatbeta dal vivo e
# possono durare minuti la prima volta. Con i 30 secondi di default gunicorn
# ucciderebbe il worker a meta' di una lettura legittima.
ExecStart=/opt/tradash2/app/backend/.venv/bin/gunicorn \
    --workers 1 --threads 8 --timeout 300 \
    --bind 127.0.0.1:5001 \
    --access-logfile - --error-logfile - \
    wsgi:app

Environment=TRADASH2_TETTO_USD=10
Environment=TRADASH2_COOKIE_SICURO=1

Restart=on-failure
RestartSec=5

# Irrigidimenti: il processo non ha motivo di scrivere fuori da casa sua.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/tradash2/app/backend
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tradash2
sudo systemctl status tradash2

# Il controllo di salute: e' pubblico apposta, perche' systemd e nginx una
# password non ce l'hanno. Dice «vivo» e da quando, e nient'altro.
curl -s localhost:5001/api/salute
```

**Il punto d'ingresso e' `wsgi:app`**, cioe' `backend/wsgi.py`. Non fa niente di
piu' di `"app:create_app()"` — e' la convenzione, e serve a chi apre il repo e
va a cercarlo dove se lo aspetta.

**`PrivateTmp=true` e la cache di Defeatbeta.** La libreria metterebbe i byte
scaricati in `/tmp`, che con questa impostazione e' privato e sparisce a ogni
riavvio. Non e' un problema: `config.py` la sposta gia' dentro
`backend/data/httpfs_cache`, che sta fra i `ReadWritePaths`.

---

## 5. nginx e il certificato

`/etc/nginx/sites-available/tradash2`:

```nginx
server {
    listen 80;
    server_name IL-TUO-DOMINIO;

    # Il corpo delle richieste e' piccolo: nessun caricamento di file.
    client_max_body_size 1m;

    # Il controllo di salute, senza log: sarebbero migliaia di righe inutili.
    location = /api/salute {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        # Questa riga NON e' decorativa: il freno ai tentativi di accesso conta
        # per indirizzo, e senza il vero indirizzo conterebbe tutti insieme
        # sotto 127.0.0.1 — cioe' un estraneo che sbaglia password chiuderebbe
        # fuori anche te.
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Una lettura a freddo di Defeatbeta puo' durare minuti.
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/tradash2 /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d IL-TUO-DOMINIO
```

Certbot riscrive il blocco per l'HTTPS e mette il rinnovo automatico. Le
intestazioni di sicurezza — CSP, HSTS, X-Frame-Options — le manda gia'
l'applicazione (`core/accesso.py`), quindi in nginx non si ripetono: due
sorgenti per la stessa intestazione sono due posti dove sbagliarla.

---

## 6. La prima accensione, nell'ordine giusto

Entra dal browser e costruisci l'universo **in quest'ordine**, perche' i prezzi
si appoggiano all'anagrafica e senza si rifiutano di partire:

1. **Universo → Anagrafica.** ~95 MB da scaricare. Misurata: 4,9 s e 248 MB di
   picco a cache calda; la prima volta dipende dalla rete della macchina.
2. **Universo → Prezzi.** ~445 MB. Misurata: 8,4 s e 3.022 MB di picco a cache
   calda. **A freddo e' stata di 12 minuti e 41 secondi da una connessione
   domestica** — e il 94% di quel tempo era attesa di rete, non calcolo: sul VPS
   sara' molto meno, ma mettilo in conto e non farlo mentre qualcuno guarda.
3. **Deriva i bilanci** e **Deriva lo storico**, quando ti servono lo scanner e
   il rigioco.

**Dopo una ricostruzione dei prezzi, riavvia il servizio.** Il worker resta a
~2,6 GB residenti anche a lavoro finito, e su 8 GB non e' un problema ma non c'e'
motivo di tenerseli: `sudo systemctl restart tradash2`.

---

## 7. Manutenzione

**Il backup e' una cartella sola: `backend/data/`.** Dentro c'e' tutto quello che
non si ricostruisce — watchlist, grafici, referti pagati, impostazioni, utente,
documenti SEC scaricati a mano. Il database no: quello si rifa' dai pulsanti.

```bash
sudo -u tradash2 tar czf /opt/tradash2/backup-$(date +%F).tgz \
    -C /opt/tradash2/app/backend data
```

**La cache dei parquet cresce e non ha un tetto.** Il 14/09/2026 era 638 MB con
tre tabelle su cinque toccate; le due non ancora lette sono le grosse (le news
pesano 1,1 GB e le trascrizioni 2,1 GB), quindi tende verso i ~4 GB. Con 100 GB
di disco non e' un'urgenza, ma se un giorno dovesse dare fastidio si svuota
fermando il servizio e cancellando `backend/data/httpfs_cache/`: si riempie da
sola alla prima lettura.

**L'aggiornamento del codice:**

```bash
sudo -u tradash2 -i
cd /opt/tradash2/app && git pull
cd backend && .venv/bin/uv pip install -r requirements.txt
cd ../frontend && pnpm install && pnpm build
exit
sudo systemctl restart tradash2
```

Se lo schema e' cambiato, l'avvio si ferma da solo dicendo di lanciare
`manage.py rebuild`. Quel comando **cancella il registro delle chiamate, lo
storico dei lavori e i costi**; i referti tornano con `manage.py referti`.

---

## 8. Cosa e' chiuso, e cosa no

**Chiuso.** Ogni rotta sotto `/api/` risponde `401` a chi non ha fatto
l'accesso, tranne tre — `stato`, `login`, `logout` — che sono l'accesso stesso.
Non e' un elenco di rotte protette ma il contrario: si chiude per percorso, e un
endpoint scritto domani nasce chiuso. Un test della suite lo verifica
enumerando le rotte che l'applicazione registra davvero.

**Il cookie** e' di sola sessione, `HttpOnly`, `Secure`, `SameSite=Lax` — e
quest'ultimo e' la difesa contro le richieste cross-site, perche' qui le POST
sono tutto cio' che spende o cancella. Dentro c'e' il nome e un numero di
generazione, niente altro.

**Il tetto di spesa** e' 10 dollari al giorno, e si controlla prima di ogni
chiamata al modello. Si cambia con `TRADASH2_TETTO_USD` nel servizio; a zero e'
spento.

**Niente parte da solo, e non e' un'opinione.** Misurato il 15/09/2026:

| misura | esito |
|---|---|
| accendere il servizio | **0 chiamate, 0 lavori** |
| aprire tutte e cinque le pagine | **+2 chiamate, 0 di rete, 0 lavori** |
| chiedere l'allarme di freschezza | **0 chiamate** |

Le due chiamate sono letture del glossario da un file locale (`source=local`).
Ogni funzione che avvia un thread e' raggiungibile **solo da una POST**, cioe'
solo da un pulsante: `universe.build_in_background`,
`fondamentali.costruisci_in_background`, `costruisci_prezzi_in_background`,
`scanner.avvia`, `rigioco.avvia`, `spinoff_elenco.calcola_in_background`. Un test
della suite legge i sorgenti e fallisce se qualcuno introduce uno scheduler.

**Le tre uscite di rete, e cosa le fa partire:**

| dove va | cosa esce | quando |
|---|---|---|
| HuggingFace (Defeatbeta) | il nome di una tabella | apri la scheda di un titolo, o premi una derivazione |
| OpenAI / Anthropic | numeri gia' calcolati e testo di documenti SEC pubblici | **solo** `POST /api/analisi/...`, cioe' un pulsante |
| stockanalysis.com | niente, e' una GET | **solo** i due pulsanti degli spin-off |

Non ce ne sono altre: `grep` su tutto il backend trova `urlopen` in un file solo.

**Quando la fonte cade.** Succede: il 15/09/2026, mentre si scriveva questa
sezione, tutti i parquet di Defeatbeta hanno risposto 404 per qualche ora. Il
sistema adesso lo dichiara con un 503 e una frase leggibile — «non e' un guasto
di tradash» — invece di un 500 con stack trace, e **tutto cio' che e' gia' in
locale continua a funzionare**: universo, watchlist, scanner e allarmi leggono
da SQLite. Solo la scheda di un titolo ha bisogno della rete.

**Quello che resta aperto, e va saputo:**

* la pagina, il JavaScript e i fogli di stile sono pubblici — sono il guscio
  dentro cui vive la schermata di accesso, e non contengono niente che non sia
  gia' nel repo;
* **non c'e' il secondo fattore.** Un utente, una password;
* **i tentativi si contano in memoria**: riavviare il servizio azzera il freno;
* le chiamate ai modelli mandano a OpenAI e ad Anthropic i numeri gia' calcolati
  e il testo dei documenti SEC, che sono pubblici. Partono **solo da un
  pulsante**, e ognuna lascia due righe di registro col costo.
