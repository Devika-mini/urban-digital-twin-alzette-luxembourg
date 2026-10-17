# Devika: static Alzette layers

## Status and first milestone

Step 1 only: independent scaffold and workflow documentation. Preparation scripts
are explicit placeholders that exit with an error; modules contain no processing
logic. Configuration is a planning template, not an implemented command interface.
SLD files will be authored after inspecting the data. No layers have been ingested
or visualised by this work.

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

Future configuration paths should resolve relative to `devika/`, independently of
the working directory. Do not adopt ambiguous top-level `from src...` imports from
other contributors. The command/import convention will be established in Step 2.

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

## Intended preparation workflow — not implemented

1. Supply sources outside Git or under ignored `devika/data/`; configure local paths
   in ignored `config.local.yaml` once local overrides are implemented.
2. Read the selected source layer, inspect CRS and required attributes, validate
   geometries, and document any repairs or rejected features. Never assign a guessed
   CRS to coordinates or silently discard invalid records.
3. Select a manageable initial region using an explicit AOI file or bounding box
   with its CRS. Do not hard-code Hesperange as the permanent Alzette boundary.
4. Preserve styling/inspection fields and transform coordinates to EPSG:4326 for
   the planned GeoJSON export. Use a metric projected CRS if calculating area.
5. Write outputs under ignored `devika/outputs/`, verify nonempty features, geometry,
   attributes, bounds and CRS by reading them back, then stage only intended exports
   into EDDIE for deployment.

GeoPandas, its vector I/O dependencies and PyYAML are expected for preparation.
Versions and an installation command will be established with the Step 2 tests;
no new dependency installation is required for this scaffold.

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

Step 1 inspected source code and scaffold structure only. No source datasets,
PostGIS ingestion, GeoServer styles, browser behaviour or DEM alignment were tested.
Cloud workspace changes do not automatically update the user's Mac or GitHub fork.
