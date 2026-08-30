"""
qualitativa.py — il report a dieci sezioni, in quattro fasi separate.
# feat (Blocco 8): l'analisi che nel vecchio sistema era la piu' usata, rifatta.

Quarantasei referti su sessantanove nel vecchio tradash erano questo. Ed era
anche quella che si bloccava: con tutte le sezioni in un'unica conversazione,
ogni ritentativo riaccodava l'intera cronologia e il contesto cresceva senza
fine — una run e' rimasta ferma venti minuti senza una sola risposta nuova.

Le quattro fasi sono la cura, e sono rimaste: sono conversazioni indipendenti,
ognuna con poche sezioni da scrivere e un contesto che non eredita le altre.
Ma qui non sono nemmeno conversazioni — sono **quattro domande secche**, ognuna
con il suo materiale gia' raccolto. Il modello non ha strumenti da chiamare,
quindi non ha modo di allungare il proprio contesto.

## Cosa vede ogni fase

1. **core** — le sezioni del filing piu' il pannello di metriche: cosa fa
   l'azienda, come spende, che clienti ha, e la classificazione in otto
   dimensioni.
2. **competitiva** — le stesse sezioni piu' il confronto con l'industria, e
   quattro dimensioni. **Senza i documenti dei concorrenti**: il vecchio
   sistema li scaricava, questo dichiara che non li ha.
3. **prospettica** — il commento del management, i dirigenti, l'indice dei
   depositi recenti, e le conclusioni della fase 1 perche' non le contraddica.
4. **citazioni** — le sezioni scritte e i testi sorgente. Ogni citazione viene
   **cercata alla lettera nel testo**: quelle che non si trovano vengono
   scartate, e il referto dice quante.

## Se manca la fonte primaria, si ferma

Senza il testo dell'ultimo 10-K non parte. Non e' rigidita': un report
qualitativo costruito su quello che il modello ricorda dell'azienda ha
esattamente lo stesso aspetto di uno costruito sui documenti.
"""
import json
import logging
import re

import config
from core import llm
from core.tipi import python_puro
from data import defeatbeta, filing_locali, materiale
from data.materiale import AnalisiError
from domain import sezioni_filing, tassonomia

logger = logging.getLogger(__name__)

FORMA_ANNUALE = "10-K"
FORMA_TRIMESTRALE = "10-Q"

# Cosa si legge di ogni documento. Del trimestrale non si rilegge il business:
# non cambia in tre mesi, e sarebbero decine di migliaia di token per riavere
# quello che il 10-K ha gia' detto meglio.
SEZIONI_ANNUALE = ("business", "risk_factors", "mda")
SEZIONI_TRIMESTRALE = ("mda", "risk_factors")

# Le sezioni senza le quali la fase 1 non ha di che scrivere. Le altre si
# possono dichiarare mancanti; queste no.
SEZIONI_PORTANTI = ("business", "mda")

# Le nove sezioni scritte, nell'ordine in cui si leggono nel report.
SEZIONI_SCRITTE = ("business_overview", "cost_structure", "customers_revenue_quality",
                   "competitors", "competitive_advantages", "industry_outlook",
                   "management_governance", "recent_developments", "five_year_narrative")

# Gli spazi non contano nel confronto di una citazione: il modello riavvolge le
# righe, e un a capo in piu' non fa di una frase copiata una frase inventata.
SPAZI = re.compile(r"\s+")


# --- il materiale: le sezioni dei documenti che hai salvato -----------------

def _tronca(testo: str) -> tuple[str, bool]:
    """Una sezione tagliata alla lunghezza utile, e se e' stata tagliata."""
    limite = config.QUALITATIVA_SEZIONE_CARATTERI
    if len(testo) <= limite:
        return testo, False
    return testo[:limite], True


def _sezioni_di(simbolo: str, voce: dict, quali: tuple) -> tuple[list[dict], list[str]]:
    """Le sezioni leggibili di un documento salvato, e cosa non si e' letto."""
    testo, errore = filing_locali.testo(simbolo, voce)
    if testo is None:
        return [], [errore]

    pezzi, avvisi = [], []
    for nome in quali:
        estratto, motivo = sezioni_filing.estrai(testo, nome, voce["form_type"])
        if estratto is None:
            avvisi.append(f"{voce['form_type']} {voce['accession_number']}, "
                          f"sezione {nome}: {motivo}")
            continue
        tagliato, troncata = _tronca(estratto)
        pezzi.append({"document_id": voce["accession_number"],
                      "forma": voce["form_type"], "sezione": nome,
                      "filing_date": voce["filing_date"], "testo": tagliato,
                      "troncata": troncata, "caratteri": len(estratto)})
    return pezzi, avvisi


