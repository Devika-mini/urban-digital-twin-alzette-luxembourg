#!/bin/bash

# Builds a Cesium quantized-mesh terrain tileset from a DEM GeoTIFF and installs it into the
# stored_data Docker volume, where the backend serves it at /terrain (see src/eddie_antartica/app.py).
# Only Docker is required; Cesium Terrain Builder runs in a container.
#
# Usage: scripts/build_terrain.sh <dem_4326.tif> [--volume NAME]
#   dem_4326.tif  Must already be EPSG:4326 with final heights and no no-data pixels: ctb-tile reads
#                 no-data values as real heights. scripts/prepare_dem.py produces this and calls this script.
#   --volume      Docker volume mounted at /stored_data. Default eddie_antarctica_antarctic_stored_data.
#
# Replaces any existing tileset. Hard-refresh the map (Ctrl+F5) afterwards.

set -euo pipefail

CTB_IMAGE=tumgis/ctb-quantized-mesh

DEM=""
VOLUME=eddie_antarctica_antarctic_stored_data

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volume) VOLUME="$2"; shift 2 ;;
    -h|--help) sed -n '3,13p' "$0"; exit 0 ;;
    *) DEM="$1"; shift ;;
  esac
done

if [[ -z "$DEM" || ! -f "$DEM" ]]; then
  echo "Error: DEM file not found: '$DEM'" >&2
  sed -n '7,7p' "$0" >&2
  exit 1
fi

DEM_DIR=$(cd "$(dirname "$DEM")" && pwd)
DEM_NAME=$(basename "$DEM")

# Docker Desktop on Windows needs C:/... style paths, and Git Bash must not rewrite container paths.
if command -v cygpath > /dev/null; then
  DEM_DIR=$(cygpath -m "$DEM_DIR")
fi
export MSYS_NO_PATHCONV=1

echo "==> Building quantized-mesh tiles from $DEM_NAME into volume $VOLUME at /stored_data/terrain"
docker run --rm -v "$DEM_DIR:/work:ro" -v "$VOLUME:/stored_data" "$CTB_IMAGE" bash -c "
  set -e
  rm -rf /stored_data/terrain
  mkdir -p /stored_data/terrain
  ctb-tile -q -f Mesh -C -N -o /stored_data/terrain '/work/$DEM_NAME'
  ctb-tile -q -f Mesh -C -N -l -o /stored_data/terrain '/work/$DEM_NAME'
  chmod -R a+rX /stored_data/terrain
  echo \"Tiles: \$(find /stored_data/terrain -name '*.terrain' | wc -l), size: \$(du -sh /stored_data/terrain | cut -f1)\"
"

echo "==> Done. Terrain is served at \$BACKEND_URL/terrain/layer.json"
