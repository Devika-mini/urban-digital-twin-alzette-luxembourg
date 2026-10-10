from datetime import datetime, timedelta, timezone

from eddie_alzette_ingest.wfs_point_timeseries import (
    build_cql_filter,
    compute_incremental_window,
    iter_backfill_windows,
)


def test_build_cql_filter_both_bounds_exclusive():
    start = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 1, 23, tzinfo=timezone.utc)
    cql = build_cql_filter(["Roeser", "Mamer"], "name_descr", "datetime", start, end)
    assert cql == (
        "(name_descr='Roeser' OR name_descr='Mamer') AND "
        "datetime AFTER 2026-09-25T01:00:00Z AND datetime BEFORE 2026-10-01T23:00:00Z"
    )


def test_build_cql_filter_single_station():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    cql = build_cql_filter(["Roeser"], "name_descr", "datetime", start, end)
    assert cql.startswith("(name_descr='Roeser') AND")


def test_iter_backfill_windows_chunks_by_days():
    start = datetime(2025, 10, 9, tzinfo=timezone.utc)
    end = datetime(2026, 10, 9, tzinfo=timezone.utc)
    windows = list(iter_backfill_windows(start, end, chunk_days=31))
    assert windows[0] == (start, start + timedelta(days=31))
    assert windows[-1][1] == end
    # Every window end is the next window's start - no gaps, no overlap.
    for (_, this_end), (next_start, _) in zip(windows, windows[1:]):
        assert this_end == next_start


def test_iter_backfill_windows_single_short_window():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 5, tzinfo=timezone.utc)
    windows = list(iter_backfill_windows(start, end, chunk_days=31))
    assert windows == [(start, end)]


def test_compute_incremental_window_bootstrap_falls_back_to_horizon():
    now = datetime(2026, 10, 10, 8, 49, tzinfo=timezone.utc)
    start, end = compute_incremental_window(last_stored=None, overlap_hours=48, now=now, horizon_days=366)
    assert start == now - timedelta(days=366)
    assert end == now


def test_compute_incremental_window_subtracts_overlap():
    now = datetime(2026, 10, 10, 8, 49, tzinfo=timezone.utc)
    last_stored = datetime(2026, 10, 9, 23, tzinfo=timezone.utc)
    start, end = compute_incremental_window(last_stored=last_stored, overlap_hours=48, now=now)
    assert start == last_stored - timedelta(hours=48)
    assert end == now
