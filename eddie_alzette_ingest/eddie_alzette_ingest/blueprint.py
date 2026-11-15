from datetime import datetime
from http.client import ACCEPTED, BAD_REQUEST

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue as ResponseValue

# EDDIE's app.py discovers every installed eddie_* package and does
# `importlib.import_module(f"{name}.blueprint")` then
# `app.register_blueprint(module.blueprint.blueprint)` - without this file
# (and this exact module-level name) the Flask backend crashes on startup.
# The ingest task stays manually triggered (scheduling is the handover's open
# design point); the route below is that manual trigger, used by the map.
blueprint = Blueprint("eddie_alzette_ingest", __name__)


@blueprint.route("/alzette-ingest/precipitation", methods=["POST"])
def fetch_precipitation_now() -> ResponseValue:
    """
    Start the ASTA precipitation ingest (tasks.fetch_precipitation) in the background.

    JSON: {"mode": "incremental"}, or
    {"mode": "backfill", "start": "2026-11-01T00:00:00Z", "end": "2026-11-03T23:00:00Z"}.
    Follow the returned task_id on GET /digital-twin-task-status/<task_id>.
    """
    # pylint: disable=import-outside-toplevel
    from eddie_alzette_ingest.tasks import fetch_precipitation

    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "incremental")
    if mode not in ("incremental", "backfill"):
        return jsonify({"status": "error", "message": "mode must be incremental or backfill."}), BAD_REQUEST
    start, end = payload.get("start"), payload.get("end")
    if mode == "backfill":
        try:
            first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
            if first.tzinfo is None or last.tzinfo is None or last < first:
                raise ValueError
        except (TypeError, ValueError):
            message = "A backfill needs ISO start and end with a time zone (e.g. Z), end after start."
            return jsonify({"status": "error", "message": message}), BAD_REQUEST
    task = fetch_precipitation.delay(mode, start, end)
    return jsonify({"status": "processing", "task_id": task.id, "mode": mode}), ACCEPTED
