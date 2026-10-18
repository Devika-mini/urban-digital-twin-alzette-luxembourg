import hashlib
import json

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union

from devika.src.landuse import PreparationError
from devika.src.national import prepare_national_landuse
from devika.src.ownership import prepare_ownership


def test_national_includes_distant_parts_and_preserves_source(tmp_path):
    source = tmp_path / 'source.gpkg'
    shapes = [MultiPolygon([box(6.12, 49.55, 6.13, 49.56), box(6.0, 50.0, 6.01, 50.01)]),
              MultiPolygon([box(6.4, 49.7, 6.41, 49.71)])]
    gpd.GeoDataFrame({'LU1_level__3_name': ['Residential ', 'Forest'], 'code': [111, 200]},
                     geometry=shapes, crs=4326).to_file(source, layer='LandUse_status_2024')
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / 'national'
    report = prepare_national_landuse(source, destination)
    assert report['status'] == 'validated'
    assert report['completed_source_features'] == report['source_feature_count'] == 2
    assert report['feature_count'] == 3
    outputs = [gpd.read_file(destination / item['path']) for item in report['files']]
    assert unary_union([g for frame in outputs for g in frame.geometry]).equals(unary_union(shapes))
    assert outputs[0]['LU1_level__3_name'].tolist() == ['Residential ', 'Residential ']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == checksum
    with pytest.raises(PreparationError, match='already exists'):
        prepare_national_landuse(source, destination)


def test_national_repair_and_failed_manifest(tmp_path):
    source = tmp_path / 'invalid.gpkg'
    gpd.GeoDataFrame({'LU1_level__3_name': ['Forest']},
        geometry=[Polygon([(6, 49), (6.1, 49.1), (6, 49.1), (6.1, 49), (6, 49)])],
        crs=4326).to_file(source, layer='LandUse_status_2024')
    with pytest.raises(PreparationError, match='No repairs enabled'):
        prepare_national_landuse(source, tmp_path / 'failed')
    assert json.loads((tmp_path / 'failed/manifest.json').read_text())['status'] == 'failed'
    result = prepare_national_landuse(source, tmp_path / 'fixed', repair_invalid=True)
    assert result['geometry_repairs'] == 1
    assert result['feature_count'] == 2
    with pytest.raises(PreparationError, match='limit'):
        prepare_national_landuse(source, tmp_path / 'limited', repair_invalid=True, max_output_mb=0.00001)
    assert json.loads((tmp_path / 'limited/manifest.json').read_text())['status'] == 'failed'


def test_full_ownership_retains_every_cell(tmp_path):
    source = tmp_path / 'ownership.geojson'
    frame = gpd.GeoDataFrame({'TOP_LEFT': ['a', 'b'], 'PUBLIC_PERCENT': [10, 40],
        'Commune_percent': [5, 20], 'Etat_percent': [5, 20], 'Autre_percent': [90, 60]},
        geometry=[box(60000, 60000, 61000, 61000), box(90000, 120000, 91000, 121000)], crs=2169)
    frame.to_crs(4326).to_file(source, driver='GeoJSON')
    report = prepare_ownership(source, tmp_path / 'all.geojson', all_features=True)
    assert report['feature_count'] == 2
    assert report['complete_cell_geometries_preserved']
    assert report['selection']['bbox'] is None
    assert report['cells_clipped'] == 0
    with pytest.raises(PreparationError, match='cannot be combined'):
        prepare_ownership(source, tmp_path / 'bad.geojson', all_features=True,
                          bbox=[6,49,7,50], bbox_crs=4326)
