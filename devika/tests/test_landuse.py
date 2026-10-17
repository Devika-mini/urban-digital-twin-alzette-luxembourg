"""Synthetic fixtures only: no national datasets or EDDIE services required."""
import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, box, Point

from devika.src.landuse import PreparationError, make_subset, prepare_landuse, validate_polygons

FIELD = "LU1_level__3_name"
LAYER = "LandUse_status_2024"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_landuse.py"


@pytest.fixture
def source(tmp_path):
    # Store in Luxembourg's metric CRS, then select/export in geographic CRS.
    frame = gpd.GeoDataFrame(
        {FIELD: ["Residential", "Forêt", "Agriculture"], "source_id": [11, 22, 33],
         "detail": ["retained", "retained too", "outside"], "value": [1.5, 2.5, 3.5]},
        geometry=[box(6.12, 49.55, 6.13, 49.56), box(6.14, 49.55, 6.15, 49.56),
                  box(6.3, 49.7, 6.31, 49.71)], crs=4326,
    ).to_crs(2169)
    path = tmp_path / "landuse.gpkg"
    frame.to_file(path, layer=LAYER, engine="pyogrio")
    return path


def run(source, tmp_path, **kwargs):
    return prepare_landuse(source, tmp_path / "subset.geojson", bbox=[6.119, 49.549, 6.151, 49.561],
                           bbox_crs=4326, **kwargs)


def test_projected_source_attributes_coordinates_and_report(source, tmp_path):
    report = run(source, tmp_path)
    result = gpd.read_file(tmp_path / "subset.geojson")
    assert result.crs.to_epsg() == 4326
    assert result["source_id"].tolist() == [11, 22]
    assert result["detail"].tolist() == ["retained", "retained too"]
    assert result["value"].tolist() == [1.5, 2.5]
    assert result.total_bounds == pytest.approx([6.12, 49.55, 6.15, 49.56], abs=1e-6)
    assert report["category_counts"] == {"Forêt": 1, "Residential": 1}
    assert report["source_crs"] == "EPSG:2169"
    assert json.loads((tmp_path / "subset.report.json").read_text()) == report


def test_polygon_aoi_filters_bbox_candidates_without_clipping(source, tmp_path):
    # Triangle bbox includes both polygons, but triangle only intersects the first.
    aoi = gpd.GeoDataFrame(geometry=[Polygon([(6.119, 49.54), (6.151, 49.54), (6.119, 49.56)])], crs=4326)
    aoi_path = tmp_path / "aoi.geojson"
    aoi.to_file(aoi_path)
    report = prepare_landuse(source, tmp_path / "subset.geojson", aoi_path=aoi_path)
    result = gpd.read_file(tmp_path / "subset.geojson")
    assert report["feature_count"] == 1
    assert result["source_id"].tolist() == [11]
    assert result.total_bounds == pytest.approx([6.12, 49.55, 6.13, 49.56], abs=1e-6)


@pytest.mark.parametrize("kwargs, message", [
    ({}, "exactly one"),
    ({"bbox": [1, 2, 3, 4]}, "bbox_crs"),
    ({"bbox": [3, 2, 1, 4], "bbox_crs": 4326}, "xmin"),
    ({"bbox": [0, 0, float('inf'), 1], "bbox_crs": 4326}, "finite"),
    ({"bbox": [0, 0, 200, 1], "bbox_crs": 4326}, "bounds"),
    ({"bbox": [1, 2, 3, 4], "bbox_crs": 4326, "aoi_path": "aoi.geojson"}, "exactly one"),
])
def test_subset_validation(kwargs, message):
    with pytest.raises(PreparationError, match=message):
        make_subset(**kwargs)


@pytest.mark.parametrize("geometry", [None, Polygon(), Point(6.12, 49.55),
    Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])])
def test_bad_geometry_rejected(geometry):
    with pytest.raises(PreparationError, match="geometries"):
        validate_polygons(gpd.GeoDataFrame(geometry=[geometry], crs=4326), "fixture")


def test_missing_crs_rejected():
    with pytest.raises(PreparationError, match="CRS"):
        validate_polygons(gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)]), "fixture")


def test_no_overlap(source, tmp_path):
    with pytest.raises(PreparationError, match="no features"):
        prepare_landuse(source, tmp_path / "subset.geojson", bbox=[0, 0, 1, 1], bbox_crs=4326)
    assert not (tmp_path / "subset.geojson").exists()


def test_limit_is_failure_not_silent_truncation(source, tmp_path):
    with pytest.raises(PreparationError, match="candidate limit"):
        run(source, tmp_path, max_features=1)
    assert not (tmp_path / "subset.geojson").exists()


