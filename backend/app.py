"""
app.py — server Flask di tradash2.0.
# feat (Blocco 0): avvio minimo, nessun lavoro che parte da solo.
# feat (Blocco 4): serve anche il build della SPA, cosi' il processo resta uno.

All'avvio si applica lo schema, si mette la porta e basta. Nessun provider
viene sondato, nessun universo viene scaricato, nessun job parte: al primo avvio
il log delle chiamate resta vuoto finche' qualcuno non chiede qualcosa.

**La porta e' `core/accesso.py`**, ed e' registrata qui invece che rotta per
rotta: e' l'unico modo perche' un endpoint scritto in futuro nasca chiuso.
"""
import logging
import os

from flask import Flask

import config
from api import installa_gestori
from api.analisi import bp as analisi_bp
from api.auth import bp as auth_bp
from api.calls import bp as calls_bp
from api.glossary import bp as glossary_bp
from api.impostazioni import bp as impostazioni_bp
from api.ops import bp as ops_bp
from api.salute import bp as salute_bp
from api.scanner import bp as scanner_bp
from api.spinoff import bp as spinoff_bp
from api.titolo import bp as titolo_bp
from api.universe import bp as universe_bp
from api.watchlist import bp as watchlist_bp
from api.web import bp as web_bp
from core import accesso
from core.schema import ensure_schema

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"


def _setup_logging() -> None:
    """Configura il log una volta sola, con lo stesso formato ovunque."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


def create_app() -> Flask:
    """Costruisce l'applicazione. Solo schema e blueprint, nessun lavoro."""
    _setup_logging()
    app = Flask(__name__)
    ensure_schema()

    # La porta si mette PRIMA delle rotte, e vale per tutte: chiude tutto cio'
    # che sta sotto `/api/` tranne l'elenco dichiarato in `core/accesso.py`.
    # Messa cosi', un endpoint aggiunto domani nasce protetto invece di nascere
    # aperto e aspettare che qualcuno se ne accorga.
    accesso.configura(app)
    # Il guasto della fonte diventa una risposta leggibile invece di un 500 con
    # stack trace. Sta qui, una volta, perche' il provider cade tutto insieme.
    installa_gestori(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(salute_bp)
    app.register_blueprint(ops_bp)
    app.register_blueprint(analisi_bp)
    app.register_blueprint(calls_bp)
    app.register_blueprint(glossary_bp)
    app.register_blueprint(impostazioni_bp)
    app.register_blueprint(scanner_bp)
    app.register_blueprint(spinoff_bp)
    app.register_blueprint(titolo_bp)
    app.register_blueprint(universe_bp)
    app.register_blueprint(watchlist_bp)
    # Per ultimo: la sua rotta generica non deve precedere le API.
    app.register_blueprint(web_bp)

    return app


if __name__ == "__main__":
    # `python app.py` e' il modo di lavorare in LOCALE, e solo quello: in uso
    # reale davanti c'e' gunicorn, che importa `create_app()` e non passa mai di
    # qui. Il debugger di Werkzeug esegue codice arbitrario da browser, quindi
    # si accende solo quando qualcuno lo chiede a voce alta.
    debug = os.environ.get("TRADASH2_DEBUG", "").strip() == "1"
    if debug:
        logging.getLogger(__name__).warning(
            "[APP] debugger acceso: esegue codice arbitrario da browser. "
            "Mai su una macchina raggiungibile da internet."
        )
    # L'indirizzo di ascolto e' configurabile ma resta `127.0.0.1` finche'
    # qualcuno non lo cambia a voce alta: aprire alla rete e' una decisione,
    # non un default.
    if config.DEV_SERVER_HOST != "127.0.0.1":
        logging.getLogger(__name__).warning(
            "[APP] in ascolto su %s: raggiungibile dalla rete. Il cookie di "
            "sessione e' Secure, quindi su http:// semplice l'accesso non "
            "regge senza TRADASH2_COOKIE_SICURO=0 — e li' la password viaggia "
            "in chiaro.", config.DEV_SERVER_HOST
        )
    create_app().run(host=config.DEV_SERVER_HOST, port=config.DEV_SERVER_PORT,
                     debug=debug, use_reloader=False)
