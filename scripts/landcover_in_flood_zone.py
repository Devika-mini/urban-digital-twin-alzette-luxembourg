from pathlib import Path

import geopandas as gpd

from src.aoi import load_aoi
from src.clip import dissolve_footprint, load_clipped
from src.config import REPO_ROOT, load_config

HQ100_PATH: Path = REPO_ROOT / "data/raw/Flood_hazard_HQ100/HWGK2021_HQ100/HWGK2021_HQ100.shp"
LANDCOVER_GDB_PATH: Path = REPO_ROOT / "data/raw/LandCover/LandCover_Luxembourg_2018_2021_2024.gdb"


def main() -> None:
    config: dict = load_config()
    aoi: gpd.GeoDataFrame = load_aoi()

    # Step 2: clip HQ100 and land cover to the AOI.
    hq100: gpd.GeoDataFrame = load_clipped(HQ100_PATH, aoi, crs=config["crs"])
    hq100_footprint: gpd.GeoDataFrame = dissolve_footprint(hq100)

    landcover_layer: str = f"LandCover_Luxembourg_status_{config['landcover_year']}"
    landcover: gpd.GeoDataFrame = load_clipped(
        LANDCOVER_GDB_PATH, aoi, layer=landcover_layer, crs=config["crs"]
    )

    # Sanity checks (§4/§5): flooded area must not exceed the AOI area.
    aoi_area: float = aoi.geometry.area.sum()
    flooded_area: float = hq100_footprint.geometry.area.sum()
    landcover_area: float = landcover.geometry.area.sum()

    print(f"AOI area:                {aoi_area:,.1f} m2")
    print(f"HQ100 rows before dissolve: {len(hq100)}")
    print(f"HQ100 flooded area (AOI): {flooded_area:,.1f} m2 ({100 * flooded_area / aoi_area:.1f}% of AOI)")
    print(f"Land cover rows (AOI):    {len(landcover)}")
    print(f"Land cover area (AOI):    {landcover_area:,.1f} m2 ({100 * landcover_area / aoi_area:.1f}% of AOI)")
    assert flooded_area <= aoi_area, "Flooded area exceeds AOI area - check clipping"

    # Save clipped layers so Step 3 (intersect) can read them back without redoing this.
    out_path: Path = REPO_ROOT / "data/processed/clipped.gpkg"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    hq100_footprint.to_file(out_path, layer="hq100_footprint", driver="GPKG")
    landcover.to_file(out_path, layer="landcover", driver="GPKG")
    print(f"Saved clipped layers to {out_path}")


if __name__ == "__main__":
    main()
