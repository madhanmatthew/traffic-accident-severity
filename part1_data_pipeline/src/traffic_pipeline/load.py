"""Load layer: analytical Parquet -> PostgreSQL/PostGIS (or SQLite locally).

Analytical tables are fully refreshed on every run (drop + create + insert) so
the warehouse always equals the output of one reproducible pipeline run and is
never edited by hand. Audit tables are append-only; rows of the current run_id
are replaced so a re-run of the same run_id is idempotent.
"""
from __future__ import annotations

import shutil

import pandas as pd
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import Engine

from . import warehouse_schema as ws
from .audit import get_logger, pipeline_step
from .config import get_settings

logger = get_logger()


def get_engine() -> Engine:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        (settings.data_dir / "warehouse").mkdir(parents=True, exist_ok=True)
    return create_engine(settings.database_url, future=True)


def _insert(engine: Engine, table_name: str, df: pd.DataFrame) -> None:
    table = ws.metadata.tables[table_name]
    df = df[[c.name for c in table.columns if c.name in df.columns]]
    df = df.astype(object).where(df.notna(), None)  # pandas NA -> SQL NULL
    chunk = max(1, 30000 // max(len(df.columns), 1))
    method = "multi" if engine.dialect.name == "postgresql" else None
    df.to_sql(table_name, engine, if_exists="append", index=False, chunksize=chunk, method=method)


def _add_postgis_geometry(engine: Engine) -> None:
    """Add a PostGIS point column + spatial index to fact_accident (PostgreSQL only)."""
    statements = [
        "CREATE EXTENSION IF NOT EXISTS postgis",
        "ALTER TABLE fact_accident ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)",
        "UPDATE fact_accident SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)",
        "CREATE INDEX IF NOT EXISTS ix_fact_accident_geom ON fact_accident USING GIST (geom)",
        "ALTER TABLE mart_location_hotspots ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)",
        "UPDATE mart_location_hotspots SET geom = ST_SetSRID(ST_MakePoint(hotspot_lon, hotspot_lat), 4326)",
    ]
    try:
        with engine.begin() as conn:
            for sql in statements:
                conn.execute(text(sql))
        logger.info("PostGIS geometry columns created")
    except Exception as exc:  # PostGIS not installed -> plain PostgreSQL still works
        logger.warning("PostGIS not available, skipping geometry columns: %s", exc)


@pipeline_step("load_warehouse")
def load_warehouse(run_id: str) -> dict:
    settings = get_settings()
    src = settings.analytics_dir / run_id
    engine = get_engine()

    analytics = [ws.metadata.tables[name] for name in ws.ANALYTICS_TABLES]
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # geometry columns are not part of the metadata, so drop with CASCADE
            for table in reversed(analytics):
                conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
        else:
            ws.metadata.drop_all(conn, tables=analytics)
        ws.metadata.create_all(conn, tables=analytics)

    rows = 0
    for name in ws.ANALYTICS_TABLES:
        df = pd.read_parquet(src / f"{name}.parquet")
        _insert(engine, name, df)
        rows += len(df)
        logger.info("loaded %-24s %8d rows", name, len(df))

    if engine.dialect.name == "postgresql":
        _add_postgis_geometry(engine)

    load_audit_tables(run_id, engine)
    publish_latest(run_id)
    return {"rows_in": rows, "rows_out": rows, "message": f"{len(ws.ANALYTICS_TABLES)} tables loaded into "
                                                          f"{engine.dialect.name}"}


def load_audit_tables(run_id: str, engine: Engine | None = None) -> None:
    """Replace this run's rows in the audit tables (idempotent)."""
    settings = get_settings()
    engine = engine or get_engine()
    audit = [ws.metadata.tables[name] for name in ws.AUDIT_TABLES]
    ws.metadata.create_all(engine, tables=audit)

    sources = {
        "etl_ingestion_log": settings.logs_dir / "ingestion_log.csv",
        "etl_run_log": settings.logs_dir / "run_log.csv",
        "dq_rejected_records": settings.rejected_dir / run_id / "rejected_records.csv",
    }
    for name, path in sources.items():
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df = df[df["run_id"] == run_id].replace({"": None})
        for col in ("row_count", "bytes", "rows_in", "rows_out"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        if "duration_s" in df:
            df["duration_s"] = pd.to_numeric(df["duration_s"], errors="coerce")
        table = ws.metadata.tables[name]
        with engine.begin() as conn:
            conn.execute(delete(table).where(table.c.run_id == run_id))
        if len(df):
            _insert(engine, name, df)


def publish_latest(run_id: str) -> None:
    """Copy this run's analytical Parquet files to data/analytics/latest (input for Part 2)."""
    settings = get_settings()
    latest = settings.analytics_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for path in (settings.analytics_dir / run_id).glob("*.parquet"):
        shutil.copy2(path, latest / path.name)
    (latest / "RUN_ID").write_text(run_id, encoding="utf-8")


@pipeline_step("verify_load")
def verify_load(run_id: str) -> dict:
    """Reconcile row counts between the Parquet layer and the database."""
    settings = get_settings()
    engine = get_engine()
    mismatches = []
    with engine.connect() as conn:
        for name in ws.ANALYTICS_TABLES:
            expected = len(pd.read_parquet(settings.analytics_dir / run_id / f"{name}.parquet"))
            actual = conn.execute(select(func.count()).select_from(ws.metadata.tables[name])).scalar_one()
            if expected != actual:
                mismatches.append(f"{name}: parquet={expected} db={actual}")
        orphans = conn.execute(text(
            "SELECT COUNT(*) FROM fact_accident f LEFT JOIN dim_date d ON f.date_key = d.date_key "
            "WHERE d.date_key IS NULL")).scalar_one()
    if orphans:
        mismatches.append(f"fact_accident rows without dim_date: {orphans}")
    if mismatches:
        raise AssertionError("Load verification failed: " + "; ".join(mismatches))
    return {"rows_out": len(ws.ANALYTICS_TABLES), "message": "row counts and referential integrity verified"}
