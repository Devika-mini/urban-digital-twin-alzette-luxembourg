import math

from eddie_alzette_ingest.wfs_point_timeseries import extract_station_id, parse_features


def test_extract_station_id():
    href = "http://catalog.inspire.geoportail.lu/geonetwork/dataset/00b35d13-.../AGM_013"
    assert extract_station_id(href) == "AGM_013"


def test_parse_features_stations(wfs_sample, fetch_cfg):
    stations_df, _ = parse_features(wfs_sample, fetch_cfg)
    # 9 features, 3 distinct stations - one row per station, not per observation.
    assert sorted(stations_df["station_id"]) == ["AGM_013", "AGM_019", "AGM_028"]
    assert set(stations_df["station_name"]) == {"Roeser", "Mamer", "Trintange"}
    assert stations_df.crs.to_string() == "EPSG:4326"


def test_parse_features_observations(wfs_sample, fetch_cfg):
    _, observations_df = parse_features(wfs_sample, fetch_cfg)
    assert len(observations_df) == 9
    assert set(observations_df["variable"]) == {"sum_nn050"}
    # raw fields stored exactly as received - not parsed/converted.
    for field in fetch_cfg["keep_raw_fields"]:
        assert field in observations_df.columns
    sample_row = observations_df.iloc[0]
    assert sample_row["datetime"] == "2026-10-02T03:00:00Z"
    assert sample_row["time"].endswith("+01:00")


def test_parse_features_empty_response_does_not_raise(fetch_cfg):
    # The source publishes roughly daily, not hourly - a short/recent window
    # can legitimately return zero features (observed live during
    # implementation); this must not crash.
    empty_geojson = {"type": "FeatureCollection", "features": []}
    stations_df, observations_df = parse_features(empty_geojson, fetch_cfg)
    assert len(stations_df) == 0
    assert len(observations_df) == 0


def test_null_value_stays_null_not_zero(wfs_sample, fetch_cfg):
    _, observations_df = parse_features(wfs_sample, fetch_cfg)
    trintange_rows = observations_df[observations_df["station_id"] == "AGM_028"]
    null_row = trintange_rows[trintange_rows["datetime"] == "2026-10-02T04:00:00Z"]
    assert len(null_row) == 1
    assert math.isnan(null_row.iloc[0]["value"])
    # The other two Trintange hours are real zero/near-zero measurements, not nulls.
    non_null = trintange_rows[trintange_rows["datetime"] != "2026-10-02T04:00:00Z"]
    assert non_null["value"].notna().all()
