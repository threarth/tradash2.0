"""
test_spinoff.py — l'elenco degli spin-off: si legge, e non parte da solo.
# feat: l'unico dato che non viene da Defeatbeta.

Due proprieta' contano piu' delle altre. La prima: **niente parte da solo** —
leggere l'elenco non lo scarica, e senza premere non si tocca la rete (la suite
lo garantisce da se': i socket sono spenti, e un fetch non voluto qui
fallirebbe rumorosamente). La seconda: **un elenco buono non si perde** —
se la pagina cambia forma e non si legge piu' niente, il file di prima resta
dov'e' invece di essere sostituito da un elenco vuoto.
"""
import json
from datetime import date, timedelta

import pytest

import config
from core.db import db_read
from data import spinoff_elenco
from data.spinoff_elenco import SpinoffError
from domain import spinoff_segnali as segnali

# Un pezzo VERO della pagina di stockanalysis, preso il 04/09/2026. I commenti
# `<!--[-->` sono suoi: la pagina e' generata da Svelte e ne e' piena, e un
# lettore che inciampasse li' dentro leggerebbe zero righe da una pagina buona.
PAGINA = """
<table class="svelte-mfd49r"><thead><tr>
<th>Date</th><th>Parent</th><th>New Stock</th><th>Parent Company</th><th>New Company</th>
</tr></thead><tbody><!--[!--><!--[-->
<tr class="svelte-mfd49r"><!--[--><!--[!-->
<td class="svelte-mfd49r">Aug 4, 2026</td><!--]-->
<td class="svelte-mfd49r"><!----><a href="/stocks/rezi/" >REZI</a><!----></td>
<td class="svelte-mfd49r"><!----><a href="/stocks/adig/" >ADIG</a><!----></td>
<td class="svelte-mfd49r">Resideo Technologies Inc</td>
<td class="svelte-mfd49r">Adi Global Distribution Inc</td><!--]--></tr>
<tr><td>Feb 21, 2025</td><td><a href="/stocks/wdc/">WDC</a></td>
<td><a href="/stocks/sndk/">SNDK</a></td>
<td>Western Digital Corp</td><td>Sandisk Corp</td></tr>
<tr><td>data che non si legge</td><td><a href="/stocks/x/">X</a></td>
<td><a href="/stocks/y/">Y</a></td><td>X Inc</td><td>Y Inc</td></tr>
<tr><td>Jan 2, 2026</td><td>Z</td><td></td><td>Z Inc</td><td></td></tr>
</tbody></table>
"""


def test_la_pagina_vera_si_legge_nonostante_i_suoi_commenti():
    righe = spinoff_elenco.analizza(PAGINA)

    assert [r["symbol"] for r in righe] == ["ADIG", "SNDK"]
    assert righe[1] == {"symbol": "SNDK", "data": "2025-02-21", "parent": "WDC",
                        "nome": "Sandisk Corp", "nome_parent": "Western Digital Corp"}


def test_una_riga_senza_data_o_senza_simbolo_si_scarta():
    """Sono i due dati per cui l'elenco esiste: una riga a meta' e' un candidato
    che non si puo' ne' cercare ne' datare."""
    simboli = [r["symbol"] for r in spinoff_elenco.analizza(PAGINA)]

    assert "Y" not in simboli, "la riga con la data illeggibile"
    assert "" not in simboli, "la riga senza il simbolo della nata"


def test_una_pagina_di_forma_diversa_da_zero_righe_non_righe_sbagliate():
    assert spinoff_elenco.analizza("<html><p>ci siamo rifatti il sito</p></html>") == []


def test_senza_elenco_lo_dice_e_dice_cosa_fare():
    """Regola 5: l'assenza si dichiara, col motivo e con l'azione."""
    stato = spinoff_elenco.elenco()

    assert stato["disponibile"] is False
    assert stato["righe"] == []
    assert "mai stato scaricato" in stato["motivo"]
    assert "premi" in stato["azione"], "dice cosa fare, non solo cosa manca"


