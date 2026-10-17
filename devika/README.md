# Devika: static Alzette layers

## Status and first milestone

Standalone land-use and ownership preparation are implemented with synthetic tests.
The cadastral command remains a placeholder. A bounded raw-XML land-cover inspector
is available; land-cover export awaits verification of the actual classification schema. Styles, EDDIE ingestion and frontend
configuration are deferred to subsequent steps. The user validated a real LIS-L export on their Mac: 1,959 clipped polygons in
EPSG:4326, 5,566,016 bytes, with 6 relevant polygon-part repairs. Ownership remains
unverified on real data. No layer has been published by this work.

First milestone: one correctly styled LIS-L 2024 land-use layer over the existing
EDDIE 3D terrain, with layer toggling, a legend, and clickable attributes. Ownership
follows; cadastral parcels are optional. Dynamic AOI statistics and new EDDIE
processing plugins are outside this phase.

## Organisation

This follows `../robin/` in separating configuration, command entry points, and
reusable Python modules. It does not import or modify Robin's code.

- `config.yaml`: source metadata, configurable subset, output and integration paths.
- `config/`: future category mappings and TerriaJS catalog fragments.
- `scripts/prepare_*.py`: future command-line entry points.
- `src/`: standalone preparation functions, without EDDIE imports.
- `styles/`: future GeoServer SLD assets; see its README.
- `tests/`: future small synthetic preparation fixtures and checks.

Keep spatial analysis separate from preparation; it is deferred. EDDIE publication
is a separate deployment step using the existing framework. Do not build another
ingestion implementation inside these preparation modules.

Data paths resolve relative to `devika/`, independently of the working directory.
The CLI uses the namespaced `devika.src` import; it does not import another
contributor's top-level `src` package. An explicit `--config` file path itself is
relative to the shell working directory.

## Inspection findings

The inspected checkout contains 132 tracked files under `EDDIE/`, despite the outer
`.gitignore` containing `EDDIE/`. Ignore rules do not remove tracked files. Verify
availability in each deployment rather than assuming it from the ignore rule.

None of these source datasets was found in the cloud workspace:

| Dataset | Source | Required metadata |
| --- | --- | --- |
| LIS-L 2024 | `landuse-luxembourg-07-15-18-21-24.gpkg` | Layer `LandUse_status_2024`; `LU1_level__3_name` |
| Ownership 2019 | `owner-type-grid.geojson` | `TOP_LEFT`, `PUBLIC_PERCENT`, `Commune_percent`, `Etat_percent`, `Autre_percent` |
| PCN parcels | `pcn-shape/PARCELLES.shp` and sidecars | `ID_PARCELL`, `CODE_NATUR`; separate category lookup |

Other useful ownership fields must be preserved when present. Ownership percentages
represent aggregated 1 km² grid cells, not individual parcel ownership. The actual
schema, CRS, category values and lookup remain unverified until sources are supplied.

## Land-use preparation

Use Python 3.11 or newer. From the repository root, create an isolated environment:

```bash
python3 -m venv devika/.venv
source devika/.venv/bin/activate
python -m pip install -r devika/requirements-dev.txt
python -m pytest devika/tests -q
```

The dependency ranges allow current compatible wheels. Validation in this cloud
checkout used Python 3.12, GeoPandas 1.2.0, Shapely 2.2.0 and Pyogrio 0.13.0; this is
not a frozen lockfile. The user also installed these dependencies and passed the
original 21 tests on an Apple silicon Mac with Python 3.14.3; the current clipping
changes still require the local test run below.

Place the original GeoPackage under ignored `devika/data/` or use an absolute path.
For an initial small test, the following bbox is an **example**, not a permanent
boundary. Replace it or use an AOI file for other Alzette regions:

```bash
python devika/scripts/prepare_landuse.py \
  --source data/landuse-luxembourg-07-15-18-21-24.gpkg \
  --bbox 6.115 49.548 6.178 49.597 --bbox-crs EPSG:4326
```

Alternatively:

```bash
python devika/scripts/prepare_landuse.py \
  --source /absolute/path/to/landuse-luxembourg-07-15-18-21-24.gpkg \
  --aoi data/my_alzette_aoi.geojson \
  --output outputs/landuse_alternative_aoi.geojson
```

AOI files must contain valid Polygon/MultiPolygon features with an EPSG-resolvable
CRS. Multi-layer AOI containers use their default layer; prefer a single-layer AOI
file. The bbox requires its CRS explicitly. CLI bbox/AOI selection overrides the
configured selection. No national export occurs by default.

The command reads `config.yaml`. For local settings, create ignored
`devika/config.local.yaml` with only the sections to override, for example:

```yaml
sources:
  landuse:
    path: data/landuse-luxembourg-07-15-18-21-24.gpkg
subset:
  bbox: [6.115, 49.548, 6.178, 49.597]
  bbox_crs: EPSG:4326
```

Run `python devika/scripts/prepare_landuse.py --config devika/config.local.yaml`.
Local overrides are loaded only when explicitly selected. CLI source/output options
take precedence. `--help` lists available arguments.

The implementation:

1. Requires a configurable AOI file or a bbox with an explicit CRS, and the source
   `LU1_level__3_name` field. It never guesses a missing CRS.
2. Transforms the AOI bounds into the source CRS and reads spatial candidates.
   **The driver still reads whole national MultiPolygon features**, but polygon
   components with envelopes outside the AOI envelope are excluded before expensive
   validity checks and repair. Progress messages identify reading, clipping, repair
   and export validation stages.
3. Checks locally relevant polygon parts, optionally repairs invalid parts with
   `--repair-invalid`, and intersects their actual geometry with the AOI. This
   replaces the earlier whole-feature selection that produced oversized GeoJSON.
4. Reprojects clipped pieces to EPSG:4326, intersects again with the AOI represented
   in that CRS, and writes individual **2D (XY)** Polygon features. Source geometry
   Z coordinates are removed only in the exported copy: the existing terrain
   supplies display elevation. Height attribute columns remain unchanged. The
   report records `source_candidates_with_z` and `output_pieces_with_z_removed`.
   This avoids GDAL interpreting a 3D GeoJSON as EPSG:4979 instead of EPSG:4326. Source attributes are
   repeated unchanged for each split piece. No category remapping or AOI statistics
   are calculated. Zero-area boundary contacts are excluded and recorded.
5. Serializes full-precision GeoJSON with right-hand polygon winding, then reads it
   independently through GDAL/Pyogrio. Checks include EPSG, valid nonempty polygons,
   feature count, attribute names, category values and AOI containment (including
   holes). A tolerance of 2e-9 degrees, roughly 0.2 mm, accommodates numerical error;
   it is not an AOI expansion for selecting features.
6. Enforces a default **25 MiB total file** and **4 MiB serialized-feature** limit
   before GDAL reads the export. These can be configured through `output.max_file_mb`,
   `output.max_feature_mb`, `--max-output-mb` or `--max-feature-mb`. Prefer reducing
   the AOI if either limit is exceeded. The `--max-features` limit (default 50,000)
   caps both source candidates and final polygon pieces without silent truncation.
7. Writes the validated GeoJSON and a `.report.json` sidecar under `outputs/`.
   The report includes source and output counts, categories, CRS, AOI/output bounds,
   byte sizes, validation results, excluded components, repairs and versions.
   The Terminal prints a compact summary; full per-part records stay in the sidecar.
   `output_feature_lineage` maps each output row (zero-based list position) back to
   a source FID and source polygon-part index. Category counts are **output polygon
   piece counts**, not original national feature counts. GeoJSON field types follow
   JSON conventions; date/time values are represented as ISO strings.

Existing outputs or reports are never overwritten: select a new `--output` name
for a rerun. On failure, no validated GeoJSON is published; a uniquely named
`.failure-<timestamp>.json` retains the error and any accumulated repair diagnostics.
Inspect that file and the progress output before retrying. A `round_trip` section
records expected and observed CRS, feature counts and Z-coordinate counts when
the read-back stage is reached. Temporary exports are
removed automatically. All outputs/reports remain in ignored `outputs/` by default.

### Explicit geometry repair

The user's local LIS-L sample contains 53 MultiPolygon candidates in EPSG:2169;
21 whole features report ring self-intersections. Many components may be outside
the AOI, so the new part-level repair count need not equal 21. Use:

