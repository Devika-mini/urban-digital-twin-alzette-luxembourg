from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
from whitebox import WhiteboxTools


# ============================================================
# SETTINGS
# ============================================================

OUTPUT_DIR = Path("../terrain_outputs")

DEM_PATH = OUTPUT_DIR / "luxembourg_dem.tif"
WATER_PATH = OUTPUT_DIR / "luxembourg_water.tif"


SLOPE_PATH = OUTPUT_DIR / "slope.tif"
ASPECT_PATH = OUTPUT_DIR / "aspect.tif"
FILLED_DEM_PATH = OUTPUT_DIR / "filled_dem.tif"
FLOW_DIRECTION_PATH = OUTPUT_DIR / "flow_direction.tif"
FLOW_ACCUMULATION_PATH = OUTPUT_DIR / "flow_accumulation.tif"
WATERSHEDS_PATH = OUTPUT_DIR / "watersheds.tif"
DRAINAGE_WATER_PATH = OUTPUT_DIR / "drainage_water.tif"


# ============================================================
# VALIDATION OF INPUT RASTERS
# ============================================================

def validate_rasters():
        
    if not DEM_PATH.exists():
        raise FileNotFoundError(
            f"DEM not found: {DEM_PATH}"
        )

    if not WATER_PATH.exists():
        raise FileNotFoundError(
            f"Water mask not found: {WATER_PATH}"
        )

    with rasterio.open(DEM_PATH) as dem:
        with rasterio.open(WATER_PATH) as water:

            if dem.shape != water.shape:
                raise ValueError(
                    "DEM and water mask have different dimensions."
                )

            if dem.transform != water.transform:
                raise ValueError(
                    "DEM and water mask are not aligned."
                )

            if dem.crs != water.crs:
                raise ValueError(
                    "DEM and water mask have different CRS."
                )

    print("DEM and water mask are aligned.")


# ============================================================
# SLOPE + ASPECT
# ============================================================

def create_slope_aspect():

    print("Creating slope and aspect maps...")

    with rasterio.open(DEM_PATH) as src:

        dem = src.read(1).astype(np.float32)
        profile = src.profile.copy()

        # Pixel dimensions
        dx = src.res[0]
        dy = src.res[1]

        # Elevation gradients
        dz_dy, dz_dx = np.gradient(dem, dy, dx)

        # ----------------------------------------------------
        # Slope
        # ----------------------------------------------------

        slope = np.degrees(
            np.arctan(
                np.sqrt(dz_dx**2 + dz_dy**2)
            )
        )

        # ----------------------------------------------------
        # Aspect
        # ----------------------------------------------------

        aspect = np.degrees(
            np.arctan2(-dz_dx, dz_dy)
        )

        # Convert to compass direction:
        # 0 = North
        # 90 = East
        # 180 = South
        # 270 = West

        aspect = (aspect + 360) % 360

        profile.update(
            dtype="float32",
            count=1,
            compress="deflate",
            nodata=np.nan
        )

        with rasterio.open(SLOPE_PATH, "w", **profile) as dst:
            dst.write(slope.astype(np.float32), 1)

        with rasterio.open(ASPECT_PATH, "w", **profile) as dst:
            dst.write(aspect.astype(np.float32), 1)

    print(f"  Created: {SLOPE_PATH}")
    print(f"  Created: {ASPECT_PATH}")


# ============================================================
# HYDROLOGY
# ============================================================

def create_hydrology():

    print("\nCreating hydrological maps...")

    wbt = WhiteboxTools()

    # Don't print every internal Whitebox message
    wbt.set_verbose_mode(False)

    dem = str(DEM_PATH.resolve())
    filled = str(FILLED_DEM_PATH.resolve())
    pointer = str(FLOW_DIRECTION_PATH.resolve())
    accumulation = str(FLOW_ACCUMULATION_PATH.resolve())
    watersheds = str(WATERSHEDS_PATH.resolve())

    # --------------------------------------------------------
    # 1. Fill depressions
    # --------------------------------------------------------

    print("Filling depressions...")

    wbt.fill_depressions(
        dem,
        filled
    )

    # --------------------------------------------------------
    # 2. D8 flow direction (NO SPLITTING)
    # --------------------------------------------------------

    print("Calculating flow direction...")

    wbt.d8_pointer(
        filled,
        pointer
    )

    # --------------------------------------------------------
    # 3. Flow accumulation
    # --------------------------------------------------------

    print("Calculating flow accumulation...")

    wbt.d8_flow_accumulation(
        filled,
        accumulation,
        out_type="cells"
    )

    # --------------------------------------------------------
    # 4. Watersheds
    # --------------------------------------------------------
    #
    # A true watershed needs outlet/pour points.
    #
    # Since we don't have outlet points yet, we first generate
    # watershed basins automatically from the DEM.
    # --------------------------------------------------------

    print("Calculating drainage basins...")

    wbt.basins(
        pointer,
        watersheds
    )

    print(f"  Created: {FILLED_DEM_PATH}")
    print(f"  Created: {FLOW_DIRECTION_PATH}")
    print(f"  Created: {FLOW_ACCUMULATION_PATH}")
    print(f"  Created: {WATERSHEDS_PATH}")


# ============================================================
# DRAINAGE WATER
# ============================================================

def create_drainage_water():

    print("\nCombining flow accumulation with water mask...")

    with rasterio.open(FLOW_ACCUMULATION_PATH) as acc_src:
        accumulation = acc_src.read(1)

        profile = acc_src.profile.copy()

    with rasterio.open(WATER_PATH) as water_src:
        water = water_src.read(1)

    drainage_water = np.where(
        water == 1,
        accumulation,
        0
    ).astype(np.float32)

    profile.update(
        dtype="float32",
        nodata=0,
        compress="deflate"
    )

    with rasterio.open(
        DRAINAGE_WATER_PATH,
        "w",
        **profile
    ) as dst:

        dst.write(drainage_water, 1)

    print(f"  Created: {DRAINAGE_WATER_PATH}")


# ============================================================
# MAIN
# ============================================================

def main():

    #validate_rasters()

    print("=" * 60)
    print("TERRAIN ANALYSIS")
    print("=" * 60)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    create_slope_aspect()
    create_hydrology()
    #create_drainage_water()

    print("\n" + "=" * 60)
    print("TERRAIN ANALYSIS COMPLETE")
    print("=" * 60)

    print("\nOutputs:")
    print(f"  Slope:             {SLOPE_PATH}")
    print(f"  Aspect:            {ASPECT_PATH}")
    print(f"  Filled DEM:        {FILLED_DEM_PATH}")
    print(f"  Flow direction:    {FLOW_DIRECTION_PATH}")
    print(f"  Flow accumulation: {FLOW_ACCUMULATION_PATH}")
    print(f"  Watersheds:        {WATERSHEDS_PATH}")
    print(f"  Drainage water:    {DRAINAGE_WATER_PATH}")

if __name__ == "__main__":
    main()