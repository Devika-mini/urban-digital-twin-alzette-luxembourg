# eddie_alzette_ingest

An EDDIE plugin that ingests weather data sources described by one YAML file
per source in `data_sources/`. Only `fetch.kind: wfs_point_timeseries`
is implemented today (the ASTA hourly precipitation WFS,
`data_sources/asta_precipitation.yml`). A different API shape gets its
own small fetcher later, in this same package - not a bigger framework built
ahead of need.

## Layout

- `eddie_alzette_ingest/source_config.py`, `wfs_point_timeseries.py`, `db.py`, `ingest.py` -
  plain functions, no `eddie.*` import, runnable and testable without EDDIE or Docker.
- `eddie_alzette_ingest/tasks.py` - the only file that imports `eddie.*`;
  defines the Celery task `eddie_alzette_ingest.tasks.fetch_precipitation`.
- `eddie_alzette_ingest/blueprint.py` - an empty Flask blueprint. EDDIE's
  backend imports `<plugin>.blueprint` for every discovered `eddie_*` package
  on startup; without this file the backend container crashes.

## Running the tests (no EDDIE, no Docker, no network needed)

```bash
pip install -e eddie_alzette_ingest[dev]
pytest eddie_alzette_ingest/tests
```

A `@pytest.mark.integration` subset additionally needs a running PostGIS
(the `db_postgres_digital_twin` container) and is skipped by default.

## Running the fetch outside EDDIE (plain Python, for local testing)

```python
import sqlalchemy as sa
from eddie_alzette_ingest import ingest
from eddie_alzette_ingest.source_config import load_source_config

source_cfg = load_source_config("data_sources/asta_precipitation.yml")
engine = sa.create_engine("postgresql://postgres:<password>@localhost:5431/db")
with engine.connect() as conn:
    ingest.run_incremental(conn, source_cfg)
```

## Running as an EDDIE plugin

Needs the EDDIE stack running (`EDDIE/eddie_antarctica`) with this
package installed into the same Python environment as `eddie`/
`eddie_antartica` (pip-installed, discovered by `pkgutil.iter_modules()` -
see the EDDIE core's `discover_plugins`). It is not wired into the Docker
image build yet; see `results/first_injection_weather_data/eddie-findings.md`
for the current install-into-the-running-containers workaround used for testing.

Once installed, trigger manually (no scheduler exists in this stack yet -
"manually triggered task is enough" for now):

```bash
docker compose exec celery_worker bash -lc \
  "source /venv/bin/activate && celery -A src.eddie_antartica.tasks call \
   eddie_alzette_ingest.tasks.fetch_precipitation --kwargs '{\"mode\": \"incremental\"}'"
```

## What it stores

Two tables (names configurable per source file, see `fetch.tables`):
- `weather_stations` - one row per station, upserted (current-state dimension).
- `weather_observations` - one row per (station, timestamp, variable),
  inserted once and never overwritten (append-only fact log; a duplicate
  re-fetch, e.g. from the `overlap_hours` safety window, is a no-op). Raw
  fields (`fetch.keep_raw_fields`, e.g. `datetime`/`time`/`day`) are stored as
  the exact strings received - the source's time zone is unresolved (`datetime`
  says `Z`, `time` says `+01:00`), so nothing here "fixes" it.

Only `weather_stations` is published as a map layer; observations are for SQL
queries, not displayed as one map feature per observation.
