from flask import Blueprint

# EDDIE's app.py discovers every installed eddie_* package and does
# `importlib.import_module(f"{name}.blueprint")` then
# `app.register_blueprint(module.blueprint.blueprint)` - without this file
# (and this exact module-level name) the Flask backend crashes on startup.
# No routes are registered; the ingest task is triggered manually (see
# tasks.py), per the handover's open design point on scheduling.
blueprint = Blueprint("eddie_alzette_ingest", __name__)
