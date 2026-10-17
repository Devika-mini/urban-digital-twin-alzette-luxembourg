"""Inspect nested GML classification fields without exporting any geospatial data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from devika.src.landcover_inspection import InspectionError, inspect_landcover, save_inspection

DEVIKA_ROOT = REPO_ROOT / "devika"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read a bounded raw GML sample, including nested classifications.")
    parser.add_argument("--source", required=True, help="GML or .gml.gz; relative paths resolve from devika/.")
    parser.add_argument("--sample-units", type=int, default=3)
    parser.add_argument("--max-scan-mb", type=int, default=64, help="Limit on decompressed XML read (default 64 MiB).")
    parser.add_argument("--report-dir", default="outputs", help="Inspection report directory, relative to devika/.")
    args = parser.parse_args(argv)
    def resolve(value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else DEVIKA_ROOT / path
    print("Reading a bounded XML sample; no national scan or geometry export...", file=sys.stderr, flush=True)
    try:
        report = inspect_landcover(resolve(args.source), sample_units=args.sample_units, max_scan_mb=args.max_scan_mb)
        destination = save_inspection(report, resolve(args.report_dir))
    except (InspectionError, OSError, ValueError) as error:
        parser.exit(2, f"Inspection failed: {error}\n")
    summary = {key: value for key, value in report.items() if key not in ("dataset_metadata", "unit_samples")}
    summary["metadata_classification_candidates"] = [
        entry for sample in report["dataset_metadata"] for entry in sample["classification_candidates"]
    ]
    summary["unit_classification_candidates"] = [sample["classification_candidates"] for sample in report["unit_samples"]]
    # If keyword matching finds no class, show all nongeometry fields of the first
    # unit so a differently named schema field can still be diagnosed.
    summary["first_unit_fields"] = report["unit_samples"][0]["fields"]
    summary["report_path"] = str(destination)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
