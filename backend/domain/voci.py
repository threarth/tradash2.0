"""
voci.py — come si chiamano in italiano le voci di bilancio, e cosa vogliono dire.
# feat: i nomi di Defeatbeta sono inglesi e criptici; qui c'e' la traduzione.

`selling_gen_admin` e `total_liabilities_net_minority_interest` sono i nomi con
cui il dato arriva, e restano: sono la chiave con cui si cerca, si confronta col
bilancio depositato, si scrive un'analisi. Ma non sono nomi da leggere in una
tabella.

**Il nome originale non sparisce mai.** L'etichetta italiana gli sta accanto, non
al posto suo: chi confronta con l'originale deve poter trovare la stessa parola,
e chi legge deve capire cosa sta guardando. Sono due bisogni diversi e nessuno
dei due si sacrifica.

Le voci che questo dizionario non conosce non diventano un buco: restano col
loro nome, con i trattini bassi sostituiti da spazi, ed e' esattamente cio' che
si vedeva prima. Un dizionario incompleto peggiora niente.

## Perche' sta in domain/

Non legge niente e non scrive niente: e' una tabella. La usano l'API dei
fondamentali (per l'etichetta accanto al nome) e il glossario (per generare una
voce per ognuna).
"""

# Nome di Defeatbeta -> (etichetta italiana, che cosa e').
#
# Le spiegazioni sono in una riga: qui serve capire cosa si sta guardando, non
# studiare il principio contabile. Chi vuole il resto apre il glossario.

CONTO_ECONOMICO = {
    "total_revenue": ("Ricavi totali", "Tutto quello che l'azienda ha fatturato nel periodo."),
    "operating_revenue": (
        "Ricavi operativi",
        "I ricavi dell'attivita' vera e propria, senza le poste straordinarie."),
    "cost_of_revenue": ("Costo del venduto", "Quanto e' costato produrre cio' che si e' venduto."),
    "reconciled_cost_of_revenue": (
        "Costo del venduto riconciliato",
        "Il costo del venduto riportato allo schema standard del fornitore."),
    "gross_profit": (
        "Margine lordo",
        "Ricavi meno costo del venduto: quanto resta prima di tutto il resto."),
    "operating_expense": (
        "Spese operative",
        "Ricerca, vendita, amministrazione: il costo di far funzionare l'azienda."),
    "research_and_development": (
        "Ricerca e sviluppo",
        "Quanto si spende per costruire i prodotti di domani."),
    "selling_gen_admin": (
        "Spese di vendita e amministrative",
        "Forza vendita, marketing, struttura amministrativa."),
    "operating_income": (
        "Reddito operativo",
        "Il guadagno del MESTIERE, prima di finanza e imposte."),
    "total_operating_income_as_reported": (
        "Reddito operativo dichiarato",
        "Il reddito operativo come lo scrive l'azienda nel proprio bilancio."),
    "ebit": (
        "EBIT",
        "Utile prima di interessi e imposte. Comprende anche i proventi NON operativi."),
    "ebitda": (
        "EBITDA",
        "EBIT piu' ammortamenti: quanto genera il conto economico prima delle "
        "poste che non escono di cassa."),
    "normalized_ebitda": (
        "EBITDA normalizzato",
        "L'EBITDA senza le voci straordinarie, per confrontare periodi diversi."),
    "normalized_income": ("Utile normalizzato", "L'utile senza le voci straordinarie."),
    "other_income_expense": (
        "Altri proventi e oneri",
        "Quello che entra o esce fuori dall'attivita' principale."),
    "other_non_operating_income_expenses": (
        "Altri proventi non operativi",
        "Poste che non c'entrano col mestiere dell'azienda."),
    "interest_expense": ("Oneri finanziari", "Quanto costano gli interessi sul debito."),
    "interest_expense_non_operating": (
        "Oneri finanziari non operativi",
        "Gli interessi che non nascono dall'attivita' caratteristica."),
    "interest_income": (
        "Proventi finanziari",
        "Gli interessi incassati sulla liquidita' e sugli investimenti."),
    "interest_income_non_operating": (
        "Proventi finanziari non operativi",
        "Interessi attivi fuori dall'attivita' caratteristica."),
    "net_interest_income": ("Saldo degli interessi", "Interessi incassati meno interessi pagati."),
    "net_non_operating_interest_income_expense": (
        "Saldo interessi non operativi",
        "Lo stesso saldo, limitato alle poste non operative."),
    "pretax_income": ("Utile ante imposte", "Quanto si e' guadagnato prima di pagare le tasse."),
    "tax_provision": ("Imposte", "Le tasse di competenza del periodo."),
    "tax_rate_for_calcs": (
        "Aliquota usata nei calcoli",
        "L'aliquota fiscale con cui il fornitore fa i suoi conti."),
    "tax_effect_of_unusual_items": (
        "Effetto fiscale delle poste straordinarie",
        "Quanta imposta e' attribuibile alle voci non ricorrenti."),
    "net_income": ("Utile netto", "Quello che resta alla fine, dopo tutto."),
    "net_income_common_stockholders": (
        "Utile netto agli azionisti ordinari",
        "L'utile che spetta a chi ha azioni ordinarie, tolti i privilegiati."),
    "net_income_continuous_operations": (
        "Utile delle attivita' continuative",
        "L'utile prodotto da cio' che l'azienda continuera' a fare."),
    "net_income_continuous_operations_net_minority_interest": (
        "Utile continuativo netto delle minoranze",
        "Come sopra, tolta la quota dei soci di minoranza."),
    "net_income_from_continuing_operation_net_minority_interest": (
        "Utile continuativo, netto minoranze",
        "L'utile delle attivita' che proseguono, senza la quota dei terzi."),
    "net_income_from_continuing_and_discontinued_operation": (
        "Utile da attivita' continuative e cessate",
        "Tutto l'utile, comprese le attivita' che si stanno chiudendo."),
    "net_income_including_noncontrolling_interests": (
        "Utile comprese le minoranze",
        "L'utile totale, compresa la parte dei soci di minoranza."),
    "diluted_ni_availto_com_stockholders": (
        "Utile diluito agli azionisti ordinari",
        "L'utile per il calcolo dell'EPS diluito."),
    "basic_eps": ("Utile per azione (base)", "Utile netto diviso le azioni in circolazione."),
    "diluted_eps": (
        "Utile per azione (diluito)",
        "Come sopra, contando anche le azioni che POTREBBERO nascere da opzioni e conversioni."),
    "basic_average_shares": ("Azioni medie (base)", "Quante azioni c'erano in media nel periodo."),
    "diluted_average_shares": (
        "Azioni medie (diluite)",
        "Le azioni medie, comprese quelle potenziali."),
    "reconciled_depreciation": (
        "Ammortamenti riconciliati",
        "Gli ammortamenti riportati allo schema standard del fornitore."),
    "total_expenses": ("Costi totali", "Tutti i costi del periodo messi insieme."),
    "special_income_charges": (
        "Oneri e proventi straordinari",
        "Voci una tantum: ristrutturazioni, cause, svalutazioni."),
    "restructuring_and_mergern_acquisition": (
        "Ristrutturazioni e acquisizioni",
        "I costi delle riorganizzazioni e delle operazioni straordinarie."),
    "total_unusual_items": (
        "Poste straordinarie",
        "Tutto cio' che non si ripetera' l'anno prossimo."),
    "total_unusual_items_excluding_goodwill": (
        "Poste straordinarie, escluso l'avviamento",
        "Le straordinarie senza le svalutazioni di avviamento."),
}

