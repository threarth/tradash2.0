"""
allarmi.py — cosa e' invecchiato. Lo dice, e non fa niente.
# feat: l'allarme sostituisce lo scheduler che questo progetto non vuole.

## La scelta, dichiarata dall'utente il 15/09/2026

**Niente scheduler, niente ricostruzioni automatiche.** Se l'anagrafica ha
quattordici giorni, il sistema lo DICE e tu decidi. Non e' una mancanza da
colmare: e' la regola 2 portata alle conseguenze. Un sistema che si ricostruisce
da solo e' un sistema che spende la tua banda, la tua CPU e — quando di mezzo
c'e' un modello — i tuoi soldi, mentre tu guardi un'altra pagina.

Il vecchio tradash lo faceva, e il 28/08 ha scaricato ~500 ticker da solo al
riavvio del backend perche' una scheda del browser era rimasta aperta.

## Perche' non basta la pagina Universo

La freschezza era gia' dichiarata, ma solo li' dentro: per vederla bisognava
aver gia' deciso di aprire quella pagina. Un allarme che si vede solo se lo vai
a cercare non e' un allarme, e' una nota a pie' di pagina.

Questo modulo risponde a una domanda sola — «cosa e' vecchio, adesso?» — e la
risposta e' fatta di righe con **motivo** e **azione**, mai di soli booleani:
«universe_anagrafica: True» non dice a nessuno cosa fare.

## Cosa NON fa

Non ricostruisce, non scarica, non tocca la rete. Legge la tabella `freshness`
e un file JSON. Si puo' chiamare a ogni apertura di pagina senza pensarci.
"""
import logging

import config
from core import freshness
from core.schema import GLOBAL_SCOPE
from data import defeatbeta, preset

logger = logging.getLogger(__name__)

# Cosa si sorveglia, cosa si fa quando e' vecchio, e DOVE si preme.
#
# L'azione e' scritta come la leggerebbe una persona — il nome del pulsante, non
# quello dell'endpoint. L'endpoint sta accanto perche' il pannello ci mette un
# pulsante sopra: se la pagina se lo ricavasse da sola dal nome della categoria,
# quella mappa invecchierebbe in silenzio il giorno in cui una rotta cambia.
#
# `endpoint` vale `None` per cio' che si rifa' solo da terminale, e li' il
# pannello mostra il comando invece di un pulsante che non potrebbe esistere.
SORVEGLIATI = (
    (defeatbeta.CATEGORY_ANAGRAFICA, "Anagrafica dell'universo",
     "Universo → Anagrafica", "/api/universe/anagrafica"),
    (defeatbeta.CATEGORY_MERCATO, "Prezzi dell'universo",
     "Universo → Prezzi", "/api/universe/mercato"),
    (defeatbeta.CATEGORY_FONDAMENTALI, "Bilanci dell'universo",
     "Universo → Deriva i bilanci", "/api/universe/fondamentali"),
    (defeatbeta.CATEGORY_PREZZI_MENSILI, "Storico mensile",
     "Universo → Deriva lo storico", "/api/universe/storico"),
)

SECONDI_PER_GIORNO = config.SECONDS_PER_DAY


def _giorni(eta_s: float | None) -> float | None:
    """L'eta' in giorni, che e' l'unita' in cui una persona la pensa."""
    return None if eta_s is None else round(eta_s / SECONDI_PER_GIORNO, 1)


def _riga(categoria: str, etichetta: str, azione: str, endpoint: str | None) -> dict:
    """Lo stato di una categoria sorvegliata, con motivo e azione sempre pieni."""
    serve, motivo = freshness.should_fetch_global(categoria)
    eta_s = freshness.age_seconds(GLOBAL_SCOPE, categoria)
    return {
        "categoria": categoria,
        "etichetta": etichetta,
        "vecchio": serve,
        "eta_giorni": _giorni(eta_s),
        "limite_giorni": _giorni(freshness.ttl_for(categoria)),
        "reason": motivo,
        "azione": azione,
        "endpoint": endpoint,
    }


def _riga_preset() -> dict:
    """I verdetti dei preset invecchiano in un altro modo: per confronto."""
    stato = preset.con_verdetto()
    return {
        "categoria": "preset",
        "etichetta": "Verdetti dei preset",
        "vecchio": stato["da_rimisurare"],
        "eta_giorni": None,
        "limite_giorni": None,
        "reason": "; ".join(stato["perche"]) or "misurati con le soglie di adesso",
        "azione": stato["azione"],
        # Niente endpoint: rigiocare i preset e' un comando da terminale, e
        # produce un file che va in git. Un pulsante che lo lanciasse dal
        # browser scriverebbe nel repo senza che nessuno veda il diff.
        "endpoint": None,
    }


def stato() -> dict:
    """Cosa e' vecchio adesso. Nessun lavoro, nessuna rete: solo la risposta.

    `quanti` e' il numero che la barra in alto mostra come pastiglia. Zero
    significa che non c'e' niente da fare, ed e' un'informazione anche quella.
    """
    righe = [_riga(categoria, etichetta, azione, endpoint)
             for categoria, etichetta, azione, endpoint in SORVEGLIATI]
    righe.append(_riga_preset())

    vecchi = [r for r in righe if r["vecchio"]]
    return {
        "quanti": len(vecchi),
        "vecchi": vecchi,
        "tutti": righe,
        # Detto qui perche' e' la domanda che chi vede una pastiglia rossa si fa
        # subito dopo: «e adesso parte qualcosa?». No.
        "nota": ("nessuna di queste cose si ricostruisce da sola: il sistema "
                 "dice cosa e' vecchio, la decisione di rifarlo e' tua"),
    }
