import os
from datetime import datetime
from pathlib import Path

import eddie.geoserver as gs
from eddie.digitaltwin import setup_environment
from eddie.tasks import app

from eddie_alzette_ingest import ingest
from eddie_alzette_ingest.source_config import load_source_config

# This is the only file in the package that imports eddie.* - everything else
# (source_config, wfs_point_timeseries, db, ingest) runs and is tested without
# EDDIE or Docker at all.

DATA_SOURCES_DIR = Path(os.environ.get("DATA_SOURCES_DIR", "/app/data_sources"))
SOURCE_FILE = DATA_SOURCES_DIR / "asta_precipitation.yml"


@app.task(name="eddie_alzette_ingest.tasks.fetch_precipitation")
def fetch_precipitation(mode: str = "incremental", start: str | None = None, end: str | None = None) -> dict:
    """Manually triggered task - precipitation has a fixed station list from
    the source yml, not an AOI, so this is not shaped as the usual
    main(selected_polygon_gdf, **kwargs) module contract. Scheduling (e.g. a
    daily celery beat) is an open design point, not decided here - this is
    deliberately just "a manually triggered task".
    """
    source_cfg = load_source_config(SOURCE_FILE)
    fetch_cfg = source_cfg["fetch"]
    engine = setup_environment.get_database()

    with engine.connect() as conn:
        kwargs = {}
        if mode == "backfill":
            kwargs = {"start": datetime.fromisoformat(start), "end": datetime.fromisoformat(end)}
        result = ingest.dispatch(source_cfg, conn, mode, **kwargs)

        # Only the stations table is published as a map layer; observations
        # is for SQL/time-series use, not a displayed feature layer (one
        # feature per station, not one per observation).
        workspace_name = gs.Workspaces.INPUT_LAYERS_WORKSPACE
        data_store = gs.create_main_db_store(workspace_name)
        gs.create_datastore_layer(conn, workspace_name, data_store, fetch_cfg["tables"]["stations"])

    return result
