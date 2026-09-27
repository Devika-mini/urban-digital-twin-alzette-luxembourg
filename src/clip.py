from pathlib import Path

import geopandas as gpd
import pyogrio


def load_clipped(
    path: str | Path,
    aoi: gpd.GeoDataFrame,
    layer: str | None = None,
    crs: str = "EPSG:2169",
) -> gpd.GeoDataFrame:
    """Read a vector dataset, reproject/fix/clip it to the AOI.

    Uses the AOI's bbox as a pre-filter so large countrywide files (e.g. the
    land cover GDB) are not fully loaded into memory. Reusable across A1/A2/A3.
    """
    # Pre-filter by bounding box before doing anything else; this is what
    # keeps country-wide datasets like the land cover GDB fast to read.
    bbox: tuple[float, float, float, float] = tuple(aoi.total_bounds)
    gdf: gpd.GeoDataFrame = pyogrio.read_dataframe(path, layer=layer, bbox=bbox)

    if gdf.crs is None or gdf.crs.to_string() != crs:
        gdf = gdf.to_crs(crs)

    # Bbox pre-filtering only matches on feature envelopes: a single
    # countrywide row (like HQ100) still spans the whole country after this.
    # Clip to the AOI polygon *before* make_valid, so make_valid only has to
    # fix the small clipped-down geometry, not the full countrywide one.
    clipped: gpd.GeoDataFrame = gpd.clip(gdf, aoi).reset_index(drop=True)
    clipped = clipped.set_geometry(clipped.geometry.make_valid())   # GEO's repair algorithm

    return clipped


def dissolve_footprint(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Merge all rows of gdf into a single-row GeoDataFrame (one footprint polygon)."""
    footprint = gdf.geometry.union_all()
    return gpd.GeoDataFrame(geometry=[footprint], crs=gdf.crs)
