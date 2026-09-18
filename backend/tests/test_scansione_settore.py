"""
test_scansione_settore.py — la forza relativa al settore.
# feat: l'indicatore trasversale, e le tre cose che deve rifiutare di dire.

E' l'unico criterio che ha bisogno di sapere come sono andati GLI ALTRI. Tutti
gli altri guardano il titolo e basta, e questo cambia due cose: la mediana va
calcolata prima di giudicare chiunque, e dove il settore e' magro la misura non
esiste invece di valere zero.
"""
from pathlib import Path

import pytest

import config
from domain import scansione


def test_la_mediana_non_e_la_media():
    """In un settore con dentro un titolo esploso, la media diventa quel titolo."""
    variazioni = {"a": 0.01, "b": 0.02, "c": 0.03, "d": 9.00}
    settori = dict.fromkeys(variazioni, "Tecnologia")

    riferimenti = scansione.mediane_di_settore(variazioni, settori)

    assert riferimenti["Tecnologia"]["mediana"] == 0.025
    assert riferimenti["Tecnologia"]["membri"] == 4


def test_chi_non_ha_settore_non_entra_nella_mediana():
    """Non e' uno zero: e' qualcuno di cui non si sa in che gara corre."""
    variazioni = {"a": 0.10, "b": 0.20, "senza": -5.0}
    settori = {"a": "Energia", "b": "Energia"}

    riferimenti = scansione.mediane_di_settore(variazioni, settori)

    assert riferimenti["Energia"]["membri"] == 2
    assert riferimenti["Energia"]["mediana"] == pytest.approx(0.15)


def test_chi_non_ha_variazione_non_entra_nella_mediana():
    """Un titolo quotato da tre mesi non ha fatto zero: non ha fatto niente."""
    variazioni = {"a": 0.10, "b": 0.20, "nuovo": None}
    settori = dict.fromkeys(variazioni, "Energia")

    riferimenti = scansione.mediane_di_settore(variazioni, settori)

    assert riferimenti["Energia"]["membri"] == 2


def test_un_settore_troppo_magro_non_da_una_misura():
    """Sotto il minimo la forza vale None, e un criterio su None non passa."""
    riferimento = {"mediana": 0.10, "membri": scansione.MEMBRI_MINIMI_SETTORE - 1}

    misura = scansione.forza_settore(0.50, riferimento)

    assert misura["forza"] is None
    assert misura["membri"] == scansione.MEMBRI_MINIMI_SETTORE - 1


def test_la_forza_e_la_differenza_dalla_mediana():
    """Il numero e' «quanto meglio dei pari», non «quanto e' salito»."""
    riferimento = {"mediana": 0.45, "membri": 80}

    misura = scansione.forza_settore(0.30, riferimento)

    # +30% in un settore che ha fatto +45% e' un titolo che perde terreno
    # mentre sale: e' esattamente il caso che il solo prezzo non distingue.
    assert misura["forza"] == pytest.approx(-0.15)
    assert misura["mediana_settore"] == 0.45


def test_senza_riferimento_la_forza_non_esiste():
    """Un settore che non c'e' non e' un settore andato a zero."""
    assert scansione.forza_settore(0.30, None)["forza"] is None
    assert scansione.forza_settore(None, {"mediana": 0.1, "membri": 99})["forza"] is None


def test_il_criterio_non_passa_senza_la_casella():
    """Chi non inietta il settore non deve far passare il criterio per sbaglio."""
    criteri = {"forza_settore_minima": 0.0}
    misurato = scansione.misure([10.0, 11.0, 12.0])

    assert scansione.misurabile(misurato, criteri) is False
    assert scansione.valuta(misurato, criteri)[0] is False


def test_il_criterio_passa_quando_batte_i_pari():
    criteri = {"forza_settore_minima": 0.05}
    misurato = scansione.misure([10.0, 11.0, 12.0])
    misurato["settore"] = scansione.forza_settore(0.30, {"mediana": 0.10, "membri": 50})

    assert scansione.misurabile(misurato, criteri) is True
    soddisfa, spiegazioni = scansione.valuta(misurato, criteri)
    assert soddisfa is True
    assert "settore" in spiegazioni[0]


