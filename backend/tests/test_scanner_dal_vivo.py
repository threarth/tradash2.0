"""
test_scanner_dal_vivo.py — ogni criterio dev'essere calcolabile dallo scanner.
# fix: il criterio piu' solido del progetto non passava mai dal vivo.

Il difetto che questo file esiste per impedire: `azioni_variazione_massima`
veniva riempito dal rigioco e da nessun altro. Il rigioco lo misurava vincente
nell'88-96% dei mesi; lo scanner lo trovava vuoto per chiunque, e un criterio
su una casella vuota non da' errore — non passa. Zero risultati, nessuna
spiegazione, e il preset «Evita i guai» che non trovava niente.

Nessun test se ne accorgeva, perche' i test del dominio costruiscono le misure
a mano: chi scrive il test mette la casella, e il codice vero non la metteva.
Qui la misura la costruisce `_misura_titolo`, cioe' lo stesso codice che gira
dal vivo, e si controlla ogni criterio di `scansione.CRITERI` — compresi quelli
che qualcuno aggiungera' domani.
"""
import pytest

from data import scanner
from domain import scansione

SIMBOLO = "PROVA"
MESE = "2026-06"

# Abbastanza sedute per ogni finestra (la piu' lunga e' 252), con una discesa
# e una risalita: senza, il drawdown non avrebbe profondita' ne' recupero.
SALITA = [100.0 + i * 0.5 for i in range(150)]
DISCESA = [175.0 - i * 1.0 for i in range(80)]
RISALITA = [95.0 + i * 0.4 for i in range(90)]
CHIUSURE = SALITA + DISCESA + RISALITA
VOLUMI = [1_000_000.0] * len(CHIUSURE)


def _mesi_indietro(quanti: int) -> str:
    anno, numero = int(MESE[:4]), int(MESE[5:7])
    totale = (anno * 12 + numero - 1) - quanti
    return f"{totale // 12:04d}-{totale % 12 + 1:02d}"


def _contesto_pieno() -> scanner.Contesto:
    """Un contesto in cui ogni misura ha i dati che le servono."""
    depositi = {_mesi_indietro(i): 2 for i in range(30)}
    mensili = {_mesi_indietro(0): {"azioni": 950.0},
               _mesi_indietro(scansione.MESI_PER_AZIONI): {"azioni": 1000.0}}
    settore = {
        "base": "sedute", "ancora": "2026-06-30",
        "settori": {SIMBOLO: "Technology"},
        "variazioni": {SIMBOLO: 0.30},
        "riferimenti": {"Technology": {
            "mediana": 0.10, "membri": scansione.MEMBRI_MINIMI_SETTORE + 10}},
    }
    return scanner.Contesto(settore=settore, depositi_8k={SIMBOLO: depositi},
                            mensili={SIMBOLO: mensili}, mese=MESE)


@pytest.fixture
def fondamentali_pieni(monkeypatch):
    """I bilanci si leggono dal database: qui si danno gia' pronti e completi."""
    pieni = {"ricavi_qoq": 0.05, "ricavi_yoy": 0.20, "ricavi_accelerazione": 0.03,
             "margine": 0.60, "margine_variazione": 0.01, "eps": 1.5, "trimestri": 8}
    monkeypatch.setattr(scanner, "_fondamentali", lambda simbolo, fino_a: pieni)


@pytest.mark.usefixtures("fondamentali_pieni")
def test_ogni_criterio_e_calcolabile_dallo_scanner_dal_vivo():
    """Con tutti i dati presenti, nessun criterio deve trovare la sua casella vuota."""
    misurato = scanner._misura_titolo(SIMBOLO, CHIUSURE, VOLUMI, _contesto_pieno(), None)

    vuoti = sorted(nome for nome, (misura, _, _) in scansione.CRITERI.items()
                   if misura(misurato) is None)

    assert not vuoti, (
        f"lo scanner dal vivo non riempie la misura di: {vuoti}. Il criterio "
        f"esiste, ma dal vivo non passera' mai per nessuno — senza un errore."
    )


@pytest.mark.usefixtures("fondamentali_pieni")
def test_il_numero_di_azioni_arriva_allo_scanner():
    """Il caso che si era rotto: 1.000 azioni un anno fa, 950 adesso."""
    misurato = scanner._misura_titolo(SIMBOLO, CHIUSURE, VOLUMI, _contesto_pieno(), None)

    assert misurato["azioni"]["variazione_1a"] == pytest.approx(-0.05)
    assert scansione.valuta(misurato, {"azioni_variazione_massima": 0.0})[0] is True


@pytest.mark.usefixtures("fondamentali_pieni")
def test_senza_un_mese_di_ancora_azioni_e_depositi_restano_vuoti():
    """Senza storico mensile non c'e' niente da confrontare: vuoto, non zero."""
    contesto = _contesto_pieno()
    senza_mese = scanner.Contesto(settore=contesto.settore, depositi_8k={},
                                  mensili={}, mese=None)

    misurato = scanner._misura_titolo(SIMBOLO, CHIUSURE, VOLUMI, senza_mese, None)

    assert misurato["azioni"] is None
    assert misurato["depositi"]["raffica"] is None
    assert scansione.misurabile(misurato, {"azioni_variazione_massima": 0.0}) is False
