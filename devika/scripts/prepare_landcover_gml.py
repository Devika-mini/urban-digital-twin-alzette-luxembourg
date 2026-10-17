#!/usr/bin/env python3
"""Stream LIS-L 2024 INSPIRE land-cover GML(.gz) to clipped 2-D GeoJSON.

Dependencies: lxml, shapely>=2, pyproj, geopandas.
Example:
 python devika/scripts/prepare_landcover_gml.py \
    --source devika/data/raw/landcover/lc.lisl-landcover2024-luxembourg.gml.gz \
    --output devika/outputs/alzette_landcover_2024_clipped.geojson \
    --report devika/outputs/landcover_validation.json \
    --bbox 6.115 49.548 6.178 49.597
"""
import argparse
import gzip
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

import geopandas as gpd
from lxml import etree
from pyproj import Transformer
from shapely.geometry import Polygon, MultiPolygon, box, mapping
from shapely.ops import transform
from shapely.validation import make_valid, explain_validity

GML = 'http://www.opengis.net/gml/3.2'
LCV = 'http://inspire.ec.europa.eu/schemas/lcv/5.0'
XLINK = 'http://www.w3.org/1999/xlink'


def lname(el):
    return etree.QName(el).localname


def parse_ring(ring):
    """Read coordinate positions for a GML LinearRing or LineString."""
    poslist = ring.find(f'{{{GML}}}posList')
    if poslist is not None and poslist.text:
        dimension = int(poslist.get('srsDimension') or ring.get('srsDimension') or 2)
        if dimension < 2:
            raise ValueError('Invalid coordinate dimension')
        nums = [float(x) for x in poslist.text.split()]
        if len(nums) % dimension:
            raise ValueError('Invalid gml:posList coordinate count')
        return [(nums[i], nums[i + 1]) for i in range(0, len(nums), dimension)]
    positions = ring.findall(f'{{{GML}}}pos')
    if positions:
        return [tuple(float(v) for v in p.text.split()[:2]) for p in positions]
    raise ValueError('Missing gml:posList or gml:pos in ring/line')


def parse_boundary(boundary):
    """Handle a LinearRing or a Ring of connected LineString curveMembers."""
    linear = boundary.find(f'{{{GML}}}LinearRing')
    if linear is not None:
        return parse_ring(linear)
    ring = boundary.find(f'{{{GML}}}Ring')
    if ring is None:
        raise ValueError('Unsupported exterior/interior GML boundary')
    coords = []
    members = ring.findall(f'{{{GML}}}curveMember')
    if not members:
        raise ValueError('GML Ring contains no curveMember')
    for member in members:
        line = member.find(f'{{{GML}}}LineString')
        if line is None:
            raise ValueError('Unsupported GML Ring curveMember (not LineString)')
        segment = parse_ring(line)
        if len(segment) < 2:
            raise ValueError('GML LineString has fewer than two positions')
        if not coords:
            coords.extend(segment)
        else:
            if coords[-1] == segment[0]:
                coords.extend(segment[1:])
            elif coords[-1] == segment[-1]:
                coords.extend(reversed(segment[:-1]))
            else:
                raise ValueError('Disconnected curveMember LineStrings in GML Ring')
    if len(coords) < 4 or coords[0] != coords[-1]:
        raise ValueError('GML Ring is not closed or has insufficient positions')
    return coords


def parse_surface(unit):
    geom = unit.find(f'{{{LCV}}}geometry')
    if geom is None:
        raise ValueError('LandCoverUnit missing geometry')
    polygons = []
    for patch in geom.iter():
        if lname(patch) not in ('PolygonPatch', 'Polygon'):
            continue
        exterior = patch.find(f'{{{GML}}}exterior')
        if exterior is None:
            raise ValueError('Polygon patch missing exterior boundary')
        holes = [parse_boundary(i) for i in patch.findall(f'{{{GML}}}interior')]
        polygons.append(Polygon(parse_boundary(exterior), holes))
    if not polygons:
        raise ValueError('No supported polygon patches found in unit geometry')
    return MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]


