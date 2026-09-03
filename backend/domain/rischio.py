"""
rischio.py — quanto si puo' perdere, e per quali ragioni. Senza chiedere a nessuno.
# feat: il punteggio di rischio, deterministico e scomponibile.

**Non viene dopo un'analisi: viene prima, e le alimenta.** Tutti i suoi
ingredienti sono gia' calcolati da codice che non parla con nessun modello — i
cinque segnali dai bilanci, la discesa storica dai prezzi, il peso del valore
terminale e la crescita implicita dal DCF. Costa zero e si puo' chiedere per
qualunque titolo, in qualunque momento.

Quello che le analisi aggiungono non e' il punteggio: sono le **condizioni** —
a cosa servirebbe guardare perche' quel rischio cambi.

## Perche' questo punteggio non e' quello che il progetto ha gia' tolto due volte

L'Health Score del vecchio tradash e il verdetto sintetico sono stati eliminati
per una ragione precisa: **erano medie pesate che nascondevano il disaccordo**.
Quattro sotto-punteggi con pesi arbitrari producevano un numero che si muoveva
per motivi che nessuno sapeva ricostruire.

Qui tre cose lo rendono diverso:

1. **Il rischio prende il PEGGIORE, non la media.** Un rischio alto non si
   annulla con quattro bassi: se il valore dipende per il 70% da cio' che
   succede dopo il decimo anno, il fatto che i margini siano solidi non lo
   riduce. Mediarli direbbe «medio», e sarebbe falso.
2. **Ogni componente porta il numero che l'ha prodotto.** Non c'e' un peso da
   indovinare: c'e' una soglia scritta, e il valore misurato accanto.
3. **Cio' che non si sa non abbassa il rischio: abbassa la CONFIDENZA.** Sono
   due assi diversi, e confonderli e' il modo classico per far sembrare sicuro
   un titolo di cui non sappiamo niente.
"""

ALTO = "alto"
MEDIO = "medio"
BASSO = "basso"
IGNOTO = "non calcolabile"

# L'ordine conta: serve a scegliere il peggiore.
GRAVITA = {IGNOTO: -1, BASSO: 0, MEDIO: 1, ALTO: 2}

# Le soglie. Stanno qui e non sparse nel codice perche' un giudizio che cambia
# al cambiare di una soglia deve poter dire QUALE soglia.
DISCESA_MEDIA = 0.15          # oltre questa discesa storica, rischio medio
DISCESA_ALTA = 0.35           # oltre, alto
CODA_MEDIA = 0.40             # quota del valore oltre il decimo anno
CODA_ALTA = 0.70
CRESCITA_RICHIESTA_MEDIA = 0.7   # implicita / storica
CRESCITA_RICHIESTA_ALTA = 1.3

# Come si legge un segnale F1-F5.
DA_SEGNALE = {"acceso": ALTO, "attenzione": MEDIO, "spento": BASSO, "ignoto": IGNOTO}


def _banda(valore: float | None, soglia_media: float, soglia_alta: float) -> str:
    """In quale banda cade un numero. `IGNOTO` se il numero non c'e'."""
    if valore is None:
        return IGNOTO
    if valore >= soglia_alta:
        return ALTO
    if valore >= soglia_media:
        return MEDIO
    return BASSO


def _voce(nome: str, banda: str, misura, perche: str) -> dict:
    """Un componente del rischio, con il numero che l'ha deciso."""
    return {"nome": nome, "banda": banda, "misura": misura, "perche": perche}


def da_segnali(segnali: dict) -> dict:
    """Il rischio che viene dai bilanci: i cinque segnali, il peggiore di loro."""
    voci = (segnali or {}).get("segnali") or {}
    if not voci:
        return _voce("Segnali di bilancio", IGNOTO, None,
                     "i cinque segnali non sono stati calcolati")

    peggiore, quale = BASSO, None
    for nome, dati in voci.items():
        banda = DA_SEGNALE.get(dati.get("stato"), IGNOTO)
        if GRAVITA[banda] > GRAVITA[peggiore]:
            peggiore, quale = banda, f"{nome}: {dati.get('perche')}"

    accesi = sum(1 for d in voci.values() if d.get("stato") == "acceso")
    ignoti = sum(1 for d in voci.values() if d.get("stato") == "ignoto")
    return _voce(
        "Segnali di bilancio", peggiore,
        {"accesi": accesi, "su": len(voci), "ignoti": ignoti},
        quale or f"nessuno dei {len(voci)} segnali e' acceso",
    )


