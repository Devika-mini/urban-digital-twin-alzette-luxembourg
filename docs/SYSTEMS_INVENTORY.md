# Systems inventory: Alzette digital twin

State as of 2026-11-15, after the Casual / In-depth UI work. Paths are relative to the repository root;
`EDDIE/…` is `EDDIE/eddie_antarctica/…`.

**UI**: where a system can be used from the map. *Casual* is the simple panel (`terriajs/casual-ui.js`),
*In-depth* the full panels (`terriajs/water-level-control.js`), *Terria* the generic TerriaJS catalogue / workbench.
**Status**: functional · data-blocked (works, but the data it needs is missing on this machine) · backend-only
(configured by environment variables, needs a restart) · dead (unused code).

## Map and UI

| System | Where | UI | Parameters a user can change | Status |
|---|---|---|---|---|
| Setup and start (one command) | `start.sh` / `start.ps1`; `.env.example`; `data/README.md` | None (terminal) | `--force`, `--no-generate`; `stop`, `logs`, `status`, `reset [--volumes]` | Functional: checks Docker, `.env` and `data/raw/`, generates the derived data in containers, starts and health-checks the stack |
| Mode selection (entry screen, mode switch) | `EDDIE/terriajs/twin-mode.js` | Entry screen; Casual / In-depth switch at the top of the map | Mode (remembered in localStorage) | Functional (new) |
| Casual panel | `EDDIE/terriajs/casual-ui.js` | Casual | Day, play / pause, timeline; 5 on/off buttons | Functional (new) |
| Shared twin state and API (`window.AlzetteTwin`) | `EDDIE/terriajs/water-level-control.js` | Used by both modes | – | Functional (new) |
| In-depth central panel and movable panels | `water-level-control.js` (`build`, `makePanel`) | In-depth | Panel position / size, open categories (kept) | Functional |
| 3D water surface (animated mesh, flow arrows, velocity on hover) | `water-level-control.js` (`buildLevel`, `updateWater`); backend `eddie_water_level/water_surface.py`, `flood_grid.py`, `flood_sections.py`, `rem.py` | Casual *Show river*; In-depth River ▸ Water surface, River panel | Show / hide; flow arrows; **ripple size, ripple period, wave strength, animation fps** (new) | Functional |
| Gauge levels: live, manual, per-gauge use, fly to gauge | `water-level-control.js`; `eddie_water_level/blueprint.py` (`/water-level/*`) | In-depth River panel, Live replay panel; Casual *Back to now* | Stage per gauge, common slider, gauges used, **live check interval** (new) | Functional |
| Gauge collector service (heichwaasser.lu → `water_level_history`) | `gauge_collector/` (port 5002, every 15 min) | Indirect (live level, replay days) | `COLLECT_INTERVAL_MIN` | Functional, backend-only (its HTTP API has no CORS, so it is not called from the map) |
| Day replay of stored gauge readings | `water-level-control.js` (`replayDay`); `/terria-water-init/date/…` | Casual date + play / pause / timeline; In-depth Data replay panel | Day, **playback speed** (new), gauges used | Functional |
| Flood scenarios HQ10 / HQ100 / HQextreme (water fills the official extent) | `water-level-control.js` (`setScenario`); `water_surface.scenario_wse` | In-depth Flood panel | Scenario | Functional |
| Flood report (per scenario, HTML) | `eddie_buildings/flood_report.py` (`/flood-report/…`) | In-depth Flood panel link | – | Functional |
| Flood zones (official HWGK 2021 hazard maps) | **new** `/flood-zones/<scenario>.geojson` (`eddie_water_level/blueprint.py`) | Casual *Show flood areas* (HQ100); In-depth Map layers (HQ10, HQ100, HQextreme) | Which zones | Functional (new) |
| 3D buildings coloured by flooding | `eddie_buildings/buildings_3d.py` (`/buildings-3d.czml`) | Casual *Show buildings*; In-depth Terrain ▸ Buildings | Show / hide | Functional |
| Flood-cost building popup (Devika) | `EDDIE/terriajs/flood-cost-popup.js`; `eddie_flood_costs/flood_costs/blueprint.py` | Click a building; comparison box (In-depth only) | HQ10 / HQ100 comparison | Data-blocked: no cost lookup loaded here (`/flood-costs/*` answers 503), so the popup shows "N/A" |
| Flood damage totals per scenario | `/flood-costs/summary/<scenario>.json` | **New**: In-depth Flood panel, under the report link | – | Wired; data-blocked as above (shows "Damage estimate unavailable") |
| Place names (streets, other) | `eddie_buildings/place_names.py` | Casual *Show place names* (both kinds); In-depth Names | Which kinds | Functional |
| Terrain: LiDAR 3D terrain tiles | `EDDIE/scripts/prepare_dem.py`, `setup_terrain.sh`, `build_lidar_terrain.sh` (run by `start.sh`); `/terrain/…` | Always on | DEM, height offset (scripts) | Functional, backend-only |
| Orthophoto grayscale | `water-level-control.js` (`applyTerrain`) | In-depth Terrain panel | On / off | Functional |
| Slope shading | `eddie_water_level/slope_shading.py` | In-depth Terrain panel | Start angle, full angle, colour, opacity | Functional |
| REM view (height above the river, contours) | `eddie_water_level/rem.py` | In-depth Terrain ▸ REM view | Contour interval, opacity | Functional |
| Sun filter (tint from the sun's position at the time shown) | `water-level-control.js` (`SUN`, `sunTint`) | In-depth Data ▸ Show sun, **Sun settings panel** (new) | **Dawn / dusk length, day / dawn / night tint strength** (new) | Functional |
| Rain: latest interpolated rainfall (live / manual views) | `eddie_precip_interpolation/tasks.py` (`derive_live_precipitation`, every 15 min) → GeoServer `precip_live_test` | Casual *Show rain*; In-depth Map layers ▸ Rain | Show / hide | Wired; data-blocked: no layer is published here, so the layer is left out and the panels say so |
| Rain: interpolated history of a replayed day | `derive_precipitation_history`; `/load-precipitation-period` | Automatic in day replays (Casual and In-depth) with the rain layer on; In-depth Data replay ▸ Prepare rainfall for a period | Period | Functional on a fresh stack (verified with `start.sh`: 3 Nov 2026, 23 hourly surfaces); fails on a database created by the old template (see notes) |
| ASTA rain observations ingest | `eddie_alzette_ingest/` (`fetch_precipitation`) | **New** route `/alzette-ingest/precipitation`, called by the rain preparation | Period (backfill) | Functional (verified: 3 Nov 2026 fetched) |
| Digital Twin date (precipitation + water-level WMS through time) | `EDDIE/terriajs/date-selector.js`; `/load-digital-twin-date`, `/terria-date-init/…` | In-depth Data ▸ Digital Twin date | Day | Functional; reloads the page by design (GeoServer time domain) |
| Water-fee and population model (Pegah) | `eddie_building_population/` (`compute_building_population`) | **New**: In-depth Data ▸ Water-fee model panel; Map layers ▸ Water fees | **Water volume, extra share, unit price** (new) | Wired; data-blocked: Pegah's inputs (`BU.Building.gml`, `LU00.gpkg`, communes, population CSV, km markers) are not in `src/static/geo` here, so the run fails and the panel reports it |
| AOI selector / browser (river-km reach) | `eddie_aoi/` (WPS `/aoi/wps`, `/terria-aoi-init/…`) | Terria catalogue ("AOI selector", "AOI browser") | River, km range | Functional through Terria's own WPS form (left there: it is a full form already) |
| Base data ingest (PostGIS `base_*` tables) | `eddie_base_data/` | None (runs at worker start) | `force` | Partly data-blocked: only buildings and HQ10 / HQ100 extents are present here |
| GeoServer layer catalogue | `EDDIE/lib/eddie/src/eddie/geoserver/terria_catalogs.py`; `/terria-catalog.json` | Terria catalogue | – | Functional |
| Data layer availability | **new** `/map-layers/status.json` | Drives the In-depth / Casual notes and the Water fees toggle | – | Functional (new) |

## Backend-only settings (not in the UI)

Set in `EDDIE/docker-compose.override.yml`, applied on restart; they shape precomputed data, so they are not live map controls:
`WATER_RENDER_OFFSET`, `CHANNEL_MARGIN`, `WATER_LEVEL_STEP_CM`, `WATER_MESH_M`, `MANNING_N`, `SLOPE_SMOOTHING_M`,
`SLOPE_SHADING_START_DEG` / `_FULL_DEG` (defaults; the map's own slope settings override them per tile request),
`WATER_SURFACE_METHOD`, `SECTION_CORRIDOR_M`, `LIVE_WATER_METHOD`, `REM_MIN_RISE_M`, `BUILDING_HEIGHT_M`,
`TERRAIN_HEIGHT_OFFSET`, `COLLECT_INTERVAL_MIN`. The CZML query arguments `transition_s` and `corridor_m` are also not exposed.

## Dead or unused code

- `GET /terria-present-rainfall.json` (`EDDIE/src/eddie_antartica/blueprint.py`): nothing calls it. The live rainfall now comes
  through the `layers/rain/` init prefix. It is left in place.
- `/wps` in `EDDIE/src/eddie_antartica/blueprint.py`: registers no processes (`processes = []`).
- Antarctic leftovers: the `.sld` styles in `EDDIE/src/static/geo/` (air temperature, ice sheet, sediment, …) and
  `src/eddie_antartica/static_boundary_instructions.json` (a New Zealand dataset). The code no longer passes those instructions
  (`instruction_json_path: None`), but a database created by the old template still lists the dataset, and then the request
  (`datafinder.stats.govt.nz`, placeholder key) fails at worker start (`eddie.tasks.add_base_data_to_db`).
- `eddie_precip_interpolation/tasks_placeholder.py`, `eddie_precip_interpolation/New Text Document.txt`.
- `users/*`: personal sandboxes (Devika, Pegah, Robin, Luiz). The integrated versions live in the `eddie_*` packages; Pegah's
  four water-fee scenarios (`users/Pegah/src/simple_model_*_scenario.py`) are not integrated yet.

## Notes

- **Shared state.** Casual and In-depth act on the same state through `window.AlzetteTwin`: layers, the day replayed, the clock.
  Switching modes only shows or hides panels (and Terria's side panel), so nothing reloads.
- **Layers in init files.** Terria replaces its workbench on every init file. The rain, flood-zone and water-fee layers are therefore
  added by the backend with a `layers/<kinds>/` path prefix, like the existing `names/`, `slope/` and `rem/` prefixes. A layer whose
  GeoServer data is not published is left out (`/map-layers/status.json`), so Terria does not show an error dialog.
- **Rain needs a database seeded by this code.** The interpolation (`derive_precipitation_history`) needs the
  `aoi_alzette_35_50_300m` table, which EDDIE's static-file loader creates at worker start. On a fresh stack (`./start.sh`, new
  volumes) it does, and rain works end to end. On a database volume created by the old template, the loader first stops on the
  New Zealand dataset recorded there, so the table is never created: `./start.sh reset --volumes` fixes that, at the cost of the
  database: the gauge history is fetched again automatically, AOIs built by hand must be built again.
- **Live water on start.** The live water level appears once a mode is confirmed on the entry screen. Before that, live readings only
  update a water view already on the map (the existing behaviour).
- **Tests.** `EDDIE/terriajs/tests/mode_checks.js` runs with Node (the `terria_map` container has it); the pytest wrapper is
  `EDDIE/tests/test_twin_modes_frontend.py` and skips without Node.
