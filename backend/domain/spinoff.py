"""
spinoff.py — riconoscere che si parla di uno spin-off, e a che punto e'.
# feat (Blocco 8): matematica pura sulle parole, nessuna lettura.

**Questo e' un rilevatore di menzioni, non un registro di eventi.** La
differenza e' sostanziale e va detta ogni volta: il vecchio tradash prendeva un
calendario curato da stockanalysis.com, con ex-date certe e la mappa
parent→newco, e lo confermava su EDGAR. Quelle due fonti sono fuori dal
perimetro deciso il 30/08/2026 — niente provider esterni nuovi, niente accessi a
sec.gov.

Quello che resta e' cio' che Defeatbeta sa: **780 notizie su 247 simboli** che
nominano uno spin-off, col corpo dell'articolo, piu' le earnings call dove il
management lo annuncia. Ci si puo' costruire un rilevatore che trova e legge,
non un calendario che certifica.

Un titolo che NOMINA uno spin-off non e' uno spin-off: puo' essere un
commento, una speculazione, un rinvio. Per questo ogni menzione porta con se'
l'articolo da cui viene, e lo stadio e' un'ipotesi dichiarata.

**Un residuo di imprecisione resta, e va saputo.** Filtrando sui titoli che
nominano la societa', NVDA passa da dodici menzioni a due — ma quelle due sono
"Nasdaq Drops As Nvidia Plunges; Chip Spinoff Soars", che nomina NVIDIA e uno
spin-off senza che sia lo spin-off di NVIDIA. Distinguere i due casi richiede di
leggere, ed e' quello che il prompt chiede al modello di fare.
"""

# Le parole con cui si nomina uno spin-off. La ricerca e' sul titolo, dove
# compaiono se l'articolo parla davvero di quello.
PAROLE = ("spin-off", "spinoff", "spin off")

# Come si riconosce lo stadio. L'ordine conta: "completato" vince su
# "annunciato", perche' un articolo che racconta il completamento nomina
# spesso anche l'annuncio.
STADI = (
    ("completato", ("completes", "completed", "begins trading", "starts trading",
                    "now trades", "has spun off", "spun off from")),
    ("rinviato", ("delays", "delayed", "postpone", "pushes back", "on hold",
                  "shelves", "scraps", "calls off")),
    ("in corso", ("approves", "approved", "sets date", "record date", "ex-date",
                  "files", "filed")),
    ("annunciato", ("plans", "announces", "announced", "to spin off", "will spin",
                    "considering", "explores", "weighs")),
)

STADIO_IGNOTO = "non determinabile"


def stadio(titolo: str) -> str:
    """A che punto sembra essere lo spin-off, dal titolo dell'articolo.

    E' un'ipotesi, non un fatto: "sembra" e' la parola giusta. Un titolo che
    non dice abbastanza torna `non determinabile`, che e' diverso da
    "annunciato" — e confonderli farebbe contare come annuncio un commento.
    """
    minuscolo = (titolo or "").lower()
    for nome, segni in STADI:
        if any(segno in minuscolo for segno in segni):
            return nome
    return STADIO_IGNOTO


def nomina_spinoff(testo: str) -> bool:
    """Il testo nomina uno spin-off?"""
    minuscolo = (testo or "").lower()
    return any(parola in minuscolo for parola in PAROLE)


def _paragrafi(corpo) -> list[str]:
    """I paragrafi di un articolo. Il corpo arriva come elenco di strutture."""
    if corpo is None:
        return []
    return [str(dict(p).get("paragraph") or "") for p in corpo]


def estratti(corpo, quanti: int = 3) -> list[str]:
    """I paragrafi dell'articolo che nominano lo spin-off, non tutto l'articolo.

    Un articolo intero sono migliaia di caratteri di cui la maggior parte non
    parla di questo. I paragrafi che lo nominano sono la parte che serve.
    """
    return [p for p in _paragrafi(corpo) if nomina_spinoff(p)][:quanti]


