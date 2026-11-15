#!/usr/bin/env bash
#
# One command from a fresh clone (plus the data folder and .env) to the running Alzette digital twin.
#
#   ./start.sh                 check, generate what is missing or outdated, build, start, wait until healthy
#   ./start.sh --force         regenerate everything derived from the data folder, then start
#   ./start.sh --no-generate   skip the generation, start straight away
#   ./start.sh stop            stop the twin (docker compose down; the database is kept)
#   ./start.sh logs [service]  follow the logs (all services, or one: backend, celery_worker, ...)
#   ./start.sh status          list the services and their health
#   ./start.sh reset [--volumes] [--yes]
#                              delete the generated files (terrain, REM, staged model inputs) so the next
#                              start rebuilds them; --volumes also deletes the Docker volumes (database,
#                              GeoServer). Never touches data/ or .env.
#   ./start.sh help
#
# Needs only Docker (with Compose v2.24 or newer) and bash; every generation step runs in a container.
# On Windows run it from Git Bash, or use start.ps1 from PowerShell.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EDDIE_DIR="$ROOT_DIR/EDDIE/eddie_antarctica"
ENV_FILE="$ROOT_DIR/.env"
DATA_DIR="$ROOT_DIR/data"
RAW_DIR="$DATA_DIR/raw"

# Generated outputs (git-ignored, apart from the raw data).
TERRAIN_DIR="$EDDIE_DIR/data/terrain"
MASTER_DEM="$TERRAIN_DIR/dem_merged.tif"
LIDAR_DIR="$TERRAIN_DIR/lidar_egm2008"
REM_DIR="$EDDIE_DIR/data/rem"
STATIC_GEO="$EDDIE_DIR/src/static/geo"
STAGED_LIST="$STATIC_GEO/.staged-by-start"
FLOOD_COSTS_DIR="$DATA_DIR/flood_costs"

RAW_DEM="$RAW_DIR/filled_dem.tif"
RIVER_KM="$RAW_DIR/River_kilometers/kilometrage-des-cours-deau.gpkg"
STATIC_INPUTS="$RAW_DIR/static_geo"

# .env keys that must be set and non-empty.
REQUIRED_KEYS=(POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD POSTGRES_PORT
  GEOSERVER_HOST GEOSERVER_PORT GEOSERVER_ADMIN_NAME GEOSERVER_ADMIN_PASSWORD
  BACKEND_HOST BACKEND_PORT WWW_PORT STATSNZ_API_KEY LINZ_API_KEY MFE_API_KEY)

# Files the data folder must contain (relative to data/raw).
REQUIRED_DATA=(
  "filled_dem.tif"
  "River_kilometers/kilometrage-des-cours-deau.gpkg"
  "Buildings/ACT2023v2_Buildings3d_Footprints.gpkg"
  "Buildings/luxembourg.gpkg"
  "Flood_hazard/HWGK2021_HQ10/HWGK2021_HQ10.shp"
  "Flood_hazard/HWGK2021_HQ10/HWGK2021_HQ10.shx"
  "Flood_hazard/HWGK2021_HQ10/HWGK2021_HQ10.dbf"
  "Flood_hazard/HWGK2021_HQ100/HWGK2021_HQ100.shp"
  "Flood_hazard/HWGK2021_HQ100/HWGK2021_HQ100.shx"
  "Flood_hazard/HWGK2021_HQ100/HWGK2021_HQ100.dbf"
  "Flood_hazard/HWGK2021_HQext/HWGK2021_HQext.shp"
  "Flood_hazard/HWGK2021_HQext/HWGK2021_HQext.shx"
  "Flood_hazard/HWGK2021_HQext/HWGK2021_HQext.dbf"
)

# Services with a health check, waited for after the start.
HEALTHY_SERVICES=(db_postgres message_broker geoserver backend celery_worker terria_map)

# Docker Desktop on Windows needs C:/... host paths; Git Bash must not rewrite container paths.
export MSYS_NO_PATHCONV=1

# ---------------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------------

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
  BOLD=""; RED=""; GREEN=""; YELLOW=""; RESET=""
fi

step() { echo "${BOLD}==> $*${RESET}"; }
info() { echo "    $*"; }
warn() { echo "${YELLOW}    Warning: $*${RESET}" >&2; }
fail() {
  echo "${RED}${BOLD}Error:${RESET}${RED} $1${RESET}" >&2
  shift
  local line
  for line in "$@"; do echo "  $line" >&2; done
  exit 1
}

host_path() {
  # A path as Docker on this host wants it.
  if command -v cygpath > /dev/null; then cygpath -m "$1"; else echo "$1"; fi
}

