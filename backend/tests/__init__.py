"""
Suite di tradash2.0.
# feat (Blocco 0, rivisto): questo file esiste per una ragione sola.

Rendendo `tests` un pacchetto, pytest importa `conftest` come `tests.conftest`
invece che come modulo di primo livello: cosi' `ReteVietata` sollevata dalla
fixture e' la STESSA classe che i test importano, e un `pytest.raises` la
riconosce.

Qui dentro non va nient'altro. Nel vecchio progetto questo file creava database
temporanei e impostava variabili d'ambiente all'import — lavoro nascosto in un
posto dove nessuno lo cerca.
"""