def _parole_del_nome(nome: str | None) -> list[str]:
    """Le parole con cui si riconosce una societa' in un titolo.

    Si scartano le forme giuridiche — Inc., Corporation, Ltd — e le parole
    corte: "Corporation" comparirebbe in mezzo mercato, e "IDT Corporation"
    verrebbe riconosciuta in un articolo su chiunque.
    """
    if not nome:
        return []
    scarti = {"inc", "inc.", "corp", "corp.", "corporation", "co", "co.", "ltd",
              "ltd.", "limited", "plc", "sa", "nv", "n.v.", "ag", "the", "holding",
              "holdings", "group", "company", "&"}
    parole = [p.strip(".,()").lower() for p in nome.split()]
    return [p for p in parole if p not in scarti and len(p) > 2]


def riguarda_il_titolo(testo: str, simbolo: str, nome: str | None) -> bool:
    """Questo testo parla della societa' che stiamo guardando, o di un'altra?

    Il difetto che chiude, misurato: NVDA risultava avere dodici menzioni di
    spin-off, e parlavano di Comcast e Honeywell. Erano notizie ASSOCIATE al
    simbolo — rassegne di mercato che nominano molti titoli — ma su altre
    societa'. Dodici menzioni che sembrano informazione e non lo sono.

    Il controllo e' sul TITOLO e non sul corpo, e la differenza si e' vista:
    guardando anche gli estratti, una rassegna che nomina NVIDIA in un
    paragrafo passava lo stesso. Chi scrive dello spin-off di una societa' la
    nomina nel titolo — vale per tutti e quattro i casi veri esaminati.
    """
    minuscolo = (testo or "").lower()
    if simbolo and simbolo.lower() in minuscolo:
        return True
    return any(parola in minuscolo for parola in _parole_del_nome(nome))


def menzioni_nelle_notizie(righe: list[dict], simbolo: str = "",
                           nome: str | None = None) -> list[dict]:
    """Le notizie che parlano di spin-off DI QUESTA societa', ridotte a cio' che si legge.

    Quando il nome non e' noto — l'8,6% dell'universo — non si puo' filtrare, e
    le menzioni tornano tutte con `riguarda_il_titolo` a `null`: e' un
    avvertimento per chi legge, non un silenzio.
    """
    trovate = []
    for riga in righe:
        titolo = riga.get("title") or ""
        if not nomina_spinoff(titolo):
            continue

        sappiamo_chi = bool(simbolo or nome)
        nostra = riguarda_il_titolo(titolo, simbolo, nome) if sappiamo_chi else None
        if nostra is False:
            continue

        pezzi = estratti(riga.get("news"))

        trovate.append({
            "quando": str(riga.get("report_date") or "")[:10],
            "titolo": titolo,
            "editore": riga.get("publisher"),
            "stadio_apparente": stadio(titolo),
            "estratti": pezzi,
            "riguarda_il_titolo": nostra,
            "link": riga.get("link"),
        })
    return trovate


def menzioni_nella_call(struttura: dict, quanti: int = 6) -> list[dict]:
    """Dove, in una earnings call, si parla di spin-off.

    Il management che lo nomina nella parte preparata e un analista che lo
    chiede nel botta e risposta non sono la stessa cosa: il primo e' una
    dichiarazione, il secondo una preoccupazione.
    """
    trovate = []

    for intervento in struttura.get("preparata", []):
        if nomina_spinoff(intervento.get("testo", "")):
            trovate.append({"dove": "parte preparata", "chi": intervento.get("chi"),
                            "testo": intervento.get("testo", "")})

    for scambio in struttura.get("scambi", []):
        if nomina_spinoff(scambio.get("domanda", "")):
            trovate.append({"dove": "domanda di un analista",
                            "chi": scambio.get("analista"), "testo": scambio.get("domanda", "")})
        for risposta in scambio.get("risposte", []):
            if nomina_spinoff(risposta.get("testo", "")):
                trovate.append({"dove": "risposta del management",
                                "chi": risposta.get("chi"), "testo": risposta.get("testo", "")})

    return trovate[:quanti]