def _documenti(simbolo: str, run_id: str | None) -> tuple[list[dict], list[str]]:
    """Le sezioni di tutti i documenti utili, e gli avvisi su cosa non c'era.

    L'annuale sempre; il trimestrale solo se e' piu' recente, perche' altrimenti
    ripete quello che il 10-K dice per esteso.
    """
    disponibili = [v for v in filing_locali.richiesti(simbolo, run_id) if v["presente"]]
    annuale = next((v for v in disponibili if v["form_type"] == FORMA_ANNUALE), None)

    if annuale is None:
        raise AnalisiError(
            f"manca il testo dell'ultimo 10-K di {simbolo}. La scheda del titolo "
            f"dice quale documento serve, con che nome salvarlo e dove: "
            f"{filing_locali.cartella(simbolo)}"
        )

    pezzi, avvisi = _sezioni_di(simbolo, annuale, SEZIONI_ANNUALE)
    lette = {p["sezione"] for p in pezzi}
    mancano = [s for s in SEZIONI_PORTANTI if s not in lette]
    if mancano:
        raise AnalisiError(
            f"del 10-K di {simbolo} non si leggono le sezioni portanti "
            f"({', '.join(mancano)}): " + " | ".join(avvisi)
        )

    trimestrali = [v for v in disponibili if v["form_type"] == FORMA_TRIMESTRALE
                   and v["filing_date"] > annuale["filing_date"]]
    if trimestrali:
        recente = max(trimestrali, key=lambda v: v["filing_date"])
        nuovi, altri_avvisi = _sezioni_di(simbolo, recente, SEZIONI_TRIMESTRALE)
        pezzi.extend(nuovi)
        avvisi.extend(altri_avvisi)

    return pezzi, avvisi


def _testo_per_il_modello(pezzi: list[dict], quali: tuple | None = None) -> str:
    """I documenti come li legge il modello, con l'identificativo da citare.

    Il taglio si dichiara nel testo stesso e non solo nei metadati: una sezione
    che finisce a meta' senza dirlo si legge come una sezione che finisce li'.
    """
    scelti = [p for p in pezzi if quali is None or p["sezione"] in quali]
    if not scelti:
        return "nessuna sezione disponibile"

    blocchi = []
    for pezzo in scelti:
        coda = (f"\n\n[…] sezione troncata a {config.QUALITATIVA_SEZIONE_CARATTERI} "
                f"caratteri su {pezzo['caratteri']}") if pezzo["troncata"] else ""
        blocchi.append(
            f"### {pezzo['forma']} — sezione {pezzo['sezione']}\n"
            f"document_id: {pezzo['document_id']} (depositato il {pezzo['filing_date']})\n\n"
            f"{pezzo['testo']}{coda}"
        )
    return "\n\n---\n\n".join(blocchi)


# --- le quattro fasi --------------------------------------------------------

def _chiedi(fase: str, sistema: str, simbolo: str, run_id: str | None,
            richiesta: str) -> tuple[dict, dict]:
    """Una fase: chiede, e ritorna `(contenuto, risposta)`. Non ingoia i rifiuti."""
    risposta = llm.chiedi(fase=f"qualitativa_{fase}", sistema=sistema,
                          messaggio=richiesta, scope=simbolo, run_id=run_id)
    if risposta["rifiutata"]:
        raise AnalisiError(f"il modello ha rifiutato di rispondere alla fase {fase}")
    return materiale.leggi_json(risposta["testo"]), risposta


def _fase1(simbolo: str, roba: dict, run_id: str | None) -> tuple:
    """La narrativa di fondo e le otto dimensioni che descrivono l'azienda."""
    misure, mancanti, rischi = roba["misure"], roba["mancanti"], roba["rischi"]
    quadro, pezzi = roba["quadro"], roba["pezzi"]

    sistema = materiale.prompt(
        "qualitativa_fase1", contesto=quadro,
        vocabolario=tassonomia.vocabolario_leggibile(tassonomia.DIMENSIONI_FASE1),
        documenti=_testo_per_il_modello(pezzi),
        misure=json.dumps({"metriche": misure, "segnali_di_rischio": rischi,
                           "metriche_non_disponibili": mancanti},
                          indent=2, ensure_ascii=False),
    )
    contenuto, risposta = _chiedi("fase1", sistema, simbolo, run_id,
                                  f"Scrivi la fase 1 del report qualitativo di {simbolo}.")
    return {**contenuto, "metriche": misure, "metriche_mancanti": mancanti,
            "segnali": rischi}, risposta


def _fase2(simbolo: str, roba: dict, run_id: str | None) -> tuple:
    """Il posizionamento competitivo, senza i documenti dei concorrenti."""
    quadro, pezzi = roba["quadro"], roba["pezzi"]
    con_settore = {nome: dati for nome, dati in roba["misure"].items()
                   if dati and dati.get("settore") is not None}

    sistema = materiale.prompt(
        "qualitativa_fase2", contesto=quadro,
        vocabolario=tassonomia.vocabolario_leggibile(tassonomia.DIMENSIONI_FASE2),
        documenti=_testo_per_il_modello(pezzi, ("business", "risk_factors")),
        misure=(json.dumps(con_settore, indent=2, ensure_ascii=False) if con_settore
                else "nessuna metrica ha un confronto di industria disponibile"),
    )
    contenuto, risposta = _chiedi("fase2", sistema, simbolo, run_id,
                                  f"Scrivi la fase 2 del report qualitativo di {simbolo}.")
    return {**contenuto, "confronto_industria": con_settore}, risposta


def _dirigenti(simbolo: str, run_id: str | None) -> str:
    """Il vertice dell'azienda, o perche' non c'e'."""
    lettura = defeatbeta.officers(simbolo, run_id=run_id)
    if not lettura.available:
        return f"non disponibili: {lettura.reason}"

    righe = [{c: python_puro(riga[c]) for c in lettura.frame.columns if c != "symbol"}
             for _, riga in lettura.frame.iterrows()]
    return json.dumps(righe, indent=2, ensure_ascii=False)


def _depositi_recenti(simbolo: str, run_id: str | None) -> str:
    """L'indice dei depositi recenti: tipo e data, non il testo."""
    lettura = defeatbeta.sec_filings(simbolo, run_id=run_id)
    if not lettura.available:
        return f"non disponibile: {lettura.reason}"

    voci = [{"form_type": python_puro(r.get("form_type")),
             "filing_date": str(python_puro(r.get("filing_date")) or "")[:10],
             "document_id": python_puro(r.get("accession_number"))}
            for _, r in lettura.frame.head(config.QUALITATIVA_DEPOSITI_RECENTI).iterrows()]
    return json.dumps(voci, indent=2, ensure_ascii=False)


def _fase3(simbolo: str, roba: dict, prima: dict, run_id: str | None) -> tuple:
    """Governance, sviluppi recenti e i cinque anni davanti."""
    conclusioni = {chiave: prima.get(chiave) for chiave in
                   ("thesis", "bull_case", "bear_case", "key_risks")}
    conclusioni["stato_corrente"] = (prima.get("classificazione") or {}).get("stato_corrente")

    sistema = materiale.prompt(
        "qualitativa_fase3", contesto=roba["quadro"],
        documenti=_testo_per_il_modello(roba["pezzi"], ("mda",)),
        dirigenti=roba["dirigenti"],
        depositi=roba["depositi"],
        fase1=json.dumps(conclusioni, indent=2, ensure_ascii=False),
    )
    return _chiedi("fase3", sistema, simbolo, run_id,
                   f"Scrivi la fase 3 del report qualitativo di {simbolo}.")


def _fase4(simbolo: str, scritte: dict, pezzi: list[dict], run_id: str | None) -> tuple:
    """Le citazioni, e la verifica che siano davvero nel testo."""
    sistema = materiale.prompt(
        "qualitativa_fase4",
        sezioni=json.dumps(scritte, indent=2, ensure_ascii=False),
        documenti=_testo_per_il_modello(pezzi),
    )
    contenuto, risposta = _chiedi("fase4", sistema, simbolo, run_id,
                                  f"Trova le citazioni per il report di {simbolo}.")

    verificate, scartate = verifica_citazioni(contenuto.get("citations") or [], pezzi)
    return {**contenuto, "citations": verificate, "citazioni_scartate": scartate}, risposta


def verifica_citazioni(citazioni: list, pezzi: list[dict]) -> tuple[list, list]:
    """Tiene solo le citazioni presenti alla lettera in un documento fornito.

    E' il controllo che rende diverso questo passaggio da una parafrasi: una
    frase che il modello ricostruisce a memoria assomiglia moltissimo a una
    citata, e l'unico modo di distinguerle e' cercarla.
    """
    testi = {}
    for pezzo in pezzi:
        testi.setdefault(pezzo["document_id"], []).append(SPAZI.sub(" ", pezzo["testo"]))

    buone, scartate = [], []
    for citazione in citazioni:
        if not isinstance(citazione, dict):
            continue
        frase = SPAZI.sub(" ", str(citazione.get("quote") or "")).strip()
        documento = str(citazione.get("document_id") or "")
        dove = testi.get(documento, [])

        if frase and any(frase in testo for testo in dove):
            buone.append(citazione)
        elif not dove:
            scartate.append({**citazione, "motivo": f"document_id {documento!r} "
                                                    f"non e' fra i testi forniti"})
        else:
            scartate.append({**citazione, "motivo": "la frase non compare nel documento"})

    return buone, scartate


# --- il report intero -------------------------------------------------------