STATO_PATRIMONIALE = {
    "total_assets": ("Attivo totale", "Tutto quello che l'azienda possiede."),
    "current_assets": ("Attivo corrente", "Cio' che diventa cassa entro un anno."),
    "total_non_current_assets": ("Attivo non corrente", "Cio' che resta in azienda oltre l'anno."),
    "cash_and_cash_equivalents": ("Cassa e equivalenti", "Il denaro subito disponibile."),
    "cash_cash_equivalents_and_short_term_investments": (
        "Cassa e investimenti a breve",
        "Denaro piu' cio' che si liquida in fretta."),
    "other_short_term_investments": (
        "Altri investimenti a breve",
        "Impieghi di liquidita' a scadenza ravvicinata."),
    "restricted_cash": ("Cassa vincolata", "Denaro che c'e' ma non si puo' usare liberamente."),
    "available_for_sale_securities": (
        "Titoli disponibili per la vendita",
        "Investimenti che si possono cedere quando serve."),
    "investmentin_financial_assets": (
        "Investimenti in attivita' finanziarie",
        "Quanto e' impiegato in strumenti finanziari."),
    "investments_and_advances": (
        "Investimenti e anticipi",
        "Partecipazioni e somme anticipate a terzi."),
    "other_investments": (
        "Altri investimenti",
        "Impieghi che non rientrano nelle altre categorie."),
    "accounts_receivable": ("Crediti verso clienti", "Quanto i clienti devono ancora pagare."),
    "receivables": ("Crediti", "Tutti i crediti a breve, clienti compresi."),
    "non_current_accounts_receivable": (
        "Crediti oltre l'anno",
        "Crediti che si incasseranno dopo dodici mesi."),
    "inventory": ("Magazzino", "Il valore di cio' che e' in giacenza."),
    "raw_materials": ("Materie prime", "La parte di magazzino non ancora lavorata."),
    "work_in_process": ("Semilavorati", "La parte di magazzino in corso di lavorazione."),
    "finished_goods": ("Prodotti finiti", "La parte di magazzino pronta per la vendita."),
    "prepaid_assets": ("Risconti attivi", "Costi gia' pagati che competono a periodi futuri."),
    "non_current_prepaid_assets": (
        "Risconti attivi oltre l'anno",
        "Costi anticipati di competenza pluriennale."),
    "other_current_assets": (
        "Altre attivita' correnti",
        "Attivita' a breve che non rientrano altrove."),
    "other_non_current_assets": (
        "Altre attivita' non correnti",
        "Attivita' durevoli che non rientrano altrove."),
    "gross_ppe": (
        "Immobilizzazioni materiali lorde",
        "Impianti e fabbricati al costo, prima degli ammortamenti."),
    "net_ppe": (
        "Immobilizzazioni materiali nette",
        "Impianti e fabbricati al netto degli ammortamenti."),
    "accumulated_depreciation": ("Fondo ammortamento", "Quanto e' stato ammortizzato finora."),
    "land_and_improvements": (
        "Terreni e migliorie",
        "Il valore dei terreni e delle opere su di essi."),
    "buildings_and_improvements": ("Fabbricati e migliorie", "Il valore degli immobili."),
    "machinery_furniture_equipment": (
        "Impianti, macchinari e attrezzature",
        "I beni strumentali della produzione."),
    "construction_in_progress": (
        "Immobilizzazioni in corso",
        "Investimenti iniziati e non ancora finiti."),
    "other_properties": ("Altri immobili", "Beni immobili che non rientrano nelle altre voci."),
    "properties": ("Immobili", "Il valore complessivo degli immobili."),
    "goodwill": (
        "Avviamento",
        "Quanto si e' pagato in piu' del valore contabile, comprando un'altra azienda."),
    "other_intangible_assets": (
        "Altre immobilizzazioni immateriali",
        "Brevetti, marchi, software capitalizzato."),
    "goodwill_and_other_intangible_assets": (
        "Avviamento e immateriali",
        "Avviamento piu' le altre attivita' senza corpo fisico."),
    "net_tangible_assets": ("Attivo tangibile netto", "L'attivo tolti gli immateriali e i debiti."),
    "tangible_book_value": (
        "Patrimonio netto tangibile",
        "Il patrimonio netto senza avviamento e immateriali."),
    "non_current_deferred_assets": (
        "Attivita' differite oltre l'anno",
        "Poste il cui beneficio si manifestera' in futuro."),
    "non_current_deferred_taxes_assets": (
        "Imposte anticipate",
        "Tasse gia' pagate che ridurranno il carico futuro."),
    "total_liabilities_net_minority_interest": (
        "Passivo totale",
        "Tutto quello che l'azienda deve."),
    "current_liabilities": ("Passivo corrente", "I debiti da pagare entro un anno."),
    "total_non_current_liabilities_net_minority_interest": (
        "Passivo non corrente",
        "I debiti oltre i dodici mesi."),
    "accounts_payable": ("Debiti verso fornitori", "Quanto si deve ancora pagare ai fornitori."),
    "payables": ("Debiti", "L'insieme dei debiti commerciali a breve."),
    "other_payable": ("Altri debiti", "Debiti che non rientrano nelle categorie principali."),
    "payables_and_accrued_expenses": (
        "Debiti e ratei passivi",
        "Debiti piu' costi maturati e non ancora pagati."),
    "tradeand_other_payables_non_current": (
        "Debiti commerciali oltre l'anno",
        "Debiti verso fornitori con scadenza lunga."),
    "current_accrued_expenses": (
        "Ratei passivi correnti",
        "Costi maturati e non ancora pagati, entro l'anno."),
    "current_debt": (
        "Debito a breve",
        "La parte di debito finanziario da rimborsare entro un anno."),
    "long_term_debt": ("Debito a lungo", "Il debito finanziario oltre i dodici mesi."),
    "total_debt": ("Debito totale", "Tutto il debito finanziario, a breve e a lungo."),
    "net_debt": ("Debito netto", "Debito totale meno la cassa: quanto si deve DAVVERO."),
    "current_debt_and_capital_lease_obligation": (
        "Debito a breve e leasing",
        "Debito entro l'anno, compresi i canoni di leasing."),
    "long_term_debt_and_capital_lease_obligation": (
        "Debito a lungo e leasing",
        "Debito oltre l'anno, compresi i canoni di leasing."),
    "capital_lease_obligations": (
        "Obbligazioni per leasing",
        "Gli impegni per beni presi in locazione finanziaria."),
    "current_capital_lease_obligation": (
        "Leasing entro l'anno",
        "La quota di leasing da pagare nei dodici mesi."),
    "long_term_capital_lease_obligation": (
        "Leasing oltre l'anno",
        "La quota di leasing con scadenza lunga."),
    "other_current_borrowings": (
        "Altri debiti finanziari a breve",
        "Finanziamenti a breve che non rientrano altrove."),
    "current_deferred_liabilities": (
        "Passivita' differite correnti",
        "Obblighi il cui effetto cade entro l'anno."),
    "non_current_deferred_liabilities": (
        "Passivita' differite oltre l'anno",
        "Obblighi il cui effetto cade oltre i dodici mesi."),
    "current_deferred_revenue": (
        "Ricavi differiti correnti",
        "Soldi gia' incassati per servizi ancora da erogare, entro l'anno."),
    "non_current_deferred_revenue": (
        "Ricavi differiti oltre l'anno",
        "Incassi anticipati di competenza pluriennale."),
    "non_current_deferred_taxes_liabilities": (
        "Imposte differite",
        "Tasse di competenza gia' maturate ma non ancora pagate."),
    "current_provisions": (
        "Fondi rischi correnti",
        "Accantonamenti per oneri probabili entro l'anno."),
    "other_current_liabilities": (
        "Altre passivita' correnti",
        "Debiti a breve che non rientrano altrove."),
    "other_non_current_liabilities": (
        "Altre passivita' non correnti",
        "Debiti a lungo che non rientrano altrove."),
    "total_tax_payable": ("Debiti tributari", "Le imposte da versare."),
    "stockholders_equity": (
        "Patrimonio netto",
        "Quello che resta agli azionisti: attivo meno passivo."),
    "common_stock_equity": (
        "Patrimonio degli azionisti ordinari",
        "La parte di patrimonio che spetta alle azioni ordinarie."),
    "total_equity_gross_minority_interest": (
        "Patrimonio netto comprese le minoranze",
        "Il patrimonio totale, compresa la quota dei terzi."),
    "common_stock": (
        "Capitale sociale ordinario",
        "Il valore nominale delle azioni ordinarie emesse."),
    "preferred_stock": (
        "Azioni privilegiate",
        "Il capitale rappresentato da azioni con diritti particolari."),
    "capital_stock": ("Capitale sociale", "Il valore nominale complessivo delle azioni."),
    "additional_paid_in_capital": (
        "Sovrapprezzo azioni",
        "Quanto gli azionisti hanno pagato oltre il valore nominale."),
    "retained_earnings": ("Utili portati a nuovo", "Gli utili degli anni passati non distribuiti."),
    "other_equity_adjustments": (
        "Altre rettifiche di patrimonio",
        "Poste che modificano il patrimonio senza passare dall'utile."),
    "gains_losses_not_affecting_retained_earnings": (
        "Utili e perdite non a conto economico",
        "Variazioni di valore che non toccano l'utile dell'anno."),
    "share_issued": ("Azioni emesse", "Quante azioni sono state create."),
    "ordinary_shares_number": (
        "Azioni ordinarie in circolazione",
        "Quante azioni ordinarie ci sono davvero in giro."),
    "treasury_shares_number": (
        "Azioni proprie",
        "Le azioni che l'azienda ha ricomprato e tiene in cassa."),
    "invested_capital": (
        "Capitale investito",
        "Il capitale che finanzia l'attivita': patrimonio piu' debito."),
    "total_capitalization": ("Capitalizzazione totale", "Patrimonio netto piu' debito a lungo."),
    "working_capital": (
        "Capitale circolante",
        "Attivo corrente meno passivo corrente: la cassa immobilizzata nel giro d'affari."),
}

