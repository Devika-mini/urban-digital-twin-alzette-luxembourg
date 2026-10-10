"""Unit-tests the backfill acceptance check ("row count per station equals
hours in window, or the gaps are listed") against a seeded in-memory DB - no
network, no live backfill. Validating this against the real rolling-year
service is a separate, manual step (see README.md).
"""
from datetime import datetime, timezone

import sqlalchemy as sa

from eddie_alzette_ingest.ingest import _expected_hourly_count, _gap_report


def test_expected_hourly_count_excludes_both_bounds():
    start = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 4, tzinfo=timezone.utc)
    # Strictly between 00:00 and 04:00: 01:00, 02:00, 03:00 -> 3 hours.
    assert _expected_hourly_count(start, end) == 3


def _seed_stand_in_stations_table(conn, rows: dict[str, str]) -> None:
    # A plain (non-geometry) stand-in: get_station_ids_by_name only reads
    # station_id/station_name, and geoalchemy2's Geometry DDL needs
    # spatialite, which plain SQLite doesn't have - see test_db_upsert.py.
    conn.execute(sa.text("CREATE TABLE weather_stations_gap_test (station_id TEXT PRIMARY KEY, station_name TEXT)"))
    for station_id, station_name in rows.items():
        conn.execute(
            sa.text("INSERT INTO weather_stations_gap_test VALUES (:id, :name)"),
            {"id": station_id, "name": station_name},
        )
    conn.commit()


def test_gap_report_lists_missing_hours_and_flags_empty_stations(sqlite_conn, fetch_cfg):
    fetch_cfg = {
        **fetch_cfg,
        "stations": ["Roeser", "Merl"],
        "tables": {"stations": "weather_stations_gap_test", "observations": "weather_observations_gap_test"},
    }
    _seed_stand_in_stations_table(sqlite_conn, {"AGM_013": "Roeser"})  # Merl: no row, as observed at the source

    from eddie_alzette_ingest import db

    db.ensure_observations_table(
        sqlite_conn, fetch_cfg["tables"]["observations"], fetch_cfg["keep_raw_fields"], fetch_cfg["unique_key"]
    )
    import pandas as pd

    start = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 4, tzinfo=timezone.utc)
    # Only the 02:00 hour present for Roeser - 01:00 and 03:00 are gaps.
    present = pd.DataFrame([{
        "station_id": "AGM_013", "variable": "sum_nn050", "value": 0.0,
        "datetime": "2026-01-01T02:00:00Z", "time": "03:00:00+01:00", "day": "2026-01-01", "gml_identifier": "x",
    }])
    db.upsert_observations(
        sqlite_conn, present, fetch_cfg["tables"]["observations"], fetch_cfg["keep_raw_fields"], fetch_cfg["unique_key"]
    )

    report = _gap_report(sqlite_conn, fetch_cfg, start, end)

    assert report["Roeser"]["expected_hours"] == 3
    assert report["Roeser"]["actual_rows"] == 1
    assert report["Roeser"]["gaps"] == ["2026-01-01T01:00:00+00:00", "2026-01-01T03:00:00+00:00"]

    assert report["Merl"] == {"expected_hours": 3, "actual_rows": 0, "gaps": "no data returned for this station"}
