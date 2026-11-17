"""PostgisInputs selects what the file inputs select; the frozen functions read markers through it."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from flood_costs import depth_reconstruction as depth

# Only query I/O is stubbed: exercise the real adapter without importing EDDIE
# services or connecting to a database during test collection.
query = ModuleType("eddie_base_data.query")
def unexpected_query(*args, **kwargs):
    raise AssertionError("Synthetic test must replace query I/O")
query.read_all = query.read_in_aoi = query.read_table = unexpected_query
spec = importlib.util.spec_from_file_location("flood_costs.postgis_inputs",
    Path(depth.__file__).with_name("postgis_inputs.py"))
postgis_inputs = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"eddie_base_data.query": query}):
    spec.loader.exec_module(postgis_inputs)
PostgisInputs = postgis_inputs.PostgisInputs

LAYER = "Kilometrierung primäre Gewässer"


@pytest.fixture
def stored_markers(monkeypatch):
    table = gpd.GeoDataFrame(
        {"objectid": [1, 2, 3, 4], "toponyme": ["Alzette", "Alzette", "Alzette", "Sûre"], "kilo_km": [36.0, 35.0, 60.0, 35.0]},
        geometry=[Point(77000, 75000), Point(77100, 75000), Point(77200, 75000), Point(60000, 110000)], crs=2169)
    monkeypatch.setattr(postgis_inputs, "read_all", lambda conn, name, order_by: table)
    return table


def test_markers_are_the_alzette_range_in_km_order(stored_markers):
    assert PostgisInputs(None).markers(LAYER)["KILO_KM"].tolist() == [35.0, 36.0]


def test_frozen_functions_read_markers_through_their_namespace(stored_markers):
    namespace = {"gpd": gpd, "KILOMETRAGE_GPKG": None}
    PostgisInputs(None).bind(namespace)
    assert namespace["KILOMETRAGE_GPKG"].is_file()
    assert sorted(namespace["gpd"].read_file(namespace["KILOMETRAGE_GPKG"], layer=LAYER)["TOPONYME"].unique()) == ["Alzette", "Sûre"]
    assert namespace["gpd"].GeoDataFrame is gpd.GeoDataFrame


@pytest.mark.parametrize("scenario", ["hq10", "hq100", "hqextreme"])
def test_extent_is_clipped_to_the_marker_crop(stored_markers, monkeypatch, scenario):
    markers = PostgisInputs(None).markers(LAYER)
    crop = depth.crop_around_markers(markers)
    inside, straddling = box(77000, 75000, 77010, 75010), box(crop.bounds[2] - 5, 75000, crop.bounds[2] + 5, 75010)
    parts = gpd.GeoDataFrame({"part_id": [1, 0]}, geometry=[straddling, inside], crs=2169)
    tables = []
    def read_parts(conn, table, aoi):
        tables.append(table)
        return parts
    monkeypatch.setattr(postgis_inputs, "read_in_aoi", read_parts)
    assert PostgisInputs(None).extent(scenario, markers).area == pytest.approx(100 + 50)
    assert tables == ["base_flood_extent_" + scenario]


def test_empty_extent_is_refused(stored_markers, monkeypatch):
    markers = PostgisInputs(None).markers(LAYER)
    empty = gpd.GeoDataFrame({"part_id": []}, geometry=[], crs=2169)
    monkeypatch.setattr(postgis_inputs, "read_in_aoi", lambda conn, table, aoi: empty)
    with pytest.raises(RuntimeError, match="hq10"):
        PostgisInputs(None).extent("hq10", markers)
