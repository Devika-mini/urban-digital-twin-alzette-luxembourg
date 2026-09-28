from pathlib import Path
import json
import zipfile

import laspy
import numpy as np
import rasterio

from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt


# ============================================================
# SETTINGS
# ============================================================

MANIFEST_PATH = Path("../lidar_manifest.json")

DOWNLOAD_DIR = Path("../lidar_downloads")
EXTRACT_DIR = Path("../lidar_tiles")

OUTPUT_DIR = Path("terrain_outputs")
OUTPUT_DEM = OUTPUT_DIR / "luxembourg_dem.tif"
OUTPUT_WATER = OUTPUT_DIR / "luxembourg_water.tif"

RESOLUTION = 0.5
GROUND_CLASSES = [2, 9]
WATER_CLASS = 9


# ============================================================
# LOAD MANIFEST
# ============================================================

def load_manifest():

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST_PATH}"
        )

    with open(
        MANIFEST_PATH,
        "r",
        encoding="utf-8"
    ) as f:
        manifest = json.load(f)

    return manifest


# ============================================================
# GET REQUIRED TILE NAMES + .laz
# ============================================================

def get_required_tiles(manifest):

    required = set()

    for tile in manifest["tiles"]:
        required.add(tile["tile"] + ".laz")

    print(f"Required LAZ tiles: {len(required):,}")

    return required


# ============================================================
# EXTRACT REQUIRED LAZ FILES
# ============================================================

def extract_required_tiles(required):

    EXTRACT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    found = set()

    zip_files = list(
        DOWNLOAD_DIR.glob("*.zip")
    )

    print(
        f"Searching {len(zip_files):,} downloaded archives..."
    )

    for zip_path in zip_files:

        with zipfile.ZipFile(zip_path, "r") as archive:

            for member in archive.namelist():

                filename = Path(member).name

                if filename not in required:
                    continue

                output = EXTRACT_DIR / filename

                # Already extracted
                if output.exists():
                    found.add(filename)
                    continue

                print(f"Extracting {filename}")

                # Avoid extracting directory structure
                with archive.open(member) as source:
                    with open(output, "wb") as destination:
                        destination.write(source.read())

                found.add(filename)

    missing = required - found

    if missing:

        print("\nWARNING — missing tiles:")

        for tile in sorted(missing):
            print(f"  {tile}")

        raise RuntimeError(
            "Some required LAZ files could not be found."
        )

    print(
        f"\nAll {len(required):,} required tiles are available."
    )


# ============================================================
# CREATE EMPTY DEM
# ============================================================

def create_dem_array(manifest):

    bbox = manifest["requested_bbox"]

    xmin = bbox["xmin"]
    xmax = bbox["xmax"]
    ymin = bbox["ymin"]
    ymax = bbox["ymax"]

    width = int(
        np.ceil(
            (xmax - xmin) / RESOLUTION
        )
    )

    height = int(
        np.ceil(
            (ymax - ymin) / RESOLUTION
        )
    )

    print("\nDEM dimensions:")
    print(f"  Columns: {width:,}")
    print(f"  Rows:    {height:,}")
    print(f"  Cells:   {width * height:,}")

    dem = np.full(
        (height, width),
        -np.inf,
        dtype=np.float32
    )

    water_mask = np.zeros(
    (height, width),
    dtype=np.uint8
    )

    return dem, water_mask, xmin, xmax, ymin, ymax


# ============================================================
# ADD ONE LAZ TILE TO DEM
# ============================================================

