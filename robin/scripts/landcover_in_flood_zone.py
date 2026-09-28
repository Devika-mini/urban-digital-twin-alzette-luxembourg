from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import colormaps
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from src.aoi import load_aoi
from src.clip import dissolve_footprint, load_clipped
from src.config import REPO_ROOT, load_config
from src.landcover import load_legend

HQ100_PATH: Path = REPO_ROOT / "data/raw/Flood_hazard_HQ100/HWGK2021_HQ100/HWGK2021_HQ100.shp"
LANDCOVER_GDB_PATH: Path = REPO_ROOT / "data/raw/LandCover/LandCover_Luxembourg_2018_2021_2024.gdb"
CLIPPED_PATH: Path = REPO_ROOT / "data/processed/clipped.gpkg"

# Flip to True to force re-clipping even if the cached layers already match.
OVERWRITE: bool = False


def main() -> None:
    config: dict = load_config()
    aoi: gpd.GeoDataFrame = load_aoi()

    # Step 2: clip HQ100 and land cover to the AOI. load_clipped() caches each
    # result under out_layer in CLIPPED_PATH, and reuses it next run as long
    # as the source path/layer/CRS/AOI haven't changed (see src/clip.py).
    hq100: gpd.GeoDataFrame = load_clipped(
        HQ100_PATH, aoi, crs=config["crs"], out_path=CLIPPED_PATH, out_layer="hq100_clipped", overwrite=OVERWRITE
    )
    landcover_layer: str = f"LandCover_Luxembourg_status_{config['landcover_year']}"
    landcover: gpd.GeoDataFrame = load_clipped(
        LANDCOVER_GDB_PATH,
        aoi,
        layer=landcover_layer,
        crs=config["crs"],
        out_path=CLIPPED_PATH,
        out_layer="landcover",
        overwrite=OVERWRITE,
    )

    # Dissolving is cheap, so always redo it fresh rather than caching it too.
    hq100_footprint: gpd.GeoDataFrame = dissolve_footprint(hq100)
    hq100_footprint.to_file(CLIPPED_PATH, layer="hq100_footprint", driver="GPKG")

    # Sanity checks: flooded area must not exceed the AOI area.
    aoi_area: float = aoi.geometry.area.sum()
    flooded_area: float = hq100_footprint.geometry.area.sum()
    landcover_area: float = landcover.geometry.area.sum()

    print(f"AOI area:                {aoi_area:,.1f} m2")
    print(f"HQ100 rows before dissolve: {len(hq100)}")
    print(f"HQ100 flooded area (AOI): {flooded_area:,.1f} m2 ({100 * flooded_area / aoi_area:.1f}% of AOI)")
    print(f"Land cover rows (AOI):    {len(landcover)}")
    print(f"Land cover area (AOI):    {landcover_area:,.1f} m2 ({100 * landcover_area / aoi_area:.1f}% of AOI)")
    assert flooded_area <= aoi_area, "Flooded area exceeds AOI area - check clipping"
    print(f"Clipped layers up to date in {CLIPPED_PATH}")

    plot_clipped(aoi, hq100_footprint, landcover)


def plot_clipped(
    aoi: gpd.GeoDataFrame,
    hq100_footprint: gpd.GeoDataFrame,
    landcover: gpd.GeoDataFrame,
) -> None:
    # QC plot for Step 2: every land cover class present, plus the flood
    # extent on top, so the clip can be visually checked against Geoportail.
    # This is not yet the grouped Step 4 map - classes are shown as-is.
    legend: dict[int, str] = load_legend(LANDCOVER_GDB_PATH)
    labels: pd.Series = landcover["LC2024"].map(legend)

    categories: list[str] = sorted(labels.unique())
    palette: list[tuple] = colormaps["tab10"].colors
    color_map: dict[str, tuple] = {cat: palette[i % len(palette)] for i, cat in enumerate(categories)}
    colors: pd.Series = labels.map(color_map)

    fig, ax = plt.subplots(figsize=(6, 8))
    landcover.plot(ax=ax, color=colors, edgecolor="none")
    hq100_footprint.plot(ax=ax, facecolor="none", edgecolor="black", hatch="///", linewidth=1.2)
    aoi.boundary.plot(ax=ax, color="red", linewidth=1)

    legend_handles: list = [Patch(facecolor=color_map[cat], label=cat) for cat in categories]
    legend_handles.append(Line2D([0], [0], color="black", lw=1.5, label="HQ100 flood extent"))
    ax.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)

    ax.set_title("Land cover and HQ100 flood extent in AOI (Step 2, ungrouped classes)")
    ax.set_xlabel("Easting (m, EPSG:2169)")
    ax.set_ylabel("Northing (m, EPSG:2169)")
    ax.set_aspect("equal")

    fig_path: Path = REPO_ROOT / "results/figures/clip_sanity_check.png"
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    print(f"Saved clip sanity-check plot to {fig_path}")


if __name__ == "__main__":
    main()
