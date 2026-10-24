"""Area-weighted grid context for polygons; not parcel ownership inference."""
import numpy as np
import pandas as pd
from shapely.ops import unary_union
from devika.src.landuse import PreparationError, validate_polygons


def estimate_ownership(landuse, ownership):
    """Return derived fields; never modify input frames. Areas use EPSG:2169.

    Null cell percentages are excluded only from that field's denominator;
    report its usable coverage separately. Do not sum overlapping categories.
    """
    validate_polygons(landuse, 'Land use')
    validate_polygons(ownership, 'Ownership')
    fields = [c for c in ownership.columns if 'percent' in c.lower()]
    if 'PUBLIC_PERCENT' not in fields:
        raise PreparationError('Missing PUBLIC_PERCENT')
    grid = ownership.to_crs(2169)
    polygons = landuse.to_crs(2169)
    numeric = {}
    for field in fields:
        original = grid[field]
        values = pd.to_numeric(original, errors='coerce')
        # Source audit explicitly permits a 0.01 percentage-point rounding excess.
        bad = original.notna() & (~np.isfinite(values) | ~values.between(0, 100.010001))
        if bad.any() or original.map(lambda v: isinstance(v, bool)).any():
            raise PreparationError(f'Invalid ownership percentages: {field}')
        numeric[field] = values
    records = []
    for polygon in polygons.geometry:
        indices = grid.sindex.query(polygon, predicate='intersects')
        overlaps = [(int(i), polygon.intersection(grid.geometry.iloc[i])) for i in indices]
        overlaps = [(i, geom) for i, geom in overlaps if geom.area > 0]
        areas = np.array([g.area for _, g in overlaps])
        covered = unary_union([g for _, g in overlaps]).area
        if areas.sum() - covered > max(1e-6, covered * 1e-9):
            raise PreparationError('Ownership cells overlap within a land-use polygon; refusing double counting.')
        row = {'polygon_area_m2': float(polygon.area), 'ownership_cell_count': len(overlaps),
               'ownership_coverage_pct': float(100 * covered / polygon.area)}
        for field in fields:
            values = np.array([numeric[field].iloc[i] for i, _ in overlaps], dtype=float)
            known = np.isfinite(values)
            denominator = areas[known].sum()
            row['estimated_' + field] = float(np.dot(areas[known], values[known]) / denominator) if denominator else None
            row['coverage_' + field] = float(100 * denominator / polygon.area)
        records.append(row)
    derived = pd.DataFrame(records)
    if set(derived.columns) & set(landuse.columns):
        raise PreparationError('Input already contains analysis fields; use original prepared land use.')
    result = landuse.copy().reset_index(drop=True)
    for field in derived:
        result[field] = derived[field].values
    result['landuse_label'] = result['LU1_level__3_name'].astype('string').str.strip()
    return result