def test_missing_category_field(source, tmp_path):
    with pytest.raises(PreparationError, match="classification field"):
        run(source, tmp_path, category_field="wrong_field")


def test_existing_output_untouched(source, tmp_path):
    output = tmp_path / "subset.geojson"
    output.write_text("existing user file")
    with pytest.raises(PreparationError, match="already exists"):
        run(source, tmp_path)
    assert output.read_text() == "existing user file"


def test_null_categories_preserved_and_counted(source, tmp_path):
    frame = gpd.read_file(source)
    frame.loc[0, FIELD] = None
    other = tmp_path / "nulls.gpkg"
    frame.to_file(other, layer=LAYER)
    report = run(other, tmp_path)
    assert report["null_category_count"] == 1
    features = json.loads((tmp_path / "subset.geojson").read_text())["features"]
    assert features[0]["properties"][FIELD] is None


def test_invalid_source_geometry_does_not_export(tmp_path):
    source = tmp_path / "bad.gpkg"
    geometry = Polygon([(6.12, 49.55), (6.13, 49.56), (6.13, 49.55), (6.12, 49.56), (6.12, 49.55)])
    gpd.GeoDataFrame({FIELD: ["Residential"]}, geometry=[geometry], crs=4326).to_file(source, layer=LAYER)
    with pytest.raises(PreparationError, match="No repairs"):
        run(source, tmp_path)
    assert not (tmp_path / "subset.geojson").exists()


def test_cli_from_other_directory_with_yaml_overrides(source, tmp_path):
    config = tmp_path / "settings.yaml"
    config.write_text(f'''sources:
  landuse:
    path: {source}
subset:
  bbox: [6.119, 49.549, 6.151, 49.561]
  bbox_crs: EPSG:4326
output:
  directory: {tmp_path / 'export'}
''')
    process = subprocess.run([sys.executable, str(SCRIPT), "--config", str(config)],
                             cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["feature_count"] == 2
    assert (tmp_path / "export/alzette_landuse_2024.geojson").is_file()


def test_cli_missing_source_is_actionable(tmp_path):
    process = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 2
    assert "Supply --source" in process.stderr


def test_opt_in_repair_preserves_source_and_attributes(tmp_path):
    import hashlib
    source = tmp_path / "bowtie.gpkg"
    geometry = Polygon([(6.12, 49.55), (6.13, 49.56), (6.13, 49.55), (6.12, 49.56), (6.12, 49.55)])
    gpd.GeoDataFrame({FIELD: ["Residential"], "record_id": [42]}, geometry=[geometry], crs=4326).to_file(source, layer=LAYER)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    report = run(source, tmp_path, repair_invalid=True)
    result = gpd.read_file(tmp_path / "subset.geojson")
    assert result.geometry.is_valid.all()
    assert result.record_id.tolist() == [42]
    assert report["geometry_repairs"] == 1
    assert report["repair_records"][0]["source_fid"] == 1
    assert "Self-intersection" in report["repair_records"][0]["reason"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_repair_refuses_collapsed_components(tmp_path):
    source = tmp_path / "spike.gpkg"
    # A valid square plus an outward spike; make_valid returns polygon + line.
    geometry = Polygon([(6.12, 49.55), (6.13, 49.55), (6.14, 49.55),
                        (6.13, 49.55), (6.13, 49.56), (6.12, 49.56), (6.12, 49.55)])
    gpd.GeoDataFrame({FIELD: ["Residential"]}, geometry=[geometry], crs=4326).to_file(source, layer=LAYER)
    with pytest.raises(PreparationError, match="No components were discarded"):
        run(source, tmp_path, repair_invalid=True)
    assert not (tmp_path / "subset.geojson").exists()


def test_cli_repair_flag(tmp_path):
    source = tmp_path / "invalid.gpkg"
    geometry = Polygon([(6.12, 49.55), (6.13, 49.56), (6.13, 49.55), (6.12, 49.56), (6.12, 49.55)])
    gpd.GeoDataFrame({FIELD: ["Residential"]}, geometry=[geometry], crs=4326).to_file(source, layer=LAYER)
    process = subprocess.run([
        sys.executable, str(SCRIPT), "--source", str(source),
        "--output", str(tmp_path / "fixed.geojson"), "--bbox", "6.119", "49.549", "6.151", "49.561",
        "--bbox-crs", "EPSG:4326", "--repair-invalid",
    ], cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["geometry_repairs"] == 1