def _riepilogo(pezzi: list[dict], avvisi: list[str], scartate: list) -> dict:
    """Cosa e' stato letto e cosa e' stato tagliato. Sempre nel referto.

    Si chiama `copertura` e non `lettura` perche' negli altri referti `lettura`
    e' la prosa del modello, e il frontend la stampa come tale: due significati
    sotto lo stesso nome sarebbero finiti a schermo come un oggetto vuoto.
    """
    return {
        "documenti_letti": sorted({f"{p['forma']} {p['document_id']}" for p in pezzi}),
        "sezioni_lette": [f"{p['forma']}/{p['sezione']}" for p in pezzi],
        "sezioni_troncate": [f"{p['forma']}/{p['sezione']}" for p in pezzi if p["troncata"]],
        "sezioni_non_lette": avvisi,
        "citazioni_scartate": len(scartate),
        "fonti_non_disponibili": [
            "i documenti dei concorrenti: il confronto competitivo poggia su "
            "quanto l'azienda dice di loro nei propri documenti",
            "il proxy statement (DEF 14A): consiglio, compensi deliberati e "
            "classi di voto non sono nel perimetro",
            "le transazioni degli insider: Defeatbeta non le porta",
        ],
    }


def raccogli(simbolo: str, run_id: str | None) -> dict:
    """Tutto il materiale delle quattro fasi, **prima** di spendere il primo token.

    Non e' ordine: e' il difetto che ha fatto pagare due volte le stesse due
    fasi. Il materiale della terza fase — l'elenco dei dirigenti — conteneva un
    valore che `json.dumps` rifiutava, e l'analisi e' andata a sbattere li',
    dopo che la prima e la seconda erano gia' state chiamate e pagate. Due
    volte, perche' la seconda volta il server girava ancora col codice vecchio.

    Raccogliere tutto prima sposta quel guasto **prima della prima chiamata**,
    dove non costa niente. Le sole cose che non si possono preparare in anticipo
    sono i pezzi che dipendono dalle risposte: le conclusioni della fase 1 per la
    terza, le sezioni scritte per la quarta.

    Il `json.dumps` qui sotto non e' decorativo: e' il controllo. Se qualcosa non
    e' serializzabile, si scopre adesso.
    """
    pezzi, avvisi = _documenti(simbolo, run_id)
    misure, mancanti = materiale.pannello_metriche(simbolo, run_id)
    roba = {
        "pezzi": pezzi,
        "avvisi": avvisi,
        "quadro": materiale.contesto(simbolo, run_id),
        "misure": misure,
        "mancanti": mancanti,
        "rischi": materiale.segnali_fondamentali(simbolo, run_id),
        "dirigenti": _dirigenti(simbolo, run_id),
        "depositi": _depositi_recenti(simbolo, run_id),
    }

    try:
        json.dumps(roba, ensure_ascii=False)
    except TypeError as exc:
        raise AnalisiError(
            f"il materiale per l'analisi di {simbolo} non e' utilizzabile: {exc}. "
            f"Nessuna chiamata al modello e' stata fatta"
        ) from exc

    return roba


def esegui(simbolo: str, lavoro) -> dict:
    """Le quattro fasi, in fila, dentro un lavoro che si puo' fermare fra l'una
    e l'altra. Ritorna il referto completo col costo di tutte e quattro."""
    run_id = lavoro.run_id
    roba = raccogli(simbolo, run_id)
    pezzi, avvisi = roba["pezzi"], roba["avvisi"]
    costo = 0.0

    prima, risposta = _fase1(simbolo, roba, run_id)
    costo += risposta["costo_usd"]
    lavoro.advance(detail="fase 1 di 4: narrativa di fondo")

    seconda, risposta = _fase2(simbolo, roba, run_id)
    costo += risposta["costo_usd"]
    lavoro.advance(detail="fase 2 di 4: posizionamento competitivo")

    terza, risposta = _fase3(simbolo, roba, prima, run_id)
    costo += risposta["costo_usd"]
    lavoro.advance(detail="fase 3 di 4: governance e prospettive")

    unito = {**prima, **seconda, **terza}
    scritte = {nome: unito.get(nome) for nome in SEZIONI_SCRITTE if unito.get(nome)}
    quarta, risposta = _fase4(simbolo, scritte, pezzi, run_id)
    costo += risposta["costo_usd"]
    lavoro.advance(detail="fase 4 di 4: citazioni verificate")

    classificazione, scarti = tassonomia.valida(
        {**(prima.get("classificazione") or {}), **(seconda.get("classificazione") or {})}
    )
    contenuto = {**unito, **quarta, "classificazione": classificazione,
                 "classificazione_scartata": scarti,
                 "copertura": _riepilogo(pezzi, avvisi, quarta["citazioni_scartate"])}

    return {"contenuto": contenuto, "modello": risposta["modello"], "costo_usd": costo}
