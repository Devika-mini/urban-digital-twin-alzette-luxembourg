from pathlib import Path

import yaml

# Anchor for the default source file location. Mirrors robin/src/config.py's
# REPO_ROOT pattern, but data_sources/*.yml is a separate config system (one
# file per data source, protocol+fetch schema) from robin/config.yaml (one
# flat flood-zone-pipeline config) - so this is its own loader, not a reuse.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent
DATA_SOURCES_DIR: Path = REPO_ROOT / "data_sources"


def load_source_config(path: str | Path) -> dict:
    # Plain load - "unknown"/"to confirm" string values are deliberate per
    # the file's own header comment and must round-trip untouched, not be
    # coerced or validated away here.
    with open(path) as f:
        return yaml.safe_load(f)
