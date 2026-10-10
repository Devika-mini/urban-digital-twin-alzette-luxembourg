from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

# The only fetch.kind implemented. A different API shape (e.g. a REST
# forecast) gets its own small fetcher later in this module, not a shared
# framework built ahead of need.
KIND: str = "wfs_point_timeseries"


def _iso_z(dt: datetime) -> str:
    # The service's AFTER/BEFORE filter wants e.g. "2026-10-09T00:00:00Z".
    # Naive datetimes are assumed UTC (callers are expected to pass UTC).
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_station_id(xlink_href: str) -> str:
    # featureofinterest_xlink_href ends in the station id, e.g.
    # ".../00b35d13-.../AGM_013" -> "AGM_013".
    return xlink_href.rstrip("/").rsplit("/", 1)[-1]


def build_cql_filter(stations: list[str], station_field: str, time_field: str, start: datetime, end: datetime) -> str:
    # Both AFTER/BEFORE bounds are exclusive at the source (observed by Robin,
    # recorded in the source yml) - this builder does not compensate for that.
    station_clause = " OR ".join(f"{station_field}='{s}'" for s in stations)
    return f"({station_clause}) AND {time_field} AFTER {_iso_z(start)} AND {time_field} BEFORE {_iso_z(end)}"


def build_request_params(fetch_cfg: dict, start: datetime, end: datetime) -> dict[str, str]:
    cql_filter = build_cql_filter(fetch_cfg["stations"], fetch_cfg["station_field"], fetch_cfg["time_field"], start, end)
    return {**fetch_cfg["params"], "CQL_FILTER": cql_filter}


def fetch_geojson(base_url: str, params: dict[str, str], timeout: float = 30.0) -> dict:
    # The only function in this module that touches the network - everything
    # else is a pure function, testable without mocking requests at all.
    response = requests.get(base_url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_window(fetch_cfg: dict, start: datetime, end: datetime, timeout: float = 30.0) -> dict:
    params = build_request_params(fetch_cfg, start, end)
    return fetch_geojson(fetch_cfg["base_url"], params, timeout=timeout)


def parse_features(geojson: dict, fetch_cfg: dict) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """One WFS GetFeature response -> (stations, observations).

    stations: one row per distinct station_id encountered (dedup by first
    occurrence), with the point geometry. observations: one row per feature,
    with keep_raw_fields stored exactly as received - the service's time zone
    conflict (datetime says Z, time says +01:00) is unresolved, so nothing
    here "fixes" it.
    """
    station_id_field = fetch_cfg["station_id_from"]
    station_name_field = fetch_cfg["station_field"]
    value_field = fetch_cfg["value_field"]
    variable = fetch_cfg["variable"]
    keep_raw_fields: list[str] = fetch_cfg["keep_raw_fields"]

    station_rows: dict[str, dict] = {}
    observation_rows: list[dict] = []

    for feature in geojson["features"]:
        props = feature["properties"]
        station_id = extract_station_id(props[station_id_field])

        if station_id not in station_rows:
            coords = feature["geometry"]["coordinates"]
            station_rows[station_id] = {
                "station_id": station_id,
                "station_name": props[station_name_field],
                "geometry": Point(coords[0], coords[1]),
            }

        observation_rows.append({
            "station_id": station_id,
            "variable": variable,
            # None stays None (-> NaN in the DataFrame): a missing station
            # value must never be substituted with 0.
            "value": props[value_field],
            **{field: props[field] for field in keep_raw_fields},
        })

    if station_rows:
        stations_df = gpd.GeoDataFrame(list(station_rows.values()), geometry="geometry", crs="EPSG:4326")
    else:
        # The source publishes roughly daily, not hourly (observed by
        # Robin) - a short/recent window legitimately returns zero
        # features; that is not an error.
        stations_df = gpd.GeoDataFrame(columns=["station_id", "station_name", "geometry"], geometry="geometry", crs="EPSG:4326")
    observations_df = pd.DataFrame(observation_rows, columns=["station_id", "variable", "value", *keep_raw_fields])
    return stations_df, observations_df


def iter_backfill_windows(start: datetime, end: datetime, chunk_days: int) -> Iterator[tuple[datetime, datetime]]:
    # Chunks [start, end) into chunk_days-sized windows. No cap was observed
    # at the source up to 43,920 rows in one request - chunking is precautionary.
    step = timedelta(days=chunk_days)
    window_start = start
    while window_start < end:
        window_end = min(window_start + step, end)
        yield window_start, window_end
        window_start = window_end


def compute_incremental_window(
    last_stored: datetime | None,
    overlap_hours: int,
    now: datetime,
    horizon_days: int = 366,
) -> tuple[datetime, datetime]:
    # last_stored is None when no station has any stored rows yet (first
    # run) - fall back to the full rolling-year horizon rather than fetching
    # nothing.
    if last_stored is None:
        start = now - timedelta(days=horizon_days)
    else:
        start = last_stored - timedelta(hours=overlap_hours)
    return start, now