usage() { sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; }

# ---------------------------------------------------------------------------------------------------
# .env: read without sourcing it and without ever printing a value
# ---------------------------------------------------------------------------------------------------

env_value() {
  # The value of a key in .env (last occurrence), without surrounding quotes or a trailing CR.
  local key=$1 line value=""
  [[ -f "$ENV_FILE" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%$'\r'}
    [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=(.*)$ ]] || continue
    value=${BASH_REMATCH[2]}
    value=${value#"${value%%[![:space:]]*}"}
    value=${value%"${value##*[![:space:]]}"}
    if [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]]; then
      value=${BASH_REMATCH[1]}
    fi
  done < "$ENV_FILE"
  printf '%s' "$value"
}

# ---------------------------------------------------------------------------------------------------
# Docker Compose
# ---------------------------------------------------------------------------------------------------

PROJECT=${COMPOSE_PROJECT_NAME:-}
COMPOSE=()

setup_compose() {
  if [[ -z "$PROJECT" ]]; then
    PROJECT=$(env_value COMPOSE_PROJECT_NAME)
    PROJECT=${PROJECT:-eddie_antarctica}
  fi
  BACKEND_IMAGE="${PROJECT}-backend"
  # docker-compose.override.yml holds the plugin mounts: with -f it must be listed explicitly.
  local files=(-f docker-compose.yml -f docker-compose.override.yml)
  # The worker reserves an NVIDIA GPU; drop the reservation on hosts without one (as up.sh does).
  if ! { docker info --format '{{json .Runtimes}}' 2> /dev/null | grep -q '"nvidia"' &&
         command -v nvidia-smi > /dev/null && nvidia-smi -L > /dev/null 2>&1; }; then
    files+=(-f docker-compose.cpu.yml)
  fi
  COMPOSE=(docker compose -p "$PROJECT" "${files[@]}")
  if [[ -f "$ENV_FILE" ]]; then
    COMPOSE+=(--env-file ../../.env)
  fi
}

compose() { (cd "$EDDIE_DIR" && "${COMPOSE[@]}" "$@"); }

# ---------------------------------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------------------------------

