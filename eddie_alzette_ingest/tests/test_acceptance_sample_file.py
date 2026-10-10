"""Pins the literal acceptance numbers from asta_precipitation.yml's
acceptance_check block against the only form this sample exists in:
Lagloire's pre-cleaned export (station_name/datetime/precip_mm), not the raw
WFS GetFeature shape the production parser (wfs_point_timeseries.py) expects.
A live WFS probe during planning confirmed the real shape has the raw fields
(name_descr, sum_nn050, featureofinterest_xlink_href, ...) this file lacks -
see test_wfs_point_timeseries_parse.py for the real-shape fixture instead.
"""
import geopandas as gpd
import pandas as pd


def test_acceptance_numbers_match_yml(legacy_sample_path):
    gdf = gpd.read_file(legacy_sample_path)

    assert len(gdf) == 167
    assert gdf["precip_mm"].isna().sum() == 1

    null_row = gdf[gdf["precip_mm"].isna()]
    # gpd.read_file parses "datetime" into a tz-aware Timestamp automatically.
    assert null_row.iloc[0]["datetime"] == pd.Timestamp("2026-09-29T09:00:00Z")

    assert round(gdf["precip_mm"].sum(), 2) == 7.11