def test_l_elenco_salvato_dice_quando_e_stato_preso():
    """Un elenco di tre mesi fa non e' sbagliato: e' incompleto, e va saputo."""
    config.SPINOFF_PATH.write_text(json.dumps({
        "versione": config.SPINOFF_FILE_VERSION,
        "preso_il": "2026-09-04T10:00:00+00:00",
        "righe": [{"symbol": "SNDK", "data": "2025-02-21", "parent": "WDC"}],
    }), encoding="utf-8")

    stato = spinoff_elenco.elenco()

    assert stato["disponibile"] is True
    assert stato["preso_il"] == "2026-09-04T10:00:00+00:00"
    assert stato["righe"][0]["symbol"] == "SNDK"


def test_un_file_illeggibile_lo_dichiara_invece_di_esplodere():
    config.SPINOFF_PATH.write_text("{non e' json", encoding="utf-8")

    stato = spinoff_elenco.elenco()

    assert stato["disponibile"] is False
    assert "non e' leggibile" in stato["motivo"]


def test_zero_righe_lette_non_cancellano_l_elenco_di_prima(monkeypatch):
    """Sostituire un elenco buono con uno vuoto sarebbe perdere l'unica cosa che
    questo modulo non sa ricostruire."""
    prima = json.dumps({"versione": 1, "preso_il": "2026-01-01T00:00:00+00:00",
                        "righe": [{"symbol": "SNDK", "data": "2025-02-21"}]})
    config.SPINOFF_PATH.write_text(prima, encoding="utf-8")
    monkeypatch.setattr(spinoff_elenco, "_scarica",
                        lambda anno, run_id: "<html>niente tabelle</html>")

    with pytest.raises(SpinoffError, match="cambiato forma"):
        spinoff_elenco.aggiorna()

    assert config.SPINOFF_PATH.read_text(encoding="utf-8") == prima


def test_un_anno_che_non_risponde_non_fa_perdere_l_altro(monkeypatch):
    """Si prende quello che c'e' e si dice cosa manca."""
    def _finta(anno, run_id):
        if anno % 2 == 0:
            raise SpinoffError(f"pagina {anno} non risponde: TimeoutError")
        return PAGINA

    monkeypatch.setattr(spinoff_elenco, "_scarica", _finta)

    esito = spinoff_elenco.aggiorna()

    assert esito["righe"] == 2
    assert len(esito["falliti"]) == 1
    assert "non risponde" in esito["falliti"][0]["motivo"]
    assert spinoff_elenco.elenco()["disponibile"] is True


def test_lo_stesso_simbolo_su_due_pagine_resta_uno(monkeypatch):
    monkeypatch.setattr(spinoff_elenco, "_scarica", lambda anno, run_id: PAGINA)

    esito = spinoff_elenco.aggiorna()

    assert esito["righe"] == 2, "due anni uguali, non quattro righe"
    assert [r["symbol"] for r in spinoff_elenco.elenco()["righe"]] == ["ADIG", "SNDK"], \
        "e restano ordinate dalla piu' recente"


def test_l_aggiornamento_lascia_la_sua_riga_nel_registro_dei_lavori(monkeypatch):
    """E' una lettura di rete come le altre: si vede e si puo' fermare."""
    monkeypatch.setattr(spinoff_elenco, "_scarica", lambda anno, run_id: PAGINA)

    spinoff_elenco.aggiorna()

    with db_read() as conn:
        lavori = [dict(r) for r in conn.execute("SELECT * FROM jobs")]

    assert [riga["kind"] for riga in lavori] == [spinoff_elenco.JOB_KIND]
    assert lavori[0]["status"] == "done"


def test_le_route(client, monkeypatch):
    vuoto = client.get("/api/spinoff").get_json()["data"]
    assert vuoto["disponibile"] is False and vuoto["azione"]

    monkeypatch.setattr(spinoff_elenco, "_scarica", lambda anno, run_id: PAGINA)
    aggiornato = client.post("/api/spinoff/aggiorna").get_json()["data"]
    assert aggiornato["righe"] == 2

    letto = client.get("/api/spinoff").get_json()["data"]
    assert [r["symbol"] for r in letto["righe"]] == ["ADIG", "SNDK"]