RENDICONTO = {
    "operating_cash_flow": (
        "Cassa dalla gestione operativa",
        "Quanto denaro ha prodotto il mestiere, davvero."),
    "cash_flow_from_continuing_operating_activities": (
        "Cassa operativa delle attivita' continuative",
        "La cassa operativa di cio' che l'azienda continuera' a fare."),
    "investing_cash_flow": (
        "Cassa dagli investimenti",
        "Denaro uscito per investire, o entrato vendendo."),
    "cash_flow_from_continuing_investing_activities": (
        "Cassa da investimenti continuativi",
        "Come sopra, per le sole attivita' che proseguono."),
    "financing_cash_flow": (
        "Cassa dai finanziamenti",
        "Denaro entrato o uscito per debito, dividendi e azioni."),
    "cash_flow_from_continuing_financing_activities": (
        "Cassa da finanziamenti continuativi",
        "Come sopra, per le sole attivita' che proseguono."),
    "free_cash_flow": (
        "Flusso di cassa libero",
        "La cassa operativa meno gli investimenti: quello che resta VERAMENTE disponibile."),
    "capital_expenditure": (
        "Investimenti in immobilizzazioni",
        "Quanto si spende per impianti, macchinari, immobili."),
    "purchase_of_ppe": (
        "Acquisto di immobilizzazioni",
        "Il denaro uscito per comprare beni strumentali."),
    "net_ppe_purchase_and_sale": (
        "Saldo acquisti e vendite di immobilizzazioni",
        "Compere meno cessioni di beni strumentali."),
    "depreciation_and_amortization": (
        "Ammortamenti",
        "La quota annua del costo dei beni durevoli. Non esce di cassa."),
    "depreciation_amortization_depletion": (
        "Ammortamenti e deplezione",
        "Ammortamenti piu' il consumo di risorse naturali."),
    "stock_based_compensation": (
        "Compensi in azioni",
        "Il costo delle azioni date ai dipendenti. Non esce di cassa, ma diluisce."),
    "change_in_working_capital": (
        "Variazione del circolante",
        "Quanta cassa e' entrata o rimasta bloccata nel giro d'affari."),
    "change_in_receivables": (
        "Variazione dei crediti",
        "Se i clienti pagano piu' tardi, la cassa peggiora."),
    "changes_in_account_receivables": (
        "Variazione dei crediti verso clienti",
        "Lo stesso, sui soli crediti commerciali."),
    "change_in_inventory": (
        "Variazione del magazzino",
        "Magazzino che cresce vuol dire cassa che si ferma."),
    "change_in_account_payable": (
        "Variazione dei debiti verso fornitori",
        "Pagare piu' tardi i fornitori migliora la cassa."),
    "change_in_payable": ("Variazione dei debiti", "Lo stesso, su tutti i debiti a breve."),
    "change_in_payables_and_accrued_expense": (
        "Variazione di debiti e ratei",
        "Debiti e costi maturati messi insieme."),
    "change_in_accrued_expense": (
        "Variazione dei ratei passivi",
        "Costi maturati e non ancora pagati."),
    "change_in_prepaid_assets": ("Variazione dei risconti attivi", "Costi pagati in anticipo."),
    "change_in_other_current_liabilities": (
        "Variazione delle altre passivita' correnti",
        "Il resto dei debiti a breve."),
    "deferred_income_tax": ("Imposte differite", "La parte di imposte che si pagera' piu' avanti."),
    "deferred_tax": (
        "Imposte differite (rendiconto)",
        "L'effetto delle imposte differite sulla cassa."),
    "income_tax_paid_supplemental_data": (
        "Imposte effettivamente pagate",
        "Le tasse uscite di cassa, che non coincidono con quelle di competenza."),
    "other_non_cash_items": ("Altre poste non monetarie", "Costi e ricavi che non muovono denaro."),
    "operating_gains_losses": (
        "Utili e perdite operativi",
        "Plusvalenze e minusvalenze legate alla gestione."),
    "gain_loss_on_investment_securities": (
        "Utili e perdite su titoli",
        "Quanto si e' guadagnato o perso sugli investimenti finanziari."),
    "gain_loss_on_sale_of_business": (
        "Utili e perdite da cessioni",
        "Il risultato della vendita di rami d'azienda."),
    "net_business_purchase_and_sale": (
        "Saldo acquisti e cessioni di aziende",
        "Quanto e' uscito per comprare aziende, meno quanto e' entrato vendendole."),
    "purchase_of_business": ("Acquisto di aziende", "Denaro uscito per acquisizioni."),
    "sale_of_business": ("Cessione di aziende", "Denaro entrato vendendo rami d'azienda."),
    "purchase_of_investment": (
        "Acquisto di investimenti",
        "Denaro impiegato in strumenti finanziari."),
    "sale_of_investment": (
        "Vendita di investimenti",
        "Denaro rientrato liquidando strumenti finanziari."),
    "net_investment_purchase_and_sale": (
        "Saldo acquisti e vendite di investimenti",
        "Compere meno vendite di strumenti finanziari."),
    "net_other_investing_changes": (
        "Altre variazioni di investimento",
        "Il resto dei movimenti di investimento."),
    "issuance_of_debt": ("Nuovo debito emesso", "Quanto si e' preso a prestito."),
    "long_term_debt_issuance": (
        "Emissione di debito a lungo",
        "Nuovi prestiti oltre i dodici mesi."),
    "repayment_of_debt": ("Rimborso di debito", "Quanto debito si e' restituito."),
    "long_term_debt_payments": (
        "Rimborsi di debito a lungo",
        "Quote di prestiti a lunga scadenza restituite."),
    "net_issuance_payments_of_debt": (
        "Saldo del debito",
        "Nuovo debito meno rimborsi: se e' positivo, ci si sta indebitando."),
    "net_long_term_debt_issuance": (
        "Saldo del debito a lungo",
        "Emissioni meno rimborsi sulle scadenze lunghe."),
    "repurchase_of_capital_stock": (
        "Riacquisto di azioni proprie",
        "Quanto si e' speso per ricomprare le proprie azioni."),
    "common_stock_payments": (
        "Pagamenti su azioni ordinarie",
        "Denaro uscito per riacquisti di azioni ordinarie."),
    "net_common_stock_issuance": (
        "Saldo delle azioni ordinarie",
        "Azioni emesse meno azioni riacquistate."),
    "proceeds_from_stock_option_exercised": (
        "Incassi da esercizio di opzioni",
        "Denaro entrato quando i dipendenti esercitano le opzioni."),
    "cash_dividends_paid": ("Dividendi pagati", "Quanto e' andato agli azionisti."),
    "common_stock_dividend_paid": (
        "Dividendi sulle azioni ordinarie",
        "La parte di dividendi destinata alle ordinarie."),
    "net_other_financing_charges": (
        "Altri oneri di finanziamento",
        "Il resto dei movimenti finanziari."),
    "net_income_from_continuing_operations": (
        "Utile delle attivita' continuative",
        "Il punto di partenza del rendiconto: l'utile da cui si risale alla cassa."),
    "beginning_cash_position": ("Cassa iniziale", "Quanto denaro c'era all'inizio del periodo."),
    "end_cash_position": ("Cassa finale", "Quanto denaro c'e' alla fine del periodo."),
    "changes_in_cash": ("Variazione di cassa", "Di quanto e' cambiato il denaro disponibile."),
}

