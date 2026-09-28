from pathlib import Path

import pyogrio

# Table inside the land cover GDB mapping LC2024 codes to human-readable names.
LEGEND_LAYER: str = "LandCover_legend"


def load_legend(gdb_path: str | Path) -> dict[int, str]:
    # Read the code -> name table once; reused for plot labels and for the
    # class -> group mapping in Step 3.
    legend = pyogrio.read_dataframe(gdb_path, layer=LEGEND_LAYER)
    return dict(zip(legend["code"], legend["name"]))