def test_una_pagina_che_non_risponde_e_un_400_col_motivo(client, monkeypatch):
    """Non e' un guasto del server: e' una pagina che non ha risposto."""
    def _esplode(anno, run_id):
        raise SpinoffError("stockanalysis.com non risponde: TimeoutError")

    monkeypatch.setattr(spinoff_elenco, "_scarica", _esplode)

    risposta = client.post("/api/spinoff/aggiorna")

    assert risposta.status_code == 400
    assert "non risponde" in risposta.get_json()["error"]


# --- i sei segnali, e le tre guardie trovate facendoli girare ---------------
#
# Il modello sulla carta sembrava a posto. Le tre cose qui sotto sono venute
# fuori solo misurando davvero i ventisette candidati dell'elenco vero.

SPIN = "2025-06-30"
OGGI = date(2026, 9, 5)


def _barre(quante: int, prezzo=lambda i: 100.0, volume=lambda i: 1000.0,
           dal=date(2025, 7, 1)) -> list[dict]:
    """Sedute consecutive, una al giorno: al dominio il calendario non serve."""
    return [{"data": (dal + timedelta(days=i)).isoformat(),
             "chiusura": prezzo(i), "volume": volume(i)} for i in range(quante)]


def test_un_segnale_non_calcolabile_esce_dal_denominatore():
    """«Non lo so» e «va male» non sono lo stesso numero: e' il difetto peggiore
    del modulo vecchio, dove un dato mancante valeva zero."""
    esito = segnali.segnali(_barre(10), {}, SPIN, oggi=OGGI)
    conto = segnali.punteggio(esito)

    assert esito["ricavi"]["quota"] is None
    assert conto["disponibili"] < sum(segnali.PESI.values())
    assert conto["calcolabili"] < conto["totali"]
    assert segnali.stato(esito) == segnali.TROPPO_PRESTO


def test_i_trimestri_chiusi_prima_dello_spin_non_si_guardano():
    """Guardia 2. MFP dava un EPS da 270,80 a 0,26: cifre per azione di una
    societa' che ancora non esisteva."""
    periodi = ["2024-12-31", "2025-03-31", "2025-09-30", "2025-12-31"]

    utili = segnali.trimestri_utili(periodi, SPIN, oggi=OGGI)

    assert utili == ["2025-09-30", "2025-12-31"], "solo quelli chiusi dopo la separazione"


def test_con_un_solo_trimestre_dopo_lo_spin_non_si_misura_niente():
    """Non e' un titolo che va male: e' un titolo su cui non si puo' dire nulla."""
    voci = {"total_revenue": {"2025-03-31": 100.0, "2025-09-30": 200.0}}

    esito = segnali.segnali(_barre(200), voci, SPIN, oggi=OGGI)

    assert esito["ricavi"]["quota"] is None
    assert "ne servono 2" in esito["ricavi"]["nota"]
    assert segnali.stato(esito) == segnali.TROPPO_PRESTO


def test_una_storia_che_comincia_prima_dello_spin_si_dichiara():
    """Guardia 1. Contati dai prezzi, NVRI dava 381 mesi e ANGI 178: quei ticker
    non sono nuovi, hanno ereditato la storia della madre."""
    assert segnali.storia_precedente("2010-01-04", SPIN) is True
    # Undici giorni di scambi when-issued prima della data ufficiale: e' il caso
    # di SNDK, ed e' normale.
    assert segnali.storia_precedente("2025-06-19", SPIN) is False
    assert segnali.storia_precedente(None, SPIN) is False


def test_i_mesi_si_contano_dallo_spin_non_dalla_prima_seduta():
    assert segnali.mesi_dallo_spin("2026-06-05", oggi=OGGI) == pytest.approx(3.0, abs=0.1)


