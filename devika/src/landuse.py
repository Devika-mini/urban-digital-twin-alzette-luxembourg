"""Prepare a bounded LIS-L subset without importing or modifying EDDIE."""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import geopandas as gpd
import pyogrio
import pandas as pd
from pyproj import CRS, Transformer
from shapely.geometry import box


class PreparationError(ValueError):
    """An input cannot safely be prepared for static ingestion."""


def validate_polygons(frame: gpd.GeoDataFrame, label: str) -> None:
    if frame.crs is None or frame.crs.to_epsg() is None:
        raise PreparationError(f"{label}: an explicit EPSG-resolvable CRS is required; do not guess it.")
    if frame.empty:
        raise PreparationError(f"{label}: no features found.")
    geometry = frame.geometry
    bad = geometry.isna() | geometry.is_empty | ~geometry.is_valid
    bad |= ~geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    if bad.any():
        raise PreparationError(
            f"{label}: {int(bad.sum())} missing, empty, invalid or non-polygon geometries. "
            "No repairs or drops were performed."
        )
    if not all(math.isfinite(float(v)) for v in frame.total_bounds):
        raise PreparationError(f"{label}: non-finite coordinates.")


def make_subset(*, bbox=None, bbox_crs=None, aoi_path=None) -> gpd.GeoDataFrame:
    if (bbox is None) == (aoi_path is None):
        raise PreparationError("Choose exactly one subset: bbox with CRS, or an AOI file.")
    if aoi_path is not None:
        subset = gpd.read_file(aoi_path, engine="pyogrio")
    else:
        if bbox_crs is None:
            raise PreparationError("bbox_crs is required; coordinates alone do not identify a CRS.")
        if len(bbox) != 4 or not all(math.isfinite(float(v)) for v in bbox):
            raise PreparationError("bbox must contain four finite values: xmin ymin xmax ymax.")
        xmin, ymin, xmax, ymax = map(float, bbox)
        if xmin >= xmax or ymin >= ymax:
            raise PreparationError("bbox must have xmin < xmax and ymin < ymax.")
        crs = CRS.from_user_input(bbox_crs)
        if crs.is_geographic and not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
            raise PreparationError("Geographic bbox is outside longitude/latitude bounds.")
        subset = gpd.GeoDataFrame(geometry=[box(xmin, ymin, xmax, ymax)], crs=crs)
    validate_polygons(subset, "Subset")
    return subset


def prepare_landuse(
    source: str | Path,
    output: str | Path,
    *,
    layer: str = "LandUse_status_2024",
    category_field: str = "LU1_level__3_name",
    bbox=None,
    bbox_crs=None,
    aoi_path=None,
    max_features: int = 50000,
) -> dict:
    """Export whole polygons intersecting an explicit subset, preserving attributes.

    Validation covers the spatially filtered candidates, not the national dataset.
    Invalid input is rejected rather than silently repaired. No clipping, area
    analysis, category remapping, ingestion or styling is performed.
    """
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise PreparationError(f"Source file does not exist: {source}")
    if output.suffix != ".geojson":
        raise PreparationError("Output must have the .geojson suffix for EDDIE ingestion.")
    report_path = output.with_suffix(".report.json")
    if output.exists() or report_path.exists():
        raise PreparationError("Output or report already exists; choose a new output filename.")
    if isinstance(max_features, bool) or not isinstance(max_features, int) or max_features < 1:
        raise PreparationError("max_features must be a positive integer.")
    subset = make_subset(bbox=bbox, bbox_crs=bbox_crs, aoi_path=aoi_path)
    info = pyogrio.read_info(source, layer=layer)
    if info["crs"] is None or CRS.from_user_input(info["crs"]).to_epsg() is None:
        raise PreparationError("Source layer requires an EPSG-resolvable CRS; none will be guessed.")
    if category_field not in info["fields"]:
        raise PreparationError(f"Missing classification field: {category_field}")
    source_crs = CRS.from_user_input(info["crs"])
    # Densify the bounding-box edges when transforming to avoid corner-only bounds.
    bounds = Transformer.from_crs(subset.crs, source_crs, always_xy=True).transform_bounds(
        *subset.total_bounds, densify_pts=21
    )
    if not all(math.isfinite(v) for v in bounds):
        raise PreparationError("Subset cannot be transformed to source CRS.")
    candidates = pyogrio.read_dataframe(source, layer=layer, bbox=bounds, max_features=max_features + 1)
    if len(candidates) > max_features:
        raise PreparationError(f"Subset exceeds the {max_features}-candidate limit; choose a smaller AOI.")
    validate_polygons(candidates, "Selected source candidates")
    selection_geometry = subset.to_crs(source_crs).geometry.union_all()
    selected = candidates.loc[candidates.intersects(selection_geometry)].copy()
    validate_polygons(selected, "Selected land use")
    result = selected.to_crs(4326)
    validate_polygons(result, "Reprojected land use")
    xmin, ymin, xmax, ymax = result.total_bounds
    if not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
        raise PreparationError("Output coordinates fall outside longitude/latitude bounds.")
    categories = result[category_field]
    if categories.notna().sum() == 0:
        raise PreparationError("All selected category values are missing.")
    nonnull = categories.dropna()
    if not nonnull.map(lambda value: isinstance(value, str)).all():
        raise PreparationError("Land-use category values must be strings or null.")
    counts = nonnull.value_counts().sort_index()
    report = {
        "source": str(source), "source_layer": layer, "source_crs": source_crs.to_string(),
        "output": str(output), "output_crs": "EPSG:4326", "category_field": category_field,
        "candidate_count": len(candidates), "feature_count": len(result),
        "category_counts": {str(k): int(v) for k, v in counts.items()},
        "null_category_count": int(categories.isna().sum()),
        "blank_category_count": int(nonnull.str.strip().eq("").sum()),
        "attributes": [column for column in result.columns if column != result.geometry.name],
        "output_bounds": [float(v) for v in result.total_bounds],
        "selection": {"method": "intersects; whole polygons retained, not clipped",
                      "bbox": list(bbox) if bbox is not None else None,
                      "bbox_crs": str(bbox_crs) if bbox_crs is not None else None,
                      "aoi_path": str(Path(aoi_path).resolve()) if aoi_path else None},
        "geometry_repairs": 0, "validation_scope": "spatial subset only",
        "versions": {"geopandas": gpd.__version__, "pyogrio": pyogrio.__version__},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Validate a temporary export before exposing it as the intended result.
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        temporary = Path(staging) / output.name
        result.to_file(temporary, driver="GeoJSON", engine="pyogrio", index=False, RFC7946="YES")
        restored = gpd.read_file(temporary, engine="pyogrio")
        validate_polygons(restored, "Export round trip")
        if restored.crs.to_epsg() != 4326 or len(restored) != len(result):
            raise PreparationError("Export round trip changed CRS or feature count.")
        features = json.loads(temporary.read_text())["features"]
        expected_categories = [None if value is None or pd.isna(value) else value for value in categories]
        if [feature["properties"].get(category_field) for feature in features] != expected_categories:
            raise PreparationError("Export round trip changed category values.")
        if any(set(feature["properties"]) != set(report["attributes"]) for feature in features):
            raise PreparationError("Export round trip changed attribute names.")
        temp_report = Path(staging) / report_path.name
        temp_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        temporary.rename(output)
        temp_report.rename(report_path)
    return report
