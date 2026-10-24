"""Inventory exact original labels and cleaned display labels without changing data."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from devika.src.merge_landuse import FeatureReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Prepared GeoJSON, relative to devika/ or absolute.')
    args = parser.parse_args()
    counts = Counter()
    for feature in FeatureReader(ROOT / 'devika' / args.source):
        if isinstance(feature, tuple):
            feature = feature[1]
        counts[feature['properties'].get('LU1_level__3_name')] += 1
    print(json.dumps([{'original_label': k, 'display_label': k.strip() if isinstance(k, str) else None,
                       'polygon_count': v} for k, v in sorted(counts.items(), key=lambda x: str(x[0]))], indent=2))


if __name__ == '__main__':
    main()