def test_un_titolo_che_non_si_scambia_piu_non_si_giudica():
    """Guardia 3. TWNPQ segnava zero ovunque: la Q finale e' il suffisso delle
    bancarotte, e un punteggio li' sopra e' un numero che sembra un giudizio."""
    sotto_il_centesimo = _barre(5, prezzo=lambda i: 0.0001, dal=date(2026, 9, 1))
    fermo_da_un_pezzo = _barre(5, dal=date(2025, 7, 1))

    assert "centesimo" in segnali.fermo(sotto_il_centesimo, oggi=OGGI), \
        "TWNPQ era quotato ogni giorno, a 0,0001: si vede solo dal prezzo"
    assert "nessun prezzo dal" in segnali.fermo(fermo_da_un_pezzo, oggi=OGGI)
    assert segnali.fermo([], oggi=OGGI) == "nessun prezzo"
    assert segnali.fermo(_barre(5, dal=date(2026, 9, 1)), oggi=OGGI) is None


def test_il_volume_confronta_l_ultimo_mese_coi_tre_prima():
    """E' il segnale che su SanDisk si e' acceso per primo, un mese prima che i
    bilanci dicessero qualcosa. Per questo pesa 25 e non 5."""
    def salita(i):
        return 1000.0 if i < 90 else 3000.0

    esito = segnali.segnali(_barre(120, volume=salita, dal=date(2026, 5, 9)), {},
                            SPIN, oggi=OGGI)

    assert esito["volume"]["quota"] == 1.0
    assert "+" in esito["volume"]["nota"]


def test_il_punteggio_dice_su_quanti_segnali_e_stato_calcolato():
    voci = {"total_revenue": {"2025-09-30": 100.0, "2025-12-31": 130.0},
            "gross_profit": {"2025-09-30": 30.0, "2025-12-31": 52.0},
            "diluted_eps": {"2025-09-30": 0.10, "2025-12-31": 0.40}}

    barre = _barre(200, prezzo=lambda i: 100.0 + i,
                   volume=lambda i: 1000.0 if i < 170 else 4000.0, dal=date(2026, 2, 17))

    esito = segnali.segnali(barre, voci, SPIN, oggi=OGGI)
    conto = segnali.punteggio(esito)

    assert conto["presi"] == conto["disponibili"], "tutti i segnali calcolabili sono pieni"
    assert conto["disponibili"] == sum(segnali.PESI.values()), "e sono tutti e sei"
    assert conto["quota"] == 1.0
    assert segnali.stato(esito) == segnali.NUMERI_GIRATI


def test_i_fondamentali_accesi_col_volume_girato_sono_raffreddamento():
    """E' lo stato che su SanDisk ha anticipato il calo: bilanci al massimo,
    volume che si gira, e da li' il prezzo ha fatto -8%."""
    voci = {"total_revenue": {"2025-09-30": 100.0, "2025-12-31": 130.0},
            "gross_profit": {"2025-09-30": 30.0, "2025-12-31": 52.0},
            "diluted_eps": {"2025-09-30": 0.10, "2025-12-31": 0.40}}

    def discesa(i):
        return 3000.0 if i < 90 else 800.0

    esito = segnali.segnali(_barre(120, volume=discesa, dal=date(2026, 5, 9)),
                            voci, SPIN, oggi=OGGI)

    assert esito["volume"]["quota"] == 0.0
    assert segnali.stato(esito) == segnali.IN_RAFFREDDAMENTO


def test_senza_elenco_il_calcolo_non_parte_e_lo_dice_subito():
    """Un errore sollevato dentro al thread non tornerebbe a chi ha premuto:
    resterebbe ad aspettare un run_id che non arriva mai."""
    with pytest.raises(SpinoffError, match="Aggiorna l'elenco"):
        spinoff_elenco.calcola_in_background()


def test_la_rotta_del_calcolo_senza_elenco_e_un_400(client):
    risposta = client.post("/api/spinoff/calcola")

    assert risposta.status_code == 400
    assert "elenco" in risposta.get_json()["error"]
