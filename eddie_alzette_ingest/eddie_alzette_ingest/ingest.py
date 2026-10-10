from datetime import datetime, timedelta, timezone

from sqlalchemy.engine import Connection

from eddie_alzette_ingest import db, wfs_point_timeseries


def _require_known_kind(fetch_cfg: dict) -> None:
    kind = fetch_cfg["kind"]
    if kind != wfs_point_timeseries.KIND:
        # Per the spec: don't build a framework for kinds that don't exist
        # yet. A future API type gets its own small fetcher, dispatched here.
        raise NotImplementedError(f"fetch.kind={kind!r} is not implemented yet; only {wfs_point_timeseries.KIND!r} is supported")


def _fetch_and_store_window(conn: Connection, fetch_cfg: dict, start: datetime, end: datetime) -> dict:
    geojson = wfs_point_timeseries.fetch_window(fetch_cfg, start, end)
    stations_df, observations_df = wfs_point_timeseries.parse_features(geojson, fetch_cfg)
    stations_upserted = db.upsert_stations(conn, stations_df, fetch_cfg["tables"]["stations"])
    observations_inserted = db.upsert_observations(
        conn, observations_df, fetch_cfg["tables"]["observations"], fetch_cfg["keep_raw_fields"], fetch_cfg["unique_key"]
    )
    print(
        f"[ingest] {start.isoformat()} to {end.isoformat()}: "
        f"{len(observations_df)} rows fetched, {observations_inserted} new, {stations_upserted} stations upserted"
    )
    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "rows_fetched": len(observations_df),
        "rows_inserted": observations_inserted,
        "stations_upserted": stations_upserted,
    }


def run_incremental(conn: Connection, source_cfg: dict, now: datetime | None = None) -> dict:
    fetch_cfg = source_cfg["fetch"]
    _require_known_kind(fetch_cfg)
    now = now or datetime.now(timezone.utc)

    db.ensure_tables(conn, fetch_cfg)
    last_stored = db.get_global_last_stored(conn, fetch_cfg["tables"]["observations"], fetch_cfg["time_field"])
    start, end = wfs_point_timeseries.compute_incremental_window(last_stored, fetch_cfg["overlap_hours"], now)

    return _fetch_and_store_window(conn, fetch_cfg, start, end)


def _expected_hourly_count(start: datetime, end: datetime) -> int:
    # Hourly timestamps strictly between start and end, matching the
    # source's own exclusive AFTER/BEFORE semantics.
    total_hours = int((end - start).total_seconds() // 3600)
    return max(total_hours - 1, 0)


def _gap_report(conn: Connection, fetch_cfg: dict, start: datetime, end: datetime) -> dict:
    expected_hours = _expected_hourly_count(start, end)
    name_to_id = db.get_station_ids_by_name(conn, fetch_cfg["tables"]["stations"])
    time_field = fetch_cfg["time_field"]

    report: dict[str, dict] = {}
    for station_name in fetch_cfg["stations"]:
        station_id = name_to_id.get(station_name)
        if station_id is None:
            # Not an error (e.g. Merl currently returns nothing from the source).
            report[station_name] = {"expected_hours": expected_hours, "actual_rows": 0, "gaps": "no data returned for this station"}
            continue

        raw_datetimes = db.get_observation_datetimes(conn, fetch_cfg["tables"]["observations"], station_id, time_field)
        parsed = {datetime.fromisoformat(v.replace("Z", "+00:00")) for v in raw_datetimes}
        in_window = {dt for dt in parsed if start < dt < end}
        expected_timestamps = {start + timedelta(hours=h) for h in range(1, expected_hours + 1)}
        missing = sorted(expected_timestamps - in_window)

        report[station_name] = {
            "expected_hours": expected_hours,
            "actual_rows": len(in_window),
            "gaps": [dt.isoformat() for dt in missing],
        }
    return report


def run_backfill(conn: Connection, source_cfg: dict, start: datetime, end: datetime) -> dict:
    fetch_cfg = source_cfg["fetch"]
    _require_known_kind(fetch_cfg)

    db.ensure_tables(conn, fetch_cfg)
    windows = [
        _fetch_and_store_window(conn, fetch_cfg, window_start, window_end)
        for window_start, window_end in wfs_point_timeseries.iter_backfill_windows(start, end, fetch_cfg["backfill_chunk_days"])
    ]
    return {"windows": windows, "gaps": _gap_report(conn, fetch_cfg, start, end)}


def dispatch(source_cfg: dict, conn: Connection, mode: str, **kwargs) -> dict:
    if mode == "incremental":
        return run_incremental(conn, source_cfg, now=kwargs.get("now"))
    if mode == "backfill":
        return run_backfill(conn, source_cfg, kwargs["start"], kwargs["end"])
    raise ValueError(f"mode={mode!r} is not supported; use 'incremental' or 'backfill'")
