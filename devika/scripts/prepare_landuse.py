"""Command line for standalone LIS-L preparation; no EDDIE services required."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support an absolute script path from any working directory, without importing
# another contributor's top-level `src` package.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml
from devika.src.landuse import prepare_landuse

DEVIKA_ROOT = REPO_ROOT / "devika"


def merge(base, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def resolve_path(value):
    if value is None:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else DEVIKA_ROOT / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare an AOI-bounded LIS-L GeoJSON for later EDDIE ingestion.")
    parser.add_argument("--config", type=Path, help="Explicit YAML overrides; relative data paths resolve from devika/.")
    parser.add_argument("--source", help="Source GeoPackage; relative to devika/.")
    parser.add_argument("--output", help="New .geojson output path; relative to devika/.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--bbox", nargs=4, type=float, metavar=("XMIN", "YMIN", "XMAX", "YMAX"))
    selection.add_argument("--aoi", help="Polygon AOI file with CRS; relative to devika/.")
    parser.add_argument("--bbox-crs", help="Explicit bbox CRS, e.g. EPSG:4326.")
    parser.add_argument("--max-features", type=int, help="Maximum spatial candidates to read (default 50000).")
    parser.add_argument("--repair-invalid", action="store_true",
                        help="Repair locally relevant invalid parts; record any non-polygon remnants.")
    parser.add_argument("--max-output-mb", type=float, help="Maximum GeoJSON size in MiB (default 25).")
    parser.add_argument("--max-feature-mb", type=float, help="Maximum serialized feature size in MiB (default 4).")
    args = parser.parse_args(argv)
    try:
        config = yaml.safe_load((DEVIKA_ROOT / "config.yaml").read_text())
        if args.config:
            override = yaml.safe_load(args.config.read_text())
            if not isinstance(override, dict):
                raise ValueError("Override configuration must be a YAML mapping.")
            merge(config, override)
        source = config["sources"]["landuse"]
        subset = config["subset"]
        output = config["output"]
        if output["format"] != "GeoJSON" or output["crs"] != "EPSG:4326":
            raise ValueError("This preparation command supports GeoJSON in EPSG:4326 only.")
        source_path = resolve_path(args.source or source["path"])
        if source_path is None:
            raise ValueError("Supply --source or sources.landuse.path; no dataset is bundled.")
        bbox, aoi = subset["bbox"], subset["aoi_path"]
        if args.bbox is not None:
            bbox, aoi = args.bbox, None
        elif args.aoi is not None:
            bbox, aoi = None, args.aoi
        report = prepare_landuse(
            source_path,
            resolve_path(args.output or str(Path(output["directory"]) / "alzette_landuse_2024.geojson")),
            layer=source["layer"], category_field=source["category_field"],
            bbox=bbox, bbox_crs=args.bbox_crs or subset["bbox_crs"], aoi_path=resolve_path(aoi),
            repair_invalid=args.repair_invalid,
            max_output_mb=args.max_output_mb if args.max_output_mb is not None else output.get("max_file_mb", 25),
            max_feature_mb=args.max_feature_mb if args.max_feature_mb is not None else output.get("max_feature_mb", 4),
            max_features=args.max_features if args.max_features is not None else subset.get("max_features", 50000),
        )
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, yaml.YAMLError) as error:
        parser.exit(2, f"Preparation failed: {error}\n")
    # Keep terminal output readable; full per-part diagnostics stay in the sidecar.
    summary = {key: value for key, value in report.items()
               if key not in {"repair_records", "geometry_events", "output_feature_lineage"}}
    summary["report_path"] = str(Path(report["output"]).with_suffix(".report.json"))
    summary["geometry_event_count"] = len(report["geometry_events"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
