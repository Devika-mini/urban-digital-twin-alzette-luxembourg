import geopandas as gpd
import pytest
from shapely.geometry import box
from devika.src.ownership_analysis import estimate_ownership
from devika.src.landuse import PreparationError


def frames():
    land = gpd.GeoDataFrame({'LU1_level__3_name': [' Residential ']}, geometry=[box(0,0,10,10)], crs=2169)
    grid = gpd.GeoDataFrame({'PUBLIC_PERCENT':[20.,70.], 'Commune_percent':[None,30.]},
        geometry=[box(0,0,6,10),box(6,0,10,10)], crs=2169)
    return land, grid


def test_weighted_and_missing_coverage():
    land, grid = frames()
    row = estimate_ownership(land,grid).iloc[0]
    assert row.estimated_PUBLIC_PERCENT == pytest.approx(40)
    assert row.estimated_Commune_percent == 30
    assert row.coverage_Commune_percent == 40
    assert row.ownership_coverage_pct == 100
    assert row.landuse_label == 'Residential'
    assert land.iloc[0].LU1_level__3_name == ' Residential '


def test_partial_and_absent():
    land,grid=frames()
    row=estimate_ownership(land,grid.iloc[:1]).iloc[0]
    assert row.estimated_PUBLIC_PERCENT == 20
    assert row.ownership_coverage_pct == 60
    land.geometry=[box(20,20,30,30)]
    row=estimate_ownership(land,grid).iloc[0]
    assert row.estimated_PUBLIC_PERCENT is None
    assert row.ownership_coverage_pct == 0


def test_overlapping_cells_rejected():
    land,grid=frames()
    grid.geometry=[box(0,0,7,10),box(6,0,10,10)]
    with pytest.raises(PreparationError,match='overlap'):
        estimate_ownership(land,grid)
