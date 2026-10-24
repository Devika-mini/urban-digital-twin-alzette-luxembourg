"""Analyse a prepared regional land-use layer (already clipped to the agreed AOI)."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import os
import geopandas as gpd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from devika.src.ownership_analysis import estimate_ownership
from devika.src.landuse import validate_polygons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--landuse', required=True, help='Prepared AOI-clipped GeoJSON; not national data.')
    parser.add_argument('--ownership', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    paths = [ROOT / 'devika' / value for value in (args.landuse, args.ownership, args.output)]
    source, ownership, output = paths
    if output.exists():
        parser.error('Output exists; choose a new name.')
    land = gpd.read_file(source)
    grid = gpd.read_file(ownership)
    result = estimate_ownership(land, grid).to_crs(4326)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        temporary = Path(staging) / 'derived.geojson'
        temporary.write_text(result.to_json(drop_id=True, na='null', allow_nan=False))
        restored = gpd.read_file(temporary)
        validate_polygons(restored, 'Analysis export')
        if len(restored) != len(result) or restored.crs.to_epsg() != 4326:
            raise ValueError('Read-back count/CRS mismatch')
        os.link(temporary, output)
    print(json.dumps({'output': str(output), 'features': len(result),
        'interpretation': 'Area-weighted estimate from 2019 grid statistics; not parcel ownership.',
        'area_crs': 'EPSG:2169', 'missing_values': 'Excluded per field; see coverage_<field>.'}, indent=2))


if __name__ == '__main__':
    main()
