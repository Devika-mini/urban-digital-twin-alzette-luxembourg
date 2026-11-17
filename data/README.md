# The data folder

Everything in `data/` except this README is git-ignored: the raw data is copied in by hand on each
computer. `./start.sh` checks it before starting and stops with the list of anything missing.
It only **reads** `data/raw/`; nothing in it is modified or overwritten.

## Layout

```
data/
├── README.md                                  this file (the only tracked one)
├── raw/                                       the raw inputs: provided by you
│   ├── filled_dem.tif                         REQUIRED  LiDAR DEM of the reach (LUREF, EPSG:2169, gaps filled)
│   ├── River_kilometers/
│   │   └── kilometrage-des-cours-deau.gpkg    REQUIRED  official river kilometre markers
│   ├── Buildings/
│   │   ├── ACT2023v2_Buildings3d_Footprints.gpkg   REQUIRED  3D building footprints (ACT 2023)
│   │   ├── luxembourg.gpkg                    REQUIRED  OpenStreetMap extract (river channel, place names)
│   │   └── inspire_building3d/                optional  bu.building3d-<commune>.gml: building heights
│   ├── Flood_hazard/                          REQUIRED  official flood hazard maps (HWGK 2021), shapefiles
│   │   ├── HWGK2021_HQ10/HWGK2021_HQ10.shp (+ .shx .dbf .prj …)
│   │   ├── HWGK2021_HQ100/HWGK2021_HQ100.shp (+ …)
│   │   └── HWGK2021_HQext/HWGK2021_HQext.shp (+ …)
│   ├── Communes/
│   │   └── communes4326.geojson               optional  commune boundaries (flood reports per commune)
│   └── static_geo/                            optional  model inputs, copied into
│                                                        EDDIE/eddie_antarctica/src/static/geo/ (see below)
└── flood_costs/                               created by start.sh: working folder of the flood-cost pipeline
```

## Where the files come from

| File | Source |
|---|---|
| `filled_dem.tif` | Made from the LiDAR 2024 point clouds (data.public.lu, "LiDAR 2024 - relevé 3D du territoire luxembourgeois") by the pipeline in `users/Luiz Ganem/src/` (`RunPipeline.py`: MakeDem, then TerrainAnalysis writes `filled_dem.tif`) |
| `kilometrage-des-cours-deau.gpkg` | data.public.lu (river kilometre markers) |
| `ACT2023v2_Buildings3d_Footprints.gpkg` | data.public.lu, "Base de données nationale des bâtiments 3D 2023" (unzipped) |
| `luxembourg.gpkg` | OpenStreetMap extract of Luxembourg from Geofabrik, as GeoPackage |
| `inspire_building3d/*.gml` | data.public.lu, "INSPIRE - Annex III Theme Buildings - Building 3D", one file per commune |
| `HWGK2021_HQ10/100/ext` | data.public.lu, flood hazard maps 2021 (`hwgk2021-hq10.zip`, `-hq100.zip`, `-hqext.zip`, unzipped) |
| `communes4326.geojson` | data.public.lu, "Limites administratives du Grand-Duché de Luxembourg" |

### `static_geo/` (optional)

Files placed here are copied into `EDDIE/eddie_antarctica/src/static/geo/`, where the population and
water-fee model (`eddie_building_population`) and the flood-cost pipeline (`eddie_flood_costs`) read them.
Without them those two models report that their inputs are missing; the rest of the twin works.
`kilometrage-des-cours-deau.gpkg` is copied there automatically from `River_kilometers/`.

| File | Used by |
|---|---|
| `BU.Building.gml`, `LU00.gpkg` | building footprints and heights (population model) |
| `LIMADM_COMMUNES.shp` (+ .shx .dbf .prj) | commune boundaries (population model) |
| `rnpp_population_per_municipality.csv` | population per commune (population model) |
| `copy_of_global_flood_depth-damage_functions__30102017.xlsx` | JRC depth-damage functions (flood costs) |
| `provisionally_classified_buildings.csv`, `building_jrc_osm_classification.csv`, `classification_review_decisions.json`, `target_manifest.json` | reviewed building classifications (flood costs) |

## What is generated from it

`./start.sh` derives these, skipping each one while it is newer than its inputs
(`./start.sh --force` rebuilds them, `./start.sh reset` deletes them). They are git-ignored and live
outside `data/`:

| Output | From |
|---|---|
| `EDDIE/eddie_antarctica/data/terrain/dem_merged.tif` | `raw/filled_dem.tif` (master DEM the backend reads; also sets the map's home view) |
| `EDDIE/eddie_antarctica/data/terrain/lidar_egm2008/` | the master DEM: 3D terrain tiles with ellipsoid heights (EGM2008 geoid) |
| `EDDIE/eddie_antarctica/data/rem/` | the master DEM and the OSM river channel: Relative Elevation Model |
| `EDDIE/eddie_antarctica/src/static/geo/<staged files>` | `raw/static_geo/*` and the river kilometre markers |

The database and GeoServer contents (Docker volumes) are filled when the services start: base data,
static layers, the default area of interest, and the gauge history from heichwaasser.lu.

## Versioned flood-cost releases

Keep completed monetary results outside Git under `data/flood_costs/`, including
`releases/RELEASE_ID/eddie_flood_costs_lookup_v2.json` and the exact matching
`building_flood_damage.geojson`. The backend mounts this directory read-only;
its optional `FLOOD_COSTS_LOOKUP_PATH` and `FLOOD_COSTS_DETAILS_PATH` must select
one immutable release pair. Empty lookup configuration preserves database mode.
The lookup contains the source GeoJSON SHA-256; reformatting that GeoJSON breaks
context verification. Keep previous releases for rollback.

Schema 2 supports HQ10/HQ100/HQextreme for the combined 507-building inventory,
with 271 approved provisional classifications. Original HQ10/HQ100 results remain
unchanged; the 87 new approvals retain null/unassessed HQ10/HQ100 amounts. The
remaining pending/unresolved/excluded buildings are not priced as zero.

Retain raw inputs, original baseline manifests, frozen approval snapshots, active
classification ledgers/evidence and pre-approval backups externally too. Do not
commit monetary CSV/GeoJSON, lookup JSON, sample archives, workbooks or rasters.
See `eddie_flood_costs/README.md` for release validation, explicit calculation
configuration, the optional database migration preflight and rollback procedure.