check_docker() {
  step "Checking Docker"
  command -v docker > /dev/null ||
    fail "Docker is not installed." "Install Docker Desktop (Windows, macOS) or Docker Engine (Linux): https://docs.docker.com/get-docker/"
  local version
  version=$(docker compose version --short 2> /dev/null) ||
    fail "Docker Compose v2 ('docker compose') is not available." "It comes with Docker Desktop; on Linux install the docker-compose-plugin package."
  version=${version#v}
  local major=${version%%.*} rest=${version#*.}
  local minor=${rest%%.*}
  if [[ "$major" -lt 2 ]] || { [[ "$major" -eq 2 ]] && [[ "$minor" -lt 24 ]]; }; then
    fail "Docker Compose $version is too old: 2.24 or newer is needed." "Update Docker Desktop, or the docker-compose-plugin package on Linux."
  fi
  docker info > /dev/null 2>&1 ||
    fail "The Docker daemon is not running." "Start Docker Desktop (or 'sudo systemctl start docker' on Linux), wait until it is ready, and run this again."
  info "Docker Compose $version, daemon running"
}

check_env() {
  step "Checking .env"
  [[ -f "$ENV_FILE" ]] || fail ".env not found at $ENV_FILE." \
    "Create it from the template and fill in the empty values:" \
    "    cp .env.example .env" \
    "(An older setup's EDDIE/eddie_antarctica/.env and api_keys.env can be merged into it:" \
    "    cat EDDIE/eddie_antarctica/.env EDDIE/eddie_antarctica/api_keys.env > .env )"
  local missing=() key
  for key in "${REQUIRED_KEYS[@]}"; do
    [[ -n "$(env_value "$key")" ]] || missing+=("$key")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "These required keys are missing or empty in .env: ${missing[*]}" \
      "Set them in $ENV_FILE (see .env.example for what each one is)."
  fi
  for key in POSTGRES_PORT GEOSERVER_PORT BACKEND_PORT WWW_PORT; do
    [[ "$(env_value "$key")" =~ ^[0-9]+$ ]] || fail "$key in .env must be a port number."
  done
  [[ "$(env_value BACKEND_PORT)" == "5000" ]] ||
    warn "BACKEND_PORT is not 5000, but docker-compose.yml publishes the backend on port 5000."
  [[ -n "$(env_value CESIUM_ACCESS_TOKEN)" ]] ||
    warn "CESIUM_ACCESS_TOKEN is empty: the map works, but without Cesium ion services."
  info "All ${#REQUIRED_KEYS[@]} required keys are set"
}

check_data() {
  step "Checking the data folder ($DATA_DIR)"
  [[ -d "$RAW_DIR" ]] || fail "The data folder is missing: $RAW_DIR does not exist." \
    "Copy the data folder into the repository root so that data/raw/ exists; see data/README.md for its layout."
  local missing=() file
  for file in "${REQUIRED_DATA[@]}"; do
    [[ -s "$RAW_DIR/$file" ]] || missing+=("data/raw/$file")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "The data folder lacks ${#missing[@]} required file(s):" "${missing[@]}" "" "See data/README.md for where each one comes from."
  fi
  [[ -d "$RAW_DIR/Buildings/inspire_building3d" ]] ||
    warn "data/raw/Buildings/inspire_building3d/ is missing: buildings get heights only from their footprints."
  [[ -f "$RAW_DIR/Communes/communes4326.geojson" ]] ||
    warn "data/raw/Communes/communes4326.geojson is missing: flood reports are not split by commune."
  # Shapefiles in the repository are stored with Git LFS: without git-lfs a clone has pointer files.
  local pointer
  pointer=$(grep -l "^version https://git-lfs" "$STATIC_GEO"/*.shp "$STATIC_GEO"/*.dbf 2> /dev/null | head -1 || true)
  [[ -z "$pointer" ]] || fail "Git LFS files were not downloaded (e.g. ${pointer#"$ROOT_DIR"/})." \
    "Install Git LFS (https://git-lfs.com), then run in the repository:" "    git lfs install && git lfs pull"
  info "All ${#REQUIRED_DATA[@]} required files present"
}

# ---------------------------------------------------------------------------------------------------
# Generation: everything derived from data/raw, each step skipped while its output is up to date
# ---------------------------------------------------------------------------------------------------

FORCE=0

newer() { [[ -e "$1" && ( ! -e "$2" || "$1" -nt "$2" ) ]]; }

stage_model_inputs() {
  # The models' inputs read from src/static/geo (eddie_base_data, eddie_flood_costs): the river
  # kilometre markers and anything in data/raw/static_geo/, copied when missing or newer.
  local sources=("$RIVER_KM") source name copied=0
  if [[ -d "$STATIC_INPUTS" ]]; then
    for source in "$STATIC_INPUTS"/*; do [[ -f "$source" ]] && sources+=("$source"); done
  fi
  touch "$STAGED_LIST"
  for source in "${sources[@]}"; do
    name=$(basename "$source")
    if (cd "$ROOT_DIR" && git ls-files --error-unmatch "EDDIE/eddie_antarctica/src/static/geo/$name" > /dev/null 2>&1); then
      warn "Not staging $name: a file of that name is part of the repository."
      continue
    fi
    if [[ $FORCE == 1 ]] || newer "$source" "$STATIC_GEO/$name"; then
      cp -p "$source" "$STATIC_GEO/$name"
      copied=$((copied + 1))
    fi
    grep -qxF "$name" "$STAGED_LIST" || echo "$name" >> "$STAGED_LIST"
  done
  if [[ $copied -gt 0 ]]; then
    info "Staged $copied model input file(s) into EDDIE/eddie_antarctica/src/static/geo/"
  else
    info "Model inputs up to date (${#sources[@]} file(s))"
  fi
}

build_master_dem() {
  # data/raw/filled_dem.tif -> data/terrain/dem_merged.tif (the DEM the backend reads) and the map's home camera.
  local user_args=()
  command -v cygpath > /dev/null || user_args=(--user "$(id -u):$(id -g)")
  mkdir -p "$TERRAIN_DIR"
  docker run --rm "${user_args[@]}" --entrypoint /venv/bin/python \
    -v "$(host_path "$EDDIE_DIR"):/project" -v "$(host_path "$RAW_DIR"):/input:ro" "$BACKEND_IMAGE" \
    /project/scripts/prepare_dem.py /input/filled_dem.tif --new --no-tiles --record-as data/raw/filled_dem.tif
}

build_rem() {
  # data/terrain/dem_merged.tif + the river channel -> data/rem/ (Relative Elevation Model and its overlays).
  mkdir -p "$REM_DIR"
  local force_arg=False
  [[ $FORCE == 1 ]] && force_arg=True
  compose run --rm --no-deps --entrypoint /venv/bin/python backend \
    -c "from eddie_water_level import rem; print('    REM:', rem.build(force=$force_arg))" 2>&1 | grep -v " INFO " || true
  [[ -f "$REM_DIR/rem.json" ]] || fail "The Relative Elevation Model was not built (see the output above)."
}

generate() {
  step "Generating data derived from data/raw$([[ $FORCE == 1 ]] && echo " (forced)")"
  local started=$SECONDS need_dem=0 need_tiles=0 need_rem=0
  mkdir -p "$FLOOD_COSTS_DIR"
  stage_model_inputs

  { [[ $FORCE == 1 ]] || newer "$RAW_DEM" "$MASTER_DEM"; } && need_dem=1
  { [[ $need_dem == 1 || ! -f "$LIDAR_DIR/terrain/layer.json" || ! -f "$LIDAR_DIR/build.stamp" ]] ||
    newer "$MASTER_DEM" "$LIDAR_DIR/build.stamp"; } && need_tiles=1
  { [[ $FORCE == 1 || $need_dem == 1 ]] || newer "$MASTER_DEM" "$REM_DIR/rem.json"; } && need_rem=1

  if [[ $need_dem == 0 && $need_tiles == 0 && $need_rem == 0 ]]; then
    info "Master DEM, 3D terrain tiles and REM are up to date"
    return
  fi
  info "Building the backend image the generation runs in (long the first time, cached afterwards)"
  compose build backend || fail "The backend image could not be built (output above)."

  if [[ $need_dem == 1 ]]; then
    info "Master DEM: data/raw/filled_dem.tif -> EDDIE/eddie_antarctica/data/terrain/dem_merged.tif"
    build_master_dem
  else
    info "Master DEM up to date"
  fi
  if [[ $need_tiles == 1 ]]; then
    info "3D terrain tiles: dem_merged.tif -> data/terrain/lidar_egm2008/ (several minutes the first time)"
    BACKEND_IMAGE="$BACKEND_IMAGE" bash "$EDDIE_DIR/scripts/build_lidar_terrain.sh" --force
  else
    info "3D terrain tiles up to date"
  fi
  if [[ $need_rem == 1 ]]; then
    info "Relative Elevation Model: dem_merged.tif -> data/rem/"
    build_rem
  else
    info "REM up to date"
  fi
  info "Generation done in $((SECONDS - started)) s"
}

# ---------------------------------------------------------------------------------------------------
# Start and health
# ---------------------------------------------------------------------------------------------------

print_logs_of() {
  local service
  for service in "$@"; do
    echo "${BOLD}---- last log lines of $service ----${RESET}" >&2
    compose logs --no-color --tail 60 "$service" >&2 || true
  done
}

wait_healthy() {
  local timeout=${TWIN_HEALTH_TIMEOUT:-$(env_value TWIN_HEALTH_TIMEOUT)}
  timeout=${timeout:-900}
  step "Waiting for the services to become healthy (up to $timeout s)"
  local started=$SECONDS line service state health pending failed
  while true; do
    pending=(); failed=()
    local status
    status=$(compose ps -a --format '{{.Service}}|{{.State}}|{{.Health}}' 2> /dev/null || true)
    for service in "${HEALTHY_SERVICES[@]}"; do
      line=$(echo "$status" | grep "^$service|" | head -1 || true)
      state=$(echo "$line" | cut -d'|' -f2)
      health=$(echo "$line" | cut -d'|' -f3)
      if [[ -z "$line" || "$state" == "exited" || "$state" == "dead" || "$health" == "unhealthy" ]]; then
        failed+=("$service")
      elif [[ "$health" != "healthy" ]]; then
        pending+=("$service")
      fi
    done
    if [[ ${#failed[@]} -gt 0 ]]; then
      print_logs_of "${failed[@]}"
      fail "Service(s) failed to start: ${failed[*]} (logs above)." "Fix the cause, then run ./start.sh again; './start.sh logs <service>' follows a service's log."
    fi
    if [[ ${#pending[@]} -eq 0 ]]; then
      info "All services healthy after $((SECONDS - started)) s"
      return
    fi
    if (( SECONDS - started > timeout )); then
      print_logs_of "${pending[@]}"
      fail "Timed out after $timeout s waiting for: ${pending[*]} (logs above)." \
        "A first start can take long (GeoServer, database setup); raise TWIN_HEALTH_TIMEOUT in .env if needed."
    fi
    sleep 5
  done
}

check_http() {
  # From this computer, as the browser will reach them.
  # A service can report healthy a moment before its published port answers: retry for a minute.
  command -v curl > /dev/null || return 0
  local name url tries
  for name in "map|$1" "backend|$2/health-check"; do
    url=${name#*|}
    tries=0
    # Output to the shell's /dev/null: with MSYS_NO_PATHCONV a Windows curl cannot open "-o /dev/null".
    until curl -fs -m 10 "$url" > /dev/null; do
      tries=$((tries + 1))
      [[ $tries -lt 12 ]] ||
        fail "The ${name%%|*} is running but does not answer at $url." "Is the port free on this computer? './start.sh logs' shows the services' logs."
      sleep 5
    done
  done
}

start() {
  local total=$SECONDS generate_step=1
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force|--rebuild) FORCE=1 ;;
      --no-generate) generate_step=0 ;;
      -h|--help) usage; exit 0 ;;
      *) fail "Unknown option: $1" "Run ./start.sh help for the options." ;;
    esac
    shift
  done
  [[ $FORCE == 1 && $generate_step == 0 ]] && fail "--force and --no-generate cannot be combined."

  check_docker
  check_env
  check_data
  setup_compose
  if [[ $generate_step == 1 ]]; then
    generate
  else
    step "Skipping the generation (--no-generate)"
  fi

  step "Building and starting the services (docker compose up -d --build)"
  compose up -d --build --remove-orphans || fail "docker compose up failed (output above)."
  wait_healthy

  local www backend geoserver
  www="http://localhost:$(env_value WWW_PORT)"
  backend="$(env_value BACKEND_HOST):$(env_value BACKEND_PORT)"
  geoserver="$(env_value GEOSERVER_HOST):$(env_value GEOSERVER_PORT)/geoserver"
  check_http "$www" "$backend"

  echo
  echo "${GREEN}${BOLD}The Alzette digital twin is running${RESET} (ready in $((SECONDS - total)) s)"
  echo
  echo "  Map (Casual / In-depth)  $www"
  echo "  Backend API              $backend   (API docs: $backend/swagger)"
  echo "  GeoServer                $geoserver"
  echo "  Gauge collector          http://localhost:5002/status"
  echo
  echo "  ./start.sh logs [service]   follow the logs      ./start.sh status   service health"
  echo "  ./start.sh stop             stop the twin        ./start.sh reset    delete generated files"
  echo
  echo "  On the first start the worker loads the base data and the gauge collector fetches the"
  echo "  water-level history in the background: give them a few minutes."
}

# ---------------------------------------------------------------------------------------------------
# Companion commands
# ---------------------------------------------------------------------------------------------------

reset() {
  local volumes=0 yes=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --volumes) volumes=1 ;;
      --yes|-y) yes=1 ;;
      *) fail "Unknown option for reset: $1" ;;
    esac
    shift
  done
  local targets=("EDDIE/eddie_antarctica/data/terrain/  (master DEM, 3D terrain tiles)"
                 "EDDIE/eddie_antarctica/data/rem/      (Relative Elevation Model)"
                 "model inputs staged into EDDIE/eddie_antarctica/src/static/geo/ (listed in .staged-by-start)")
  [[ $volumes == 1 ]] && targets+=("the Docker volumes of project '$PROJECT' (database, GeoServer, stored data)")
  step "Reset: deleting generated outputs"
  local target
  for target in "${targets[@]}"; do info "- $target"; done
  info "data/ and .env are not touched."
  if [[ $yes == 0 ]]; then
    [[ -t 0 ]] || fail "Not a terminal: add --yes to confirm the reset."
    read -r -p "    Delete these? [y/N] " answer
    [[ "$answer" == [yY] || "$answer" == [yY][eE][sS] ]] || { info "Nothing deleted."; exit 0; }
  fi
  if [[ $volumes == 1 ]]; then
    compose down -v --remove-orphans
  else
    compose down --remove-orphans
  fi
  rm -rf "$TERRAIN_DIR" "$REM_DIR"
  if [[ -f "$STAGED_LIST" ]]; then
    local name
    while IFS= read -r name; do
      [[ -n "$name" && "$name" != */* ]] && rm -f "$STATIC_GEO/$name"
    done < "$STAGED_LIST"
    rm -f "$STAGED_LIST"
  fi
  info "Done. ./start.sh regenerates everything."
}

main() {
  local command=${1:-start}
  case "$command" in
    help|-h|--help) usage ;;
    stop)
      setup_compose
      step "Stopping the twin"
      compose down --remove-orphans
      ;;
    logs)
      shift
      setup_compose
      compose logs -f --tail 100 "$@"
      ;;
    status|ps)
      setup_compose
      compose ps -a
      ;;
    reset)
      shift
      command -v docker > /dev/null || fail "Docker is not installed."
      setup_compose
      reset "$@"
      ;;
    start) shift || true; start "$@" ;;
    -*) start "$@" ;;
    *) fail "Unknown command: $command" "Run ./start.sh help for the commands." ;;
  esac
}

main "$@"