def polygon_parts(geom):
    if geom is None or geom.is_empty:
        return
    if geom.geom_type == 'Polygon':
        yield geom
    elif geom.geom_type == 'MultiPolygon':
        yield from geom.geoms
    elif hasattr(geom, 'geoms'):
        for part in geom.geoms:
            yield from polygon_parts(part)


def get_class(unit):
    path = f'{{{LCV}}}landCoverObservation/{{{LCV}}}LandCoverObservation/{{{LCV}}}class'
    elem = unit.find(path)
    if elem is None:
        raise ValueError('LandCoverUnit missing land-cover class')
    href = elem.get(f'{{{XLINK}}}href')
    if not href:
        raise ValueError('LandCover class missing xlink:href')
    return href.rstrip('/').split('/')[-1], href


def write_feature(fout, poly, code, href, source_id, first):
    feature = {'type': 'Feature',
               'properties': {'class_code': code, 'class_href': href, 'source_id': source_id},
               'geometry': mapping(poly)}
    if not first:
        fout.write(',\n')
    fout.write(json.dumps(feature, separators=(',', ':')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--bbox', nargs=4, type=float, default=[6.115, 49.548, 6.178, 49.597],
                    metavar=('WEST', 'SOUTH', 'EAST', 'NORTH'))
    ap.add_argument('--axis-order', choices=['auto', 'en', 'ne'], default='auto')
    ap.add_argument('--max-features', type=int, default=250000)
    args = ap.parse_args()
    source, output, report_path = map(Path, (args.source, args.output, args.report))
    if not source.is_file():
        ap.error(f'Cannot find source: {source}')
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    west, south, east, north = args.bbox
    if not (west < east and south < north):
        ap.error('Invalid bbox ordering')
    geographic_bbox = box(west, south, east, north)
    to_ll = Transformer.from_crs('EPSG:3035', 'EPSG:4326', always_xy=True).transform
    from_ll = Transformer.from_crs('EPSG:4326', 'EPSG:3035', always_xy=True).transform
    clip = transform(from_ll, geographic_bbox)
    stats, codes = Counter(), Counter()
    detected_order = None if args.axis_order == 'auto' else args.axis_order
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=output.parent,
                                         prefix='.landcover-', suffix='.geojson', delete=False) as fout:
            tmp_path = Path(fout.name)
            fout.write('{"type":"FeatureCollection","features":[\n')
            first = True
            opener = gzip.open if source.name.lower().endswith('.gz') else open
            with opener(source, 'rb') as inp:
                context = etree.iterparse(inp, events=('end',), tag=f'{{{LCV}}}LandCoverUnit',
                                          huge_tree=True, resolve_entities=False, no_network=True)
                for _, unit in context:
                    stats['units_seen'] += 1
                    source_id = unit.get(f'{{{GML}}}id')
                    try:
                        raw = parse_surface(unit)
                        code, href = get_class(unit)
                        if detected_order is None:
                            first_polygon = next(polygon_parts(raw))
                            x0, y0 = first_polygon.exterior.coords[0]
                            candidates = {}
                            for order, coords in [('en', (x0, y0)), ('ne', (y0, x0))]:
                                candidates[order] = to_ll(*coords)
                            matching = [k for k, (lon, lat) in candidates.items()
                                        if 5.5 <= lon <= 6.7 and 49.2 <= lat <= 50.3]
                            if len(matching) != 1:
                                raise ValueError(f'Ambiguous GML EPSG:3035 axis order: {candidates}')
                            detected_order = matching[0]
                            print(f'Detected EPSG:3035 GML axis order: {detected_order}', flush=True)
                        if detected_order == 'ne':
                            raw = transform(lambda x, y, z=None: (y, x), raw)
                        # Repair only relevant geometries where possible.
                        if not raw.is_valid:
                            raw = make_valid(raw)
                            stats['repaired_units'] += 1
                        if not raw.intersects(clip):
                            stats['outside_aoi'] += 1
                            continue
                        inside = raw.intersection(clip)
                        for part in polygon_parts(inside):
                            if part.is_empty or part.area <= 0:
                                continue
                            if not part.is_valid:
                                stats['repaired_clipped_parts'] += 1
                                part = make_valid(part)
                            for clean_part in polygon_parts(part):
                                if clean_part.is_empty or clean_part.area <= 0:
                                    continue
                                # Second geographic clipping guards against reprojection rounding.
                                projected = transform(to_ll, clean_part)
                                clipped_ll = projected.intersection(geographic_bbox)
                                if not clipped_ll.is_valid:
                                    clipped_ll = make_valid(clipped_ll)
                                    stats['repaired_after_projection'] += 1
                                for final_poly in polygon_parts(clipped_ll):
                                    if final_poly.is_empty or final_poly.area <= 0:
                                        continue
                                    # GeoJSON rounding / tiny precision gaps can create invalid rings.
                                    if not final_poly.is_valid:
                                        final_poly = make_valid(final_poly)
                                        stats['repaired_before_write'] += 1
                                    for valid_poly in polygon_parts(final_poly):
                                        if valid_poly.is_empty or valid_poly.area <= 0:
                                            continue
                                        if not valid_poly.is_valid:
                                            raise ValueError('Unable to repair polygon before GeoJSON export: '
                                                             + explain_validity(valid_poly))
                                        write_feature(fout, valid_poly, code, href, source_id, first)
                                        first = False
                                        stats['exported_polygons'] += 1
                                        codes[code] += 1
                                        if stats['exported_polygons'] > args.max_features:
                                            raise ValueError('Exceeded --max-features; narrow AOI')
                    except (ValueError, etree.XMLSyntaxError) as exc:
                        raise ValueError(f'Unit #{stats["units_seen"]} ({source_id}): {exc}') from exc
                    finally:
                        parent = unit.getparent()
                        unit.clear()
                        if parent is not None:
                            while unit.getprevious() is not None:
                                del parent[0]
                    if stats['units_seen'] % 100000 == 0:
                        print(f'Scanned {stats["units_seen"]:,} units; exported {stats["exported_polygons"]:,}', flush=True)
            fout.write('\n]}\n')

        if stats['exported_polygons'] == 0:
            raise ValueError('No polygons exported: check extent, CRS and axis order')
        check = gpd.read_file(tmp_path)
        if check.crs is None or check.crs.to_epsg() != 4326:
            raise ValueError(f'Read-back CRS mismatch: observed={check.crs}, expected=EPSG:4326')
        if len(check) != stats['exported_polygons']:
            raise ValueError(f'Read-back count mismatch: observed={len(check)}, expected={stats["exported_polygons"]}')
        invalid_mask = check.geometry.isna() | check.geometry.is_empty | ~check.geometry.is_valid
        if invalid_mask.any():
            print(f'Found {int(invalid_mask.sum())} invalid/empty exported polygons:', flush=True)
            for idx, row in check.loc[invalid_mask].head(15).iterrows():
                geom = row.geometry
                print({'row': int(idx), 'source_id': row.get('source_id'),
                       'class_code': row.get('class_code'),
                       'geom_type': None if geom is None else geom.geom_type,
                       'reason': 'Missing geometry' if geom is None else explain_validity(geom)}, flush=True)
            raise ValueError('Read-back contains invalid or empty geometry; see printed IDs')
        if check['class_code'].isna().any():
            raise ValueError('Missing land-cover classification codes in read-back')
        if not check.geometry.within(geographic_bbox.buffer(1e-7)).all():
            raise ValueError('Read-back polygons extend beyond AOI bbox')
        os.replace(tmp_path, output)
        report = {'source': str(source), 'output': str(output),
                  'source_crs': 'EPSG:3035 (sampled)', 'output_crs': 'EPSG:4326',
                  'bbox_4326': args.bbox, 'axis_order': detected_order,
                  'counts': dict(stats), 'class_codes_exported': dict(sorted(codes.items())),
                  'file_bytes': output.stat().st_size, 'validated': True,
                  'note': 'Codes retained; names require verification against official legend.'}
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    except Exception:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise


if __name__ == '__main__':
    main()
