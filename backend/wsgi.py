"""
wsgi.py — il punto d'ingresso per il server di produzione.
# feat: la convenzione, perche' chi apre il repo lo cerchi dove se lo aspetta.

Tre righe che non fanno niente di nuovo: `gunicorn "app:create_app()"`
funzionava gia' identico. Esistono perche' `wsgi.py` e' il posto dove chiunque
conosca Flask va a guardare per primo — e perche' un punto d'ingresso dentro una
stringa nell'unit di systemd si trova solo se sai che e' li'.

    gunicorn --workers 1 --threads 8 wsgi:app

**Un worker solo**, sempre: `core/registry.py` tiene i lavori in memoria di
processo, e con piu' worker il pulsante Stop cadrebbe sul processo sbagliato.
Il perche' per esteso sta in `docs/DEPLOY.md`.
"""
from app import create_app

app = create_app()