VOCI = {**CONTO_ECONOMICO, **STATO_PATRIMONIALE, **RENDICONTO}


# Le voci che meritano piu' di una riga, e cosa aggiungere: come si legge il
# numero, la formula quando ce n'e' una, e la trappola quando ce n'e' una.
#
# **Non sono tutte, ed e' voluto.** Centottanta voci con un paragrafo ciascuna
# sarebbero centottanta paragrafi generici: chi legge non li leggerebbe, e
# scriverli avrebbe prodotto testo, non informazione. Qui ci sono quelle che
# qualcuno guarda davvero e su cui si sbaglia davvero — il resto tiene la sua
# riga, che per «Terreni e migliorie» e' esattamente quello che serve.
DETTAGLI = {
    "total_revenue": {
        "esteso": (
            "I ricavi sono il punto di partenza di tutto il conto economico, e "
            "l'unica voce che non si puo' migliorare con la contabilita': o il "
            "cliente ha pagato, o no. Quello che si puo' spostare e' QUANDO si "
            "contabilizzano — un contratto pluriennale riconosciuto tutto "
            "subito o spalmato negli anni da' due curve di crescita diverse "
            "sulla stessa realta'. Per questo i ricavi si guardano insieme ai "
            "ricavi differiti: se crescono i primi e crollano i secondi, "
            "l'azienda sta incassando il futuro."),
        "attenzione": (
            "La crescita dei ricavi da sola non dice niente sulla qualita': si "
            "compra crescita con acquisizioni, con sconti, o vendendo sotto "
            "costo. Va letta insieme al margine lordo."),
    },
    "gross_profit": {
        "esteso": (
            "Il margine lordo e' la prima cosa che dice se un'azienda ha "
            "potere: e' quanto resta dopo aver pagato cio' che serve a "
            "produrre, prima di ogni scelta discrezionale. Un margine lordo "
            "alto e stabile vuol dire che il cliente paga piu' del costo senza "
            "che l'azienda debba difendersi ogni trimestre; uno che scende di "
            "punto in punto e' quasi sempre la prima traccia di un vantaggio "
            "che si consuma — molto prima che si veda nell'utile."),
        "formula": "Margine lordo = ricavi - costo del venduto",
        "attenzione": (
            "Cosa finisce nel «costo del venduto» cambia da azienda ad "
            "azienda: chi ci mette dentro l'ammortamento degli impianti mostra "
            "un margine lordo piu' basso di chi lo mette fra le spese "
            "operative, a parita' di tutto il resto."),
    },
    "operating_income": {
        "esteso": (
            "Il reddito operativo e' il guadagno del MESTIERE: ricavi meno "
            "tutti i costi per farlo, e niente altro. Non contiene interessi, "
            "non contiene imposte, e soprattutto non contiene le poste che non "
            "c'entrano con l'attivita' — plusvalenze, proventi finanziari, "
            "cessioni. E' il numero da guardare per rispondere a «questa "
            "azienda, facendo quello che fa, guadagna?»."),
        "formula": "Reddito operativo = margine lordo - spese operative",
        "attenzione": (
            "Non e' l'EBIT, anche se spesso li si usa come sinonimi. L'EBIT "
            "comprende anche i proventi NON operativi: su NVDA, nel trimestre "
            "chiuso ad aprile 2026, l'EBIT sta 16,47 miliardi SOPRA il reddito "
            "operativo, e la differenza sono altri proventi. Chi guarda l'EBIT "
            "crede di guardare la redditivita' del mestiere; chi guarda il "
            "reddito operativo la guarda davvero."),
    },
    "ebit": {
        "esteso": (
            "L'EBIT — utile prima di interessi e imposte — serve a confrontare "
            "aziende con strutture finanziarie e fiscali diverse: togliendo "
            "interessi e tasse, resta quello che l'azienda produce a "
            "prescindere da come e' finanziata e da dove ha sede. E' il "
            "numeratore della copertura degli interessi, che dice quante volte "
            "il reddito copre il costo del debito."),
        "formula": "EBIT = utile ante imposte + oneri finanziari",
        "attenzione": (
            "Comprende i proventi non operativi, quindi puo' essere gonfiato "
            "da cose che non si ripeteranno: una plusvalenza da cessione entra "
            "nell'EBIT e non nel reddito operativo."),
    },
    "ebitda": {
        "esteso": (
            "L'EBITDA aggiunge all'EBIT gli ammortamenti, che sono costi che "
            "non escono di cassa: e' un'approssimazione di quanta cassa "
            "produce la gestione prima degli investimenti. Si usa moltissimo "
            "nei multipli e nel rapporto col debito perche' e' confrontabile "
            "fra aziende con parchi impianti di eta' diversa."),
        "formula": "EBITDA = EBIT + ammortamenti",
        "attenzione": (
            "Gli ammortamenti non escono di cassa OGGI, ma corrispondono a "
            "impianti che prima o poi vanno rifatti. Per un'azienda che "
            "investe molto, l'EBITDA e' sistematicamente piu' generoso della "
            "cassa che restera' davvero: il flusso di cassa libero lo dice, "
            "l'EBITDA no."),
    },
    "net_income": {
        "esteso": (
            "L'utile netto e' quello che resta dopo tutto: costi, interessi, "
            "imposte, poste straordinarie. E' il numero che finisce nell'EPS e "
            "nei multipli, e proprio per questo e' il piu' esposto a essere "
            "spostato — una svalutazione, una plusvalenza, un beneficio "
            "fiscale una tantum lo muovono senza che il mestiere sia cambiato."),
        "attenzione": (
            "Un utile netto che cresce mentre il flusso di cassa libero non "
            "cresce e' il segnale classico da guardare: la sezione «Dall'utile "
            "alla cassa» esiste per mostrare voce per voce dove i due si "
            "separano."),
    },
    "free_cash_flow": {
        "esteso": (
            "Il flusso di cassa libero e' la cassa che resta dopo aver pagato "
            "la gestione E gli investimenti necessari a tenerla in piedi: e' "
            "quello che l'azienda puo' davvero usare per ripagare debito, "
            "distribuire dividendi o ricomprare azioni. E' il numero su cui si "
            "costruisce il DCF, e la ragione per cui il prezzo equo dipende "
            "tanto dalle ipotesi: si proietta questo."),
        "formula": "Flusso di cassa libero = cassa dalla gestione - investimenti",
        "attenzione": (
            "Non distingue gli investimenti di MANTENIMENTO da quelli di "
            "CRESCITA: un'azienda che sta costruendo capacita' nuova mostra un "
            "flusso libero basso pur non avendo nessun problema. Guardare "
            "capex su ricavi, e la loro direzione, aiuta a separarli."),
    },
    "stockholders_equity": {
        "esteso": (
            "Il patrimonio netto e' cio' che resta agli azionisti se si "
            "vendesse tutto l'attivo e si pagassero tutti i debiti — a valori "
            "di bilancio, non di mercato. E' il denominatore del ROE e del "
            "rapporto debito/patrimonio, e cresce con gli utili non "
            "distribuiti e con gli aumenti di capitale, cala con perdite, "
            "dividendi e riacquisti di azioni."),
        "attenzione": (
            "Un patrimonio netto che cresce puo' far SCENDERE il rapporto "
            "debito/patrimonio anche mentre il debito aumenta. Su NVDA e' "
            "successo: da 0,088 a 0,063 in due trimestri, col debito salito da "
            "10,5 a 12,3 miliardi. Il rapporto da solo direbbe «si sta "
            "indebitando meno», ed e' falso."),
    },
    "total_debt": {
        "esteso": (
            "Il debito totale mette insieme quello a breve e quello a lungo, "
            "leasing finanziari compresi. Da solo dice poco: cento milioni di "
            "debito sono niente per chi ne guadagna cinquecento all'anno e "
            "sono una condanna per chi ne perde dieci. Si legge sempre in "
            "rapporto a qualcosa — al patrimonio, all'EBITDA, o alla cassa che "
            "l'azienda produce."),
        "attenzione": (
            "Non comprende gli impegni fuori bilancio: acquisti garantiti, "
            "obblighi di capacita', garanzie. Su alcune aziende quelli valgono "
            "piu' del debito iscritto — nel referto qualitativo di NVDA "
            "risultano 279 miliardi di impegni di fornitura."),
    },
    "net_debt": {
        "esteso": (
            "Il debito netto toglie dal debito la cassa e gli investimenti "
            "liquidi: e' quanto si dovrebbe davvero, potendo usare subito il "
            "denaro che si ha. Quando e' NEGATIVO l'azienda ha piu' cassa che "
            "debiti, ed e' una posizione di forza — puo' comprare, resistere a "
            "un ciclo cattivo, o restituire capitale senza chiedere niente a "
            "nessuno."),
        "formula": "Debito netto = debito totale - cassa e investimenti a breve",
    },
    "working_capital": {
        "esteso": (
            "Il capitale circolante e' la cassa immobilizzata nel giro "
            "d'affari: crediti verso clienti piu' magazzino, meno debiti verso "
            "fornitori. Se cresce piu' in fretta dei ricavi vuol dire che "
            "l'azienda sta finanziando i propri clienti o accumulando merce — "
            "in entrambi i casi la cassa peggiora mentre l'utile no. Un "
            "circolante NEGATIVO e' l'opposto, ed e' un vantaggio strutturale: "
            "vuol dire incassare prima di pagare, come fa chi vende in "
            "abbonamento."),
        "formula": "Capitale circolante = attivo corrente - passivo corrente",
    },
    "capital_expenditure": {
        "esteso": (
            "Gli investimenti in immobilizzazioni sono la cassa che esce per "
            "impianti, macchinari e immobili. Sono la voce che separa il "
            "flusso di cassa della gestione da quello libero, e la loro "
            "direzione racconta la fase in cui l'azienda si trova: capex in "
            "forte crescita e' un'azienda che sta costruendo, capex fermo su "
            "un'azienda matura e' manutenzione."),
        "attenzione": (
            "Nel rendiconto compaiono col segno negativo. Un capex «alto» non "
            "e' ne' buono ne' cattivo finche' non si sa se produrra' ricavi: "
            "il ritorno si vede anni dopo, nel ROIC."),
    },
    "stock_based_compensation": {
        "esteso": (
            "I compensi in azioni sono un costo vero — l'azienda paga i "
            "dipendenti con qualcosa che vale — ma non escono di cassa, quindi "
            "vengono aggiunti indietro nel rendiconto e gonfiano il flusso di "
            "cassa. Il conto lo pagano gli azionisti esistenti sotto forma di "
            "DILUIZIONE: piu' azioni in giro, stessa azienda."),
        "attenzione": (
            "Un'azienda che dichiara un flusso di cassa libero robusto e "
            "insieme riacquista azioni per neutralizzare la diluizione sta "
            "usando quella cassa per stare ferma. I due numeri vanno guardati "
            "insieme: compensi in azioni e riacquisti."),
    },
    "retained_earnings": {
        "esteso": (
            "Gli utili portati a nuovo sono la somma di tutti gli utili mai "
            "prodotti meno tutti i dividendi mai distribuiti: la memoria "
            "contabile di quanto l'azienda ha guadagnato e tenuto. Negativi "
            "vuol dire che nella sua storia ha perso piu' di quanto ha "
            "guadagnato — normale per un'azienda giovane, un fatto da spiegare "
            "per una matura."),
    },
    "deferred_income_tax": {
        "esteso": (
            "Le imposte differite nascono dalla differenza fra le regole "
            "contabili e quelle fiscali: un costo che il bilancio riconosce "
            "oggi e il fisco domani crea un'imposta che si paghera' piu' "
            "avanti. Nel rendiconto compaiono come rettifica perche' l'imposta "
            "di COMPETENZA e quella PAGATA non coincidono quasi mai."),
    },
    "current_deferred_revenue": {
        "esteso": (
            "I ricavi differiti sono soldi gia' incassati per servizi non "
            "ancora erogati: un debito, contabilmente, ma un debito che si "
            "paga lavorando invece che pagando. Per un'azienda in abbonamento "
            "sono il miglior indicatore anticipato che ci sia: crescono prima "
            "dei ricavi, perche' i ricavi di domani sono gia' incassati oggi."),
        "attenzione": (
            "Ricavi che crescono mentre i ricavi differiti calano vuol dire "
            "che l'azienda sta riconoscendo incassi vecchi senza farne di "
            "nuovi: e' il contrario di quello che sembra guardando la riga dei "
            "ricavi."),
    },
}


def dettaglio(nome: str) -> dict | None:
    """La spiegazione estesa di una voce, se ne ha una. `None` se non ce l'ha.

    Una voce senza dettaglio non e' un buco: ha la sua riga, e per «Terreni e
    migliorie» quella riga e' tutto quello che serve sapere.
    """
    return DETTAGLI.get(nome)


def etichetta(nome: str) -> str:
    """Il nome in italiano, o quello originale se il dizionario non lo conosce.

    Una voce sconosciuta non diventa un buco: torna col suo nome, con gli spazi
    al posto dei trattini bassi. E' esattamente cio' che si vedeva prima che
    questo dizionario esistesse.
    """
    voce = VOCI.get(nome)
    return voce[0] if voce else nome.replace("_", " ")


def etichette(nomi) -> dict[str, str]:
    """Le etichette di un insieme di voci, pronte da mandare al frontend."""
    return {nome: etichetta(nome) for nome in nomi}