# --- il buco che questo test chiude -----------------------------------------

def test_ogni_criterio_del_backend_e_premibile_in_pagina():
    """Un criterio che esiste e non si puo' premere e' un criterio che non c'e'.

    E' successo due volte: i ricavi anno su anno — che il rigioco misura
    VINCENTI — mancavano in pagina mentre c'era solo il trimestrale, che perde;
    e poi di nuovo con l'accelerazione e il numero di azioni, cioe' il risultato
    piu' forte e meglio campionato di tutto il rigioco.

    Il difetto non si vede da nessuna parte: il backend risponde, i test del
    dominio passano, e la sola conseguenza e' che nessuno puo' usarlo.
    """
    pagina = (Path(config.BASE_DIR).parent / "frontend" / "src"
              / "routes" / "Scanner.svelte").read_text(encoding="utf-8")

    mancanti = sorted(nome for nome in scansione.CRITERI
                      if f'chiave: "{nome}"' not in pagina)

    assert not mancanti, (
        f"questi criteri esistono nel backend e non si possono premere: {mancanti}. "
        f"Vanno aggiunti a CRITERI in routes/Scanner.svelte."
    )


def test_la_finestra_a_un_anno_e_la_stessa_nei_due_posti():
    """Il titolo e la mediana del suo settore devono misurare lo stesso periodo.

    La variazione del singolo titolo la calcola `scansione` su una serie in
    memoria, con `FINESTRA_LUNGA`. La chiusura di un anno fa di TUTTI i titoli
    la porta a casa la query giornaliera, con `UNIVERSE_SESSIONS_IN_YEAR`. Sono
    due numeri in due file diversi, e se divergono non succede niente di
    visibile: escono solo forze relative calcolate su periodi diversi.
    """
    assert config.UNIVERSE_SESSIONS_IN_YEAR == scansione.FINESTRA_LUNGA


# --- la raffica di depositi -------------------------------------------------

def test_la_raffica_e_il_ritmo_recente_sul_solito():
    """Quindici 8-K in tre mesi, contro un'abitudine di uno al mese: 5x."""
    serie = {f"{anno}-{mese:02d}": 1 for anno in (2024, 2025) for mese in range(1, 13)}
    serie.update({"2026-01": 6, "2026-02": 5, "2026-03": 4})

    misura = scansione.depositi(serie, "2026-03")

    assert misura["recenti"] == 15
    assert misura["abitudine"] == pytest.approx(3.0)
    assert misura["raffica"] == pytest.approx(5.0)


def test_senza_abitudine_la_raffica_non_esiste():
    """Un titolo quotato da poco non ha un «solito» da cui scostarsi.

    Non e' zero: e' proprio il caso in cui la misura sarebbe piu' sbagliata, e
    infatti il criterio non passa e il titolo esce dal paragone.
    """
    misura = scansione.depositi({"2026-03": 9}, "2026-03")

    assert misura["raffica"] is None
    assert scansione.misurabile({"depositi": misura},
                                {"depositi_raffica_massima": 2.0}) is False


def test_la_soglia_della_raffica_e_un_massimo():
    """Passa chi NON e' in raffica: e' un criterio che serve a togliere."""
    serie = {f"{anno}-{mese:02d}": 1 for anno in (2024, 2025) for mese in range(1, 13)}
    criteri = {"depositi_raffica_massima": 2.0}

    tranquillo = dict(serie, **{"2026-01": 1, "2026-02": 1, "2026-03": 1})
    in_raffica = dict(serie, **{"2026-01": 4, "2026-02": 4, "2026-03": 4})

    assert scansione.valuta(
        {"depositi": scansione.depositi(tranquillo, "2026-03")}, criteri)[0] is True
    assert scansione.valuta(
        {"depositi": scansione.depositi(in_raffica, "2026-03")}, criteri)[0] is False
