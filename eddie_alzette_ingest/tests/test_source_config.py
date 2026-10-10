from eddie_alzette_ingest.source_config import DATA_SOURCES_DIR, load_source_config


def test_loads_asta_precipitation_yml():
    cfg = load_source_config(DATA_SOURCES_DIR / "asta_precipitation.yml")
    assert cfg["id"] == "asta_precipitation"
    assert cfg["fetch"]["kind"] == "wfs_point_timeseries"
    assert "Roeser" in cfg["fetch"]["stations"]


def test_loads_template_yml_without_raising():
    cfg = load_source_config(DATA_SOURCES_DIR / "_template.yml")
    # Deliberately blank, not omitted - the template exists to show which
    # keys a new source file must fill in.
    assert set(cfg["fetch"].keys()) == set(load_source_config(DATA_SOURCES_DIR / "asta_precipitation.yml")["fetch"].keys())