def process_laz(
    laz_path,
    dem,
    water_mask,
    tile_bounds,
    xmin,
    xmax,
    ymin,
    ymax
):

    print(f"Processing {laz_path.name}")

    las = laspy.read(laz_path)

    # --------------------------------------------------------
    # Filter MNT classes
    # --------------------------------------------------------

    classification = np.asarray(
        las.classification
    )

    class_mask = np.isin(
        classification,
        GROUND_CLASSES
    )

    x = np.asarray(las.x)[class_mask]
    y = np.asarray(las.y)[class_mask]
    z = np.asarray(las.z)[class_mask]

    # --------------------------------------------------------
    # Crop to exact requested area
    # --------------------------------------------------------

    tile_xmin = tile_bounds["xmin"]
    tile_xmax = tile_bounds["xmax"]
    tile_ymin = tile_bounds["ymin"]
    tile_ymax = tile_bounds["ymax"]

    effective_xmin = max(xmin, tile_xmin)
    effective_xmax = min(xmax, tile_xmax)
    effective_ymin = max(ymin, tile_ymin)
    effective_ymax = min(ymax, tile_ymax)


    bbox_mask = (
        (x >= effective_xmin)
        & (x < effective_xmax)
        & (y >= effective_ymin)
        & (y < effective_ymax)
    )

    x = x[bbox_mask]
    y = y[bbox_mask]
    z = z[bbox_mask]

    if len(x) == 0:
        return

    # --------------------------------------------------------
    # Convert X/Y into raster row/column
    #
    # Raster rows start at NORTH/top.
    # --------------------------------------------------------

    cols = (
        (x - xmin) / RESOLUTION
    ).astype(np.int64)

    rows = (
        (ymax - y) / RESOLUTION
    ).astype(np.int64)

    # Numerical boundary protection
    valid = (
        (rows >= 0)
        & (rows < dem.shape[0])
        & (cols >= 0)
        & (cols < dem.shape[1])
    )

    rows = rows[valid]
    cols = cols[valid]
    z = z[valid]

    # --------------------------------------------------------
    # Highest Z value per 0.5 m cell
    # --------------------------------------------------------

    np.maximum.at(
        dem,
        (rows, cols),
        z.astype(np.float32)
    )

    # --------------------------------------------------------
    # Watermask making
    # --------------------------------------------------------
    water = classification == WATER_CLASS

    water_mask[
        rows[water],
        cols[water]
    ] = 1

# ============================================================
# FILL EMPTY CELLS
# ============================================================

def fill_empty_cells(dem):

    missing = np.isneginf(dem)

    number_missing = np.count_nonzero(
        missing
    )

    print(
        f"\nEmpty cells before interpolation: "
        f"{number_missing:,}"
    )

    if number_missing == 0:
        return dem

    if np.all(missing):
        raise RuntimeError(
            "DEM contains no valid elevation points."
        )

    # Find nearest valid raster cell for each missing cell
    indices = distance_transform_edt(
        missing,
        return_distances=False,
        return_indices=True
    )

    filled = dem.copy()

    filled[missing] = dem[
        tuple(
            index[missing]
            for index in indices
        )
    ]

    return filled


# ============================================================
# SAVE GEOTIFF
# ============================================================

def save_dem(
    dem,
    xmin,
    ymax
):

    transform = from_origin(
        xmin,
        ymax,
        RESOLUTION,
        RESOLUTION
    )

    print(f"\nSaving DEM: {OUTPUT_DEM}")

    with rasterio.open(
        OUTPUT_DEM,
        "w",

        driver="GTiff",

        height=dem.shape[0],
        width=dem.shape[1],

        count=1,

        dtype="float32",

        crs="EPSG:2169",

        transform=transform,

        compress="deflate",

        tiled=True,

        nodata=np.nan

    ) as dst:

        dst.write(
            dem,
            1
        )

    print("DEM saved successfully.")


# ============================================================
# SAVE WATERMASK
# ============================================================

def save_water_mask(water_mask, xmin, ymax):

    transform = from_origin(
        xmin,
        ymax,
        RESOLUTION,
        RESOLUTION
    )

    with rasterio.open(
        OUTPUT_WATER,
        "w",
        driver="GTiff",
        height=water_mask.shape[0],
        width=water_mask.shape[1],
        count=1,
        dtype="uint8",
        crs="EPSG:2169",
        transform=transform,
        compress="deflate",
        tiled=True,
        nodata=0
    ) as dst:

        dst.write(water_mask, 1)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("LUXEMBOURG LIDAR -> DEM")
    print("=" * 60)

    manifest = load_manifest()

    required = get_required_tiles(
        manifest
    )

    extract_required_tiles(
        required
    )

    (
        dem,
        water_mask,
        xmin,
        xmax,
        ymin,
        ymax
    ) = create_dem_array(
        manifest
    )

    for tile in manifest["tiles"]:

        filename = tile["tile"] + ".laz"
        laz_path = EXTRACT_DIR / filename

        process_laz(
            laz_path,
            dem,
            water_mask,
            tile["bounds"],
            xmin,
            xmax,
            ymin,
            ymax
        )

    dem = fill_empty_cells(
        dem
    )

    save_dem(
        dem,
        xmin,
        ymax
    )

    save_water_mask(
        water_mask,
        xmin,
        ymax
    )


if __name__ == "__main__":
    main()