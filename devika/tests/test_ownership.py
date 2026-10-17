"""Whole-cell selection regression tests using small synthetic ownership grids."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, box

from devika.src.landuse import PreparationError
from devika.src.ownership import prepare_ownership

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_ownership.py"
BBOX = [78050, 70050, 78100, 70100]  # A tiny AOI within a complete 1 km² cell.


@pytest.fixture
def source(tmp_path):
    frame = gpd.GeoDataFrame({
        "TOP_LEFT": ["78000_71000", "79000_71000", "90000_91000"],
        "PUBLIC_PERCENT": [35.5, 60.0, 20.0], "Commune_percent": [20.0, 30.0, 10.0],
        "Etat_percent": [10.0, 20.0, 5.0], "Autre_percent": [5.5, 10.0, 5.0],
        "Domaine_public_percent": [1.0, None, 3.0], "Extra_PERCENT": [5.0, 6.0, 7.0],
        "notes": ["Keep attributes", "Second", "Outside"],
    }, geometry=[box(78000, 70000, 79000, 71000), box(79000, 70000, 80000, 71000),
                 box(90000, 90000, 91000, 91000)], crs=2169)
    path = tmp_path / "ownership.gpkg"
    frame.to_file(path)
    return path


def run(source, tmp_path, **kwargs):
    return prepare_ownership(source, tmp_path / "ownership.geojson", bbox=BBOX, bbox_crs=2169, **kwargs)


def test_whole_cell_preserved_not_clipped_and_all_fields_retained(source, tmp_path):
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    original = gpd.read_file(source).iloc[:1].to_crs(4326)
    report = run(source, tmp_path)
    result = gpd.read_file(tmp_path / "ownership.geojson")
    assert len(result) == 1
    assert result.crs.to_epsg() == 4326
    assert result.geometry[0].equals_exact(original.geometry.iloc[0], 1e-12)
    assert result.to_crs(2169).geometry.area.iloc[0] == pytest.approx(1_000_000, rel=1e-5)
    assert result.to_crs(2169).geometry.area.iloc[0] > box(*BBOX).area * 100
    assert result.drop(columns="geometry").to_dict("records") == original.drop(columns="geometry").to_dict("records")
    assert report["complete_cell_geometries_preserved"]
    assert report["all_attributes_preserved"]
    assert report["cells_clipped"] == 0
    assert "not exact parcel ownership" in report["interpretation"]
    assert "Domaine_public_percent" in report["percentage_validation"]
    assert "Extra_PERCENT" in report["percentage_validation"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == checksum
    assert json.loads((tmp_path / "ownership.report.json").read_text()) == report


def test_actual_geojson_source_and_geographic_aoi(source, tmp_path):
    geojson = tmp_path / "owner-type-grid.geojson"
    frame = gpd.read_file(source).to_crs(4326)
    geojson.write_text(frame.to_json(drop_id=True))
    aoi = gpd.GeoDataFrame(geometry=[box(*BBOX)], crs=2169).to_crs(4326)
    report = prepare_ownership(geojson, tmp_path / "ownership.geojson", bbox=list(aoi.total_bounds), bbox_crs=4326)
    assert report["feature_count"] == 1
    assert report["source_crs"] == "EPSG:4326"


def test_polygon_aoi_exact_selection_excludes_cells_in_holes(source, tmp_path):
    outer = box(77500, 69500, 80500, 71500)
    hole = box(78900, 69900, 80100, 71100)
    mask = Polygon(outer.exterior.coords, holes=[hole.exterior.coords])
    aoi_path = tmp_path / "aoi.gpkg"
    gpd.GeoDataFrame(geometry=[mask], crs=2169).to_file(aoi_path)
    report = prepare_ownership(source, tmp_path / "ownership.geojson", aoi_path=aoi_path)
    assert report["feature_count"] == 1
    assert gpd.read_file(tmp_path / "ownership.geojson").TOP_LEFT.tolist() == ["78000_71000"]


def test_boundary_touch_cells_are_selected_in_full(source, tmp_path):
    report = prepare_ownership(source, tmp_path / "ownership.geojson",
                               bbox=[78050, 70050, 79000, 70100], bbox_crs=2169)
    assert report["feature_count"] == 2
    assert report["cells_clipped"] == 0


@pytest.mark.parametrize("field,value", [("PUBLIC_PERCENT", 101), ("Commune_percent", -1),
    ("Extra_PERCENT", "bad"), ("PUBLIC_PERCENT", float("inf")), ("PUBLIC_PERCENT", True)])
def test_bad_percentages_fail(source, tmp_path, field, value):
    frame = gpd.read_file(source)
    frame[field] = frame[field].astype(object)
    frame.at[0, field] = value
    # Test attributes in memory to avoid driver coercion of bool/string fixtures.
    from devika.src.ownership import REQUIRED_FIELDS, validate_attributes
    with pytest.raises(PreparationError, match="percentages"):
        validate_attributes(frame, REQUIRED_FIELDS)


def test_missing_extra_null_and_numeric_string_values(source, tmp_path):
    frame = gpd.read_file(source)
    frame.loc[0, "Domaine_public_percent"] = None
    frame["PUBLIC_PERCENT"] = frame["PUBLIC_PERCENT"].astype(str)
    path = tmp_path / "nullable.gpkg"
    frame.to_file(path)
    report = run(path, tmp_path)
    result = gpd.read_file(tmp_path / "ownership.geojson")
    assert result.PUBLIC_PERCENT.iloc[0] == "35.5"
    assert result.Domaine_public_percent.isna().all()
    assert len(report["warnings"]) == 2


@pytest.mark.parametrize("problem", ["missing_field", "missing_id", "duplicate_id", "all_null_public"])
def test_invalid_schema_and_identifiers(source, tmp_path, problem):
    frame = gpd.read_file(source)
    if problem == "missing_field":
        frame = frame.drop(columns="Etat_percent")
    elif problem == "missing_id":
        frame.loc[0, "TOP_LEFT"] = None
    elif problem == "duplicate_id":
        frame.loc[1, "TOP_LEFT"] = frame.loc[0, "TOP_LEFT"]
    else:
        frame["PUBLIC_PERCENT"] = None
    path = tmp_path / "bad.gpkg"
    frame.to_file(path)
    with pytest.raises(PreparationError):
        prepare_ownership(path, tmp_path / "ownership.geojson", bbox=[78050, 70050, 79900, 70100], bbox_crs=2169)
    assert not (tmp_path / "ownership.geojson").exists()
    assert next(tmp_path.glob("*.failure-*.json")).is_file()


def test_invalid_geometry_is_not_repaired(source, tmp_path):
    frame = gpd.read_file(source)
    frame.loc[0, "geometry"] = Polygon([(78000, 70000), (79000, 71000), (79000, 70000), (78000, 71000), (78000, 70000)])
    path = tmp_path / "invalid.gpkg"
    frame.to_file(path)
    with pytest.raises(PreparationError, match="geometries"):
        run(path, tmp_path)


def test_no_overlap_and_existing_output(source, tmp_path):
    with pytest.raises(PreparationError, match="no features"):
        prepare_ownership(source, tmp_path / "ownership.geojson", bbox=[0, 0, 1, 1], bbox_crs=2169)
    output = tmp_path / "ownership.geojson"
    output.write_text("user data")
    with pytest.raises(PreparationError, match="already exists"):
        run(source, tmp_path)
    assert output.read_text() == "user data"


def test_cli_from_other_directory(source, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(f'''sources:
  ownership:
    path: {source}
subset:
  bbox: {BBOX}
  bbox_crs: EPSG:2169
output:
  directory: {tmp_path / 'exports'}
''')
    result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(config)],
                             cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["feature_count"] == 1


def test_source_required_in_cli(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 2
    assert "sources.ownership.path" in result.stderr


@pytest.mark.parametrize("limits", [{"max_output_mb": 0.00001}, {"max_feature_mb": 0.00001}])
def test_size_guard_prevents_publication(source, tmp_path, limits):
    with pytest.raises(PreparationError, match="limit"):
        run(source, tmp_path, **limits)
    assert not (tmp_path / "ownership.geojson").exists()
    assert not (tmp_path / "ownership.report.json").exists()


def test_candidate_cap_fails_without_truncation(source, tmp_path):
    with pytest.raises(PreparationError, match="candidate limit"):
        prepare_ownership(source, tmp_path / "ownership.geojson",
                          bbox=[78050, 70050, 79900, 70100], bbox_crs=2169, max_features=1)
    assert not (tmp_path / "ownership.geojson").exists()


def test_z_removal_preserves_complete_horizontal_footprint(source, tmp_path):
    import shapely
    frame = gpd.read_file(source)
    frame.geometry = frame.geometry.map(lambda geom: shapely.force_3d(geom, z=100))
    path = tmp_path / "with_z.gpkg"
    frame.to_file(path)
    report = run(path, tmp_path)
    result = gpd.read_file(tmp_path / "ownership.geojson")
    assert report["output_pieces_with_z_removed"] == 1
    assert result.crs.to_epsg() == 4326
    assert not result.geometry.has_z.any()
    assert result.geometry[0].equals_exact(shapely.force_2d(frame.to_crs(4326).geometry.iloc[0]), 1e-12)
