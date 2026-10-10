import json
from pathlib import Path

import pytest
import sqlalchemy as sa

from eddie_alzette_ingest.source_config import DATA_SOURCES_DIR, load_source_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def source_cfg() -> dict:
    # The real, checked-in source file - tests run against the actual
    # contract, not a hand-rolled stand-in that could drift from it.
    return load_source_config(DATA_SOURCES_DIR / "asta_precipitation.yml")


@pytest.fixture
def fetch_cfg(source_cfg: dict) -> dict:
    return source_cfg["fetch"]


@pytest.fixture
def wfs_sample() -> dict:
    # Real response, fetched live from the ASTA WFS on 2026-10-10 for 3 of
    # the yml's stations over a short window that happens to include one
    # null value (Trintange, 2026-10-02T04:00:00Z) - not synthetic data.
    with open(FIXTURES_DIR / "wfs_getfeature_sample.json") as f:
        return json.load(f)


@pytest.fixture
def legacy_sample_path() -> Path:
    return FIXTURES_DIR / "precipitation_roeser_7days_eddie.geojson"


@pytest.fixture
def sqlite_conn():
    # Observations have no geometry column, so the append-only fact-log path
    # (upsert_observations, re-run-safety) is fully exercisable on SQLite.
    # The stations table (PostGIS Geometry) is not - see the integration
    # marker in test_db_upsert.py for that half.
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        yield conn