def da_discesa(profilo: dict | None) -> dict:
    """Il rischio che viene da quanto il titolo e' gia' sceso in passato.

    Si guarda la discesa MASSIMA dentro la caduta in corso, non quella attuale:
    quanto e' arrivato a perdere chi era entrato prima e' cio' che dice quanto
    puo' fare male, non quanto fa male adesso.
    """
    if not profilo:
        return _voce("Discesa attraversata", IGNOTO, None,
                     "non ci sono abbastanza prezzi per misurarla")

    profonda = abs(profilo.get("profondita_massima") or 0.0)
    return _voce(
        "Discesa attraversata", _banda(profonda, DISCESA_MEDIA, DISCESA_ALTA),
        round(profonda, 4),
        f"e' arrivato a perdere il {profonda * 100:.0f}% dal suo massimo, e ci ha "
        f"messo {profilo.get('giorni_sotto_il_massimo', 0)} sedute a risalire",
    )


def da_coda(peso_terminale: float | None, motivo: str | None = None) -> dict:
    """Il rischio che viene da quanta parte del valore sta oltre l'orizzonte.

    Se meta' del valore dipende da cio' che succede dopo il decimo anno, il DCF
    sta dicendo soprattutto una cosa che nessuno sa prevedere.
    """
    return _voce(
        "Valore oltre l'orizzonte", _banda(peso_terminale, CODA_MEDIA, CODA_ALTA),
        None if peso_terminale is None else round(peso_terminale, 4),
        (motivo or "non c'e' un DCF da cui misurarlo") if peso_terminale is None else
        f"il {peso_terminale * 100:.0f}% del valore viene da dopo il decimo anno",
    )


def da_crescita(implicita: float | None, storica: float | None,
                motivo: str | None = None) -> dict:
    """Il rischio che viene da quanto il prezzo chiede rispetto a quanto e' stato.

    Non e' «cresce poco» o «cresce tanto»: e' se il prezzo attuale pretende una
    crescita che questa azienda non ha mai avuto. Un titolo che ne chiede meta'
    di quella storica e' meno esposto di uno che ne chiede il doppio.
    """
    if implicita is None or not storica or storica <= 0:
        return _voce("Crescita richiesta dal prezzo", IGNOTO, None,
                     motivo or "manca la crescita implicita o quella storica")

    rapporto = implicita / storica
    return _voce(
        "Crescita richiesta dal prezzo",
        _banda(rapporto, CRESCITA_RICHIESTA_MEDIA, CRESCITA_RICHIESTA_ALTA),
        round(rapporto, 4),
        f"il prezzo implica il {implicita * 100:.0f}% di crescita, la storia ne "
        f"ha fatto il {storica * 100:.0f}%",
    )


def punteggio(componenti: list[dict]) -> dict:
    """Il rischio complessivo: il PEGGIORE dei componenti, e chi l'ha deciso.

    Non la media, ed e' la scelta che tiene questo punteggio diverso da quelli
    che il progetto ha gia' tolto: un rischio alto non si annulla con quattro
    bassi. La confidenza e' un asse a parte — dice quanti componenti si sono
    potuti calcolare, e non abbassa il rischio.
    """
    calcolabili = [c for c in componenti if c["banda"] != IGNOTO]
    if not calcolabili:
        return {"banda": IGNOTO, "deciso_da": None, "componenti": componenti,
                "confidenza": "bassa",
                "perche": "nessun componente del rischio si e' potuto calcolare"}

    peggiore = max(calcolabili, key=lambda c: GRAVITA[c["banda"]])
    quanti = len(calcolabili)
    return {
        "banda": peggiore["banda"],
        "deciso_da": peggiore["nome"],
        "perche": peggiore["perche"],
        "componenti": componenti,
        "calcolati": quanti,
        "su": len(componenti),
        # Cio' che non si sa non abbassa il rischio: abbassa la confidenza.
        "confidenza": "alta" if quanti == len(componenti)
                      else "media" if quanti >= len(componenti) - 1 else "bassa",
    }
