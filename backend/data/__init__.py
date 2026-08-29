"""
Accesso ai dati. Qui dentro sta l'UNICO punto che parla con Defeatbeta.
# feat (Blocco 1): fonte unica, e una sola porta per attraversarla.

Nessun altro modulo del progetto puo' interrogare i parquet: chi vuole un dato
di mercato passa da `data/defeatbeta.py`, che e' anche l'unico posto in cui la
provenienza (rete o cache) viene misurata e scritta nel registro.
"""
