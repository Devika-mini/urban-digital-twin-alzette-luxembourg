from datetime import datetime

import geopandas as gpd
import pandas as pd
import sqlalchemy as sa
from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape
from sqlalchemy.engine import Connection


def _dialect_insert(conn: Connection):
    # The observations/no-geometry path is also exercised against SQLite in
    # tests (PostGIS geometry isn't testable there) - both dialects' insert()
    # support on_conflict_do_nothing/do_update with the same call shape.
    if conn.engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    return dialect_insert


def _stations_table(table_name: str) -> sa.Table:
    return sa.Table(
        table_name,
        sa.MetaData(),
        sa.Column("station_id", sa.Text, primary_key=True),
        sa.Column("station_name", sa.Text),
        sa.Column("geometry", Geometry("POINT", srid=4326)),
    )


def _observations_table(table_name: str, keep_raw_fields: list[str], unique_key: list[str]) -> sa.Table:
    # keep_raw_fields (e.g. datetime/time/day/gml_identifier) become plain
    # TEXT columns, stored exactly as received - the source's time zone is
    # unresolved, so nothing here parses or converts them.
    columns = [sa.Column("station_id", sa.Text, nullable=False)]
    columns += [sa.Column(field, sa.Text) for field in keep_raw_fields]
    columns += [
        sa.Column("variable", sa.Text, nullable=False),
        sa.Column("value", sa.Float),  # null stays SQL NULL, never substituted with 0
        sa.UniqueConstraint(*unique_key, name=f"{table_name}_unique_key"),
    ]
    return sa.Table(table_name, sa.MetaData(), *columns)


def ensure_stations_table(conn: Connection, table_name: str) -> None:
    _stations_table(table_name).create(conn, checkfirst=True)


def ensure_observations_table(conn: Connection, table_name: str, keep_raw_fields: list[str], unique_key: list[str]) -> None:
    _observations_table(table_name, keep_raw_fields, unique_key).create(conn, checkfirst=True)


def ensure_tables(conn: Connection, fetch_cfg: dict) -> None:
    ensure_stations_table(conn, fetch_cfg["tables"]["stations"])
    ensure_observations_table(conn, fetch_cfg["tables"]["observations"], fetch_cfg["keep_raw_fields"], fetch_cfg["unique_key"])


def upsert_stations(conn: Connection, stations_gdf: gpd.GeoDataFrame, table_name: str) -> int:
    # Stations are a current-state dimension keyed only by station_id (no
    # time component) - a later fetch should overwrite stale name/geometry,
    # unlike observations below.
    if stations_gdf.empty:
        return 0
    table = _stations_table(table_name)
    rows = [
        {
            "station_id": row.station_id,
            "station_name": row.station_name,
            "geometry": from_shape(row.geometry, srid=4326),
        }
        for row in stations_gdf.itertuples()
    ]
    insert = _dialect_insert(conn)
    stmt = insert(table).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["station_id"],
        set_={"station_name": stmt.excluded.station_name, "geometry": stmt.excluded.geometry},
    )
    result = conn.execute(stmt)
    conn.commit()
    return result.rowcount


def upsert_observations(conn: Connection, observations_df: pd.DataFrame, table_name: str, keep_raw_fields: list[str], unique_key: list[str]) -> int:
    # Observations are an append-only fact log keyed by
    # (station_id, datetime, variable): overlap_hours means the same hour is
    # routinely re-requested, so a duplicate must be a no-op (0 rows
    # inserted), not an overwrite - that is what "running the fetch twice
    # adds zero rows" means in the acceptance check.
    if observations_df.empty:
        return 0
    table = _observations_table(table_name, keep_raw_fields, unique_key)
    # NaN (from pandas, where a missing value became float('nan') rather than
    # None) must become SQL NULL on insert, not the literal float NaN.
    clean_df = observations_df.astype(object).where(pd.notnull(observations_df), None)
    rows = clean_df.to_dict("records")
    insert = _dialect_insert(conn)
    stmt = insert(table).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=unique_key)
    result = conn.execute(stmt)
    conn.commit()
    return result.rowcount


def get_last_stored_datetime_per_station(
    conn: Connection,
    observations_table: str,
    station_ids: list[str],
    time_field: str,
) -> dict[str, datetime | None]:
    if not sa.inspect(conn).has_table(observations_table):
        return dict.fromkeys(station_ids)

    table = sa.Table(observations_table, sa.MetaData(), autoload_with=conn)
    time_column = table.c[time_field]
    result: dict[str, datetime | None] = {}
    for station_id in station_ids:
        stmt = (
            sa.select(time_column)
            .where(table.c.station_id == station_id)
            .order_by(time_column.desc())
            .limit(1)
        )
        row = conn.execute(stmt).first()
        # Stored as raw text (e.g. "2026-10-09T03:00:00Z"); parsed back to a
        # datetime only here, in memory, never written back to the table.
        result[station_id] = datetime.fromisoformat(row[0].replace("Z", "+00:00")) if row else None
    return result


def get_global_last_stored(conn: Connection, observations_table: str, time_field: str) -> datetime | None:
    # The incremental window needs a single start point, but which station
    # ids exist isn't known ahead of a fetch (fetch.stations lists names, not
    # ids) - so this looks at whatever station_ids are already in the table
    # and takes the minimum of their latest timestamps, so a lagging station
    # still gets covered. None (bootstrap) only when no station has any rows.
    if not sa.inspect(conn).has_table(observations_table):
        return None
    table = sa.Table(observations_table, sa.MetaData(), autoload_with=conn)
    station_ids = [row[0] for row in conn.execute(sa.select(table.c.station_id).distinct())]
    if not station_ids:
        return None
    per_station = get_last_stored_datetime_per_station(conn, observations_table, station_ids, time_field)
    known = [v for v in per_station.values() if v is not None]
    return min(known) if known else None


def get_station_ids_by_name(conn: Connection, stations_table: str) -> dict[str, str]:
    if not sa.inspect(conn).has_table(stations_table):
        return {}
    table = sa.Table(stations_table, sa.MetaData(), autoload_with=conn)
    rows = conn.execute(sa.select(table.c.station_id, table.c.station_name))
    return {station_name: station_id for station_id, station_name in rows}


def get_observation_datetimes(conn: Connection, observations_table: str, station_id: str, time_field: str) -> list[str]:
    if not sa.inspect(conn).has_table(observations_table):
        return []
    table = sa.Table(observations_table, sa.MetaData(), autoload_with=conn)
    stmt = sa.select(table.c[time_field]).where(table.c.station_id == station_id)
    return [row[0] for row in conn.execute(stmt)]
