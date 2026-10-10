import os

import pytest
import sqlalchemy as sa

from eddie_alzette_ingest import db
from eddie_alzette_ingest.wfs_point_timeseries import parse_features

OBSERVATIONS_TABLE = "weather_observations_test"
STATIONS_TABLE = "weather_stations_test"


def test_upsert_observations_rerun_adds_zero_rows(sqlite_conn, wfs_sample, fetch_cfg):
    _, observations_df = parse_features(wfs_sample, fetch_cfg)
    keep_raw_fields, unique_key = fetch_cfg["keep_raw_fields"], fetch_cfg["unique_key"]
    db.ensure_observations_table(sqlite_conn, OBSERVATIONS_TABLE, keep_raw_fields, unique_key)

    first_run = db.upsert_observations(sqlite_conn, observations_df, OBSERVATIONS_TABLE, keep_raw_fields, unique_key)
    assert first_run == len(observations_df) == 9

    second_run = db.upsert_observations(sqlite_conn, observations_df, OBSERVATIONS_TABLE, keep_raw_fields, unique_key)
    assert second_run == 0


def test_upsert_observations_null_value_stored_as_sql_null(sqlite_conn, wfs_sample, fetch_cfg):
    _, observations_df = parse_features(wfs_sample, fetch_cfg)
    keep_raw_fields, unique_key = fetch_cfg["keep_raw_fields"], fetch_cfg["unique_key"]
    db.ensure_observations_table(sqlite_conn, OBSERVATIONS_TABLE, keep_raw_fields, unique_key)
    db.upsert_observations(sqlite_conn, observations_df, OBSERVATIONS_TABLE, keep_raw_fields, unique_key)

    table = sa.Table(OBSERVATIONS_TABLE, sa.MetaData(), autoload_with=sqlite_conn)
    row = sqlite_conn.execute(
        sa.select(table.c.value).where(table.c.datetime == "2026-10-02T04:00:00Z", table.c.station_id == "AGM_028")
    ).first()
    # Must be SQL NULL, not the literal float NaN and not 0.
    assert row[0] is None


@pytest.mark.integration
def test_upsert_stations_overwrites_on_conflict(wfs_sample, fetch_cfg):
    password = os.environ.get("TEST_POSTGRES_PASSWORD")
    if not password:
        pytest.skip("set TEST_POSTGRES_PASSWORD to run against the local db_postgres_digital_twin container")

    engine = sa.create_engine(f"postgresql://postgres:{password}@localhost:5431/db")
    stations_df, _ = parse_features(wfs_sample, fetch_cfg)

    with engine.connect() as conn:
        db.ensure_stations_table(conn, STATIONS_TABLE)
        first = db.upsert_stations(conn, stations_df, STATIONS_TABLE)
        assert first == len(stations_df)

        renamed = stations_df.copy()
        renamed.loc[renamed["station_id"] == "AGM_013", "station_name"] = "Roeser (renamed)"
        db.upsert_stations(conn, renamed, STATIONS_TABLE)

        table = sa.Table(STATIONS_TABLE, sa.MetaData(), autoload_with=conn)
        row = conn.execute(sa.select(table.c.station_name).where(table.c.station_id == "AGM_013")).first()
        assert row[0] == "Roeser (renamed)"

        conn.execute(sa.text(f"DROP TABLE {STATIONS_TABLE}"))
        conn.commit()
