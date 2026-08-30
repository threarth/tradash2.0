"""
app.py — server Flask di tradash2.0.
# feat (Blocco 0): avvio minimo, nessun lavoro che parte da solo.
# feat (Blocco 4): serve anche il build della SPA, cosi' il processo resta uno.

All'avvio si applica lo schema e basta. Nessun provider viene sondato,
nessun universo viene scaricato, nessun job parte: al primo avvio il log delle
chiamate resta vuoto finche' qualcuno non chiede qualcosa.
"""
import logging

from flask import Flask

import config
from api.calls import bp as calls_bp
from api.ops import bp as ops_bp
from api.universe import bp as universe_bp
from api.watchlist import bp as watchlist_bp
from api.web import bp as web_bp
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

    app.register_blueprint(ops_bp)
    app.register_blueprint(calls_bp)
    app.register_blueprint(universe_bp)
    app.register_blueprint(watchlist_bp)
    # Per ultimo: la sua rotta generica non deve precedere le API.
    app.register_blueprint(web_bp)

    return app


if __name__ == "__main__":
    create_app().run(port=config.DEV_SERVER_PORT, debug=True, use_reloader=False)