```bash
python devika/scripts/prepare_landuse.py \
  --source data/landuse-luxembourg-07-15-18-21-24.gpkg \
  --bbox 6.115 49.548 6.178 49.597 --bbox-crs EPSG:4326 \
  --repair-invalid --output outputs/alzette_landuse_2024_clipped.geojson
```

`make_valid` (linework) runs on locally relevant invalid polygon parts in the source
CRS, entirely in memory. The source GeoPackage is never written. Without the flag,
invalid relevant parts remain errors. Remote parts are not validated. AOI geometries
must already be valid and are never automatically repaired.

Each attempted repair records source FID/part index, original validity reason,
status, original/result type, polygon-piece count and before/after area in source
CRS squared units. EPSG:2169 uses square metres; invalid pre-repair areas are only
diagnostics, not reliable reference measurements. GeometryCollection results retain
all polygon components; collapsed lines/points are omitted **with their types/counts
recorded explicitly**. A repair with no valid polygon area fails. Clipping-created
nonpolygon contacts are similarly recorded, and no source attributes are discarded.

Tests use synthetic multipart, self-intersecting, collapsed, holed and disconnected
geometries, with geographic and projected AOIs. The real LIS-L file remains on the
user's Mac: its clipped export has not yet been verified in the cloud. Review the
report and inspect the local output before proceeding to EDDIE integration.

Preparation does not copy anything into EDDIE or contact PostGIS/GeoServer. That is
Step 3. Styles must be based on observed category values, not guessed labels.

## Ownership preparation — full grid cells

Ownership is a separate dataset from LIS-L. Place `owner-type-grid.geojson` in
ignored `devika/data/` (or supply its absolute path). It is not present in the cloud
workspace; no real-data ownership counts, CRS or schema are claimed yet.

Reuse the same virtual environment and install requirements. From repository root:

```bash
python -m pytest devika/tests -q
python devika/scripts/prepare_ownership.py \
  --source data/owner-type-grid.geojson \
  --bbox 6.115 49.548 6.178 49.597 --bbox-crs EPSG:4326 \
  --output outputs/alzette_ownership_2019.geojson
```

The example uses the same test region as land use. The bbox remains configurable;
`--aoi data/my_alzette_aoi.geojson` selects an alternative polygon AOI. Both commands
read the shared `subset` settings and accept `--config devika/config.local.yaml`.
Set `sources.ownership.path` there to avoid passing `--source`. No AOI is assumed
if neither configuration nor CLI supplies one.

**Ownership percentages describe the complete nominal 1 km² grid cells, not exact
parcel ownership or ownership percentages within the selected AOI.** The command
selects cells that intersect the AOI (including boundary-only touches) and exports
their **whole horizontal footprints**. Cells will normally extend outside the AOI.
It does not clip, explode, repair, allocate percentages, or calculate AOI statistics.
Invalid cells are rejected for inspection rather than silently changing their grid.

Validation and preservation:

- Require an EPSG-resolvable source/AOI CRS and valid nonempty polygon geometries.
  GeoJSON's standard WGS84 interpretation is used by the reader where applicable;
  no manual CRS override is guessed.
- Require `TOP_LEFT`, `PUBLIC_PERCENT`, `Commune_percent`, `Etat_percent`, and
  `Autre_percent`. `TOP_LEFT` must be nonempty and unique among selected cells.
  Additional required fields can be listed under `sources.ownership.fields`.
- Preserve **all** source attribute columns, including `Domaine_public_percent`
  and any other category percentages. Validate fields containing `percent`
  (case-insensitive) as finite values from 0 to 100. Numeric strings are validated
  but preserved; they generate a field-type warning for future styling.
- Preserve null percentages without treating them as zero; report null counts and
  reject an entirely null selected `PUBLIC_PERCENT` column. Do not require category
  totals to equal 100%, because totals and subcategories can overlap.
- Export EPSG:4326 GeoJSON with full coordinate precision. Z coordinates, if present,
  are removed only from the exported geometry, with the count recorded; source
  footprints and all height **attributes** remain intact. Terrain supplies elevation.
- Read back and compare feature count, CRS, complete transformed geometries, all
  attribute names and values. The original source is opened only for reading.
- Report minimum/maximum complete-cell area in EPSG:2169 as a grid sanity check.
  Flag areas differing from nominal 1 km² by more than 1%, but retain the original
  geometry for review. This is not an ownership composition calculation.
- Apply the shared candidate, total-file and individual-feature limits and refuse
  to overwrite existing outputs. Failure diagnostics are saved separately.

Outputs are `outputs/alzette_ownership_2019.geojson` and its `.report.json` sidecar.
The report includes the whole-cell interpretation warning, source and output CRS,
selection, counts, field validation, original FIDs, geometry and attribute read-back
results, grid-area checks, warnings, and file sizes. Review these before ingestion.
The Terminal prints a summary; source FIDs remain in the full sidecar.

Synthetic tests verify full 1 km² cells survive tiny-AOI selection without clipping,
source checksums remain unchanged, unknown percentage fields are preserved, polygon
AOI holes filter correctly, boundary touches are included, invalid percentages and
IDs fail, nulls/numeric strings are preserved, and the CLI works outside repo root.
**Real ownership validation is pending.** Stop after this preparation step. Land
cover must be identified independently after confirmation; do not substitute LIS-L
land use for land cover. EDDIE publication planning for three layers is deferred
until all three datasets have passed validation.

## Land-cover GML inspection (before preparation)

The user's local metadata inspection found these layers in
`data/raw/landcover/lc.lisl-landcover2024-luxembourg.gml.gz`:

- `LandCoverDataset`: one metadata record describing LIS-L Land Cover 2024.
- `LandCoverUnit`: 469,288 features; source CRS EPSG:3035; OGR geometry type Unknown.
- Reported EPSG:4326 bounds: approximately 5.990724, 49.511251, 6.317782, 49.698323.
  These bounds include our test AOI but do not establish complete feature coverage.
  This is a regional extract despite the national parent metadata; the filename
  alone must not be interpreted as national coverage.
- The basic GML driver exposed identifiers and generic metadata, but no `LC2024`
  field or legend table. Robin's GDB layer/field assumptions are not verified for
  this GML and must not be copied blindly.

The source is on the user's Mac, not in the cloud workspace. Before implementing
conversion, inspect the nested XML directly with the versioned command below:

```bash
python devika/scripts/inspect_landcover.py \
  --source data/raw/landcover/lc.lisl-landcover2024-luxembourg.gml.gz
```

The command reads `.gml` or `.gml.gz` sequentially, without extracting the gzip to
disk or rescanning the entire dataset for counts. It stops after three complete
`LandCoverUnit` elements by default, with a 64 MiB decompressed scan limit. It
preserves the source and creates no GFS sidecar or geometry export. It does not
fetch remote schema files, legends or linked classifications. No extra dependency
installation is needed beyond the existing preparation environment.

An ignored `outputs/landcover_inspection-<timestamp>.json` report records:

- XML namespaces and schema-location attributes;
- encountered dataset metadata and nomenclature references;
- nested unit field paths, values, attributes and links;
- candidate class fields (heuristic suggestions, not verified classifications);
- sampled GML geometry element types, CRS identifiers and a few coordinate tokens;
- sample size, bytes read, source file metadata and any field-text truncation.

The Terminal prints a compact report including the first unit's nongeometry fields.
Share that output or the small JSON report for review. Large coordinate arrays are
omitted. A sample cannot prove national feature counts, full geometry validity,
complete class coverage or an official code-to-label mapping. If metadata appears
after the sampled units, it will not be included. If a record exceeds the default
scan budget, the inspector fails rather than silently reading the whole file;
`--max-scan-mb` may be increased deliberately, up to 1024. `--sample-units` controls
sample count (1–100). Malformed/truncated XML and unsupported DTD/entity declarations
produce explicit errors.

After the actual code paths and legend have been verified, the preparation command
can reuse the tested clipping/repair/export workflow while retaining original
land-cover codes and joining verified readable labels. **No land-cover preparation
or EDDIE ingestion command is implemented by this inspection step.** Do not use
the generic dataset title as a feature class or substitute land-use categories.

## Verified EDDIE integration contract

Paths below are relative to `../EDDIE/eddie_antarctica/`:

- Correct ingestion directory: **`src/static/geo/`**.
- Do not use `lib/eddie/src/static/geo/`; that is the framework source tree.
- `lib/eddie/src/eddie/digitaltwin/data_to_db.py` defines `serve_static_files` and
  `add_vector_file_to_db`. Supported vector suffixes are `.geojson`, `.shp`, and
  `.geodb`; `.gpkg` is not dispatched. GeoJSON is the planned interchange format.
- Input CRS must resolve to an EPSG code. The static reader does not reproject or
  repair vectors. Missing CRS is not handled gracefully, so validate beforehand.
- The filename stem becomes the PostGIS table name. Loading uses
  `if_exists="replace"`; ingesting the directory can replace all matching tables.
  Use distinct names such as `alzette_landuse_2024` and inventory existing inputs.
- `geoserver/database_layers.py` publishes vectors in `static_files`. Existing layers
  are skipped; changed bounds/schema may require an explicit metadata refresh.
- Files in the `3d/` subdirectory use extrusion. Terrain-draped overlays belong in
  the normal static directory.
- `geoserver/raster_layers.py:add_style` uploads `.sld` files under their filename
  stem. Uploading a style does not assign it as a vector layer's default style.
- `geoserver/terria_catalogs.py` generates vector **WFS** items (60,000-feature cap).
  SLD styling is not automatically applied to those client-rendered features.
- `src/eddie_antartica/app.py` exposes `/terria-catalog.json`, nesting discovered
  layers under `Intermediate Layers`, then `Static Files`.
- `terriajs/client_config.json` loads that dynamic catalog and `terriajs/catalog.json`.
  The latter currently has an empty explicit catalog.

For styled land use, plan one explicit **WMS** item in the application catalog with
layer `static_files:alzette_landuse_2024` and the uploaded SLD style. Use existing
TerriaJS legend and GeoServer GetFeatureInfo support; verify both at runtime. WMS
can overlay the existing terrain without changing the terrain pipeline. Keep the
existing `/terrain` endpoint, `TERRAIN_DATA_DIR`, tiles and DEM setup intact.

## Deployment prerequisites and later validation

The worker's Docker build copies `src/` into `/app/src/`. The inspected override
mounts weather code/configuration but not static inputs. New inputs therefore need
a worker image rebuild/recreation or an explicit local mount. Do not assume a file
copied onto the host is visible inside a running container.

Use EDDIE's `setup_environment.get_database()` for ingestion: it uses AUTOCOMMIT,
allowing GeoServer's separate database connection to see published tables. The
reference command using a plain SQLAlchemy connection and closing without a commit
must not be copied unchanged. Verify the container Python path before running.

Required services: PostGIS, GeoServer, backend and the worker for the documented
command path; Redis supports worker operation. Docker images, credentials, volume
mounts and Mac CPU/GPU compatibility need deployment-specific verification. Never
store secrets in scripts, tracked YAML or documentation.

After implementation, check:

1. PostGIS row counts, EPSG/SRID, bounds, geometry validity and retained attributes.
2. GeoServer layer availability, WMS GetMap, SLD legend and GetFeatureInfo response.
3. TerriaJS catalog visibility, toggling, readable legend, clicked attributes and
   alignment with the existing terrain.
4. Ownership legends/popups explicitly describe grid-level aggregation.

Troubleshooting: missing layer -> inspect ingestion logs and container input paths;
uniform colours -> verify WMS item and selected SLD; missing click data -> inspect
GetFeatureInfo and attribute names; displaced polygons -> verify source CRS and
coordinate transformation; missing terrain -> inspect existing tiles and endpoint
without overwriting the team's setup.

## Git and verification boundaries

Work on a separate branch in the fork. Do not merge into main or push upstream.
Commit only small scripts, configuration templates, styles, tests and documentation.
`data/`, `outputs/`, `results/`, local configuration and secrets are ignored here.
Generated files copied into EDDIE need their own local exclusion: the outer EDDIE
ignore rule does not protect paths that are already tracked. Review Git status
before any later commit.

Step 2 is tested using synthetic GeoPackages and AOI files, including projected
coordinates, retained attributes, invalid inputs, candidate limits, and CLI use
from another directory. No real source datasets, PostGIS ingestion, GeoServer
styles, browser behaviour or DEM alignment were tested.
Cloud workspace changes do not automatically update the user's Mac or GitHub fork.
