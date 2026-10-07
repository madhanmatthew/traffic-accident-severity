"""Staging layer: raw files -> typed, consistently named Parquet tables.

Staging does *not* drop anything. It only
  * harmonises column names across STATS19 releases (accident_* -> collision_*),
  * selects the columns the warehouse needs,
  * casts codes to integers, dates/times to proper types (bad values -> null),
  * adds lineage columns (`_source_file`).
Invalid rows are removed later by the data-quality step so that every
rejection is logged with a reason.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .audit import get_logger, pipeline_step
from .config import WEATHER_VARIABLES, get_settings
from .extract import STATS19_DATASETS, stats19_filename

logger = get_logger()

# Older STATS19 releases used "accident_*" names.
COLUMN_ALIASES = {
    "accident_index": "collision_index",
    "accident_year": "collision_year",
    "accident_reference": "collision_ref_no",
    "accident_severity": "collision_severity",
}

COLLISION_COLUMNS = {
    "collision_index": "str", "collision_year": "int", "latitude": "float", "longitude": "float",
    "location_easting_osgr": "float", "location_northing_osgr": "float", "police_force": "int",
    "collision_severity": "int", "number_of_vehicles": "int", "number_of_casualties": "int",
    "date": "str", "day_of_week": "int", "time": "str", "local_authority_ons_district": "str",
    "local_authority_highway": "str", "first_road_class": "int", "first_road_number": "int",
    "road_type": "int", "speed_limit": "int", "junction_detail": "int", "junction_control": "int",
    "second_road_class": "int", "light_conditions": "int", "weather_conditions": "int",
    "road_surface_conditions": "int", "special_conditions_at_site": "int", "carriageway_hazards": "int",
    "urban_or_rural_area": "int", "did_police_officer_attend_scene_of_accident": "int",
    "trunk_road_flag": "int", "lsoa_of_accident_location": "str",
}

VEHICLE_COLUMNS = {
    "collision_index": "str", "vehicle_reference": "int", "vehicle_type": "int",
    "vehicle_manoeuvre": "int", "skidding_and_overturning": "int", "first_point_of_impact": "int",
    "sex_of_driver": "int", "age_of_driver": "int", "age_band_of_driver": "int",
    "engine_capacity_cc": "int", "propulsion_code": "int", "age_of_vehicle": "int",
}

CASUALTY_COLUMNS = {
    "collision_index": "str", "vehicle_reference": "int", "casualty_reference": "int",
    "casualty_class": "int", "sex_of_casualty": "int", "age_of_casualty": "int",
    "age_band_of_casualty": "int", "casualty_severity": "int", "casualty_type": "int",
}

SCHEMAS = {"collision": COLLISION_COLUMNS, "vehicle": VEHICLE_COLUMNS, "casualty": CASUALTY_COLUMNS}


def _standardise(df: pd.DataFrame, schema: dict[str, str], source_file: str) -> pd.DataFrame:
    df = df.rename(columns=lambda c: COLUMN_ALIASES.get(c.strip().lower(), c.strip().lower()))
    missing = [c for c in schema if c not in df.columns]
    if missing:
        logger.warning("%s is missing columns %s - filled with nulls", source_file, missing)
    out = pd.DataFrame(index=df.index)
    for column, kind in schema.items():
        values = df[column] if column in df.columns else pd.Series(np.nan, index=df.index)
        if kind == "int":
            out[column] = pd.to_numeric(values, errors="coerce").astype("Int64")
        elif kind == "float":
            out[column] = pd.to_numeric(values, errors="coerce").astype("float64")
        else:
            out[column] = values.astype("string").str.strip().replace({"": pd.NA, "NULL": pd.NA, "-1": pd.NA})
    out["_source_file"] = source_file
    return out


def _read_dataset(run_id: str, dataset: str) -> pd.DataFrame:
    settings = get_settings()
    frames = []
    for year in settings.stats19_years:
        filename = stats19_filename(dataset, year)
        raw = pd.read_csv(settings.raw_dir / "stats19" / run_id / filename, dtype=str, low_memory=False)
        frames.append(_standardise(raw, SCHEMAS[dataset], filename))
    return pd.concat(frames, ignore_index=True)


@pipeline_step("stage_stats19")
def stage_stats19(run_id: str) -> dict:
    settings = get_settings()
    out_dir = settings.run_dir("staging", run_id)
    data = {dataset: _read_dataset(run_id, dataset) for dataset in STATS19_DATASETS}
    rows_in = sum(len(df) for df in data.values())

    collisions = data["collision"]
    collisions["collision_date"] = pd.to_datetime(collisions["date"], format="%d/%m/%Y", errors="coerce")
    parsed_time = pd.to_datetime(collisions["time"], format="%H:%M", errors="coerce")
    collisions["collision_hour"] = parsed_time.dt.hour.astype("Int64")
    collisions["collision_minute"] = parsed_time.dt.minute.astype("Int64")

    if settings.max_collisions and len(collisions) > settings.max_collisions:
        keep = collisions["collision_index"].dropna().drop_duplicates().sample(
            n=settings.max_collisions, random_state=42)
        collisions = collisions[collisions["collision_index"].isin(keep)]
        for dataset in ("vehicle", "casualty"):
            data[dataset] = data[dataset][data[dataset]["collision_index"].isin(keep)]
        logger.info("MAX_COLLISIONS=%d - working on a reproducible sample", settings.max_collisions)
    data["collision"] = collisions

    names = {"collision": "collisions", "vehicle": "vehicles", "casualty": "casualties"}
    for dataset, df in data.items():
        df.reset_index(drop=True).to_parquet(out_dir / f"{names[dataset]}.parquet", index=False)
    rows_out = sum(len(df) for df in data.values())
    return {"rows_in": rows_in, "rows_out": rows_out,
            "message": ", ".join(f"{names[k]}={len(v)}" for k, v in data.items())}


@pipeline_step("stage_weather")
def stage_weather(run_id: str) -> dict:
    settings = get_settings()
    out_dir = settings.run_dir("staging", run_id)
    files = sorted((settings.raw_dir / "weather" / run_id).glob("cell_*.json"))
    frames = []
    for path in files:
        body = json.loads(path.read_text(encoding="utf-8"))
        hourly = body.get("hourly") or {}
        if not hourly.get("time"):
            logger.warning("%s has no hourly data", path.name)
            continue
        frame = pd.DataFrame({var: hourly.get(var) for var in ["time", *WEATHER_VARIABLES]})
        frame["weather_cell_id"] = body["requested_cell_id"]
        frames.append(frame)

    columns = ["weather_cell_id", "weather_time", *WEATHER_VARIABLES]
    if frames:
        weather = pd.concat(frames, ignore_index=True)
        weather["weather_time"] = pd.to_datetime(weather.pop("time"), errors="coerce")
        for var in WEATHER_VARIABLES:
            weather[var] = pd.to_numeric(weather[var], errors="coerce")
        # Autumn clock change repeats one local hour; keep the first reading.
        weather = weather.drop_duplicates(["weather_cell_id", "weather_time"])[columns]
    else:
        weather = pd.DataFrame(columns=columns)
    weather.to_parquet(out_dir / "weather_hourly.parquet", index=False)
    return {"rows_in": len(files), "rows_out": len(weather), "message": f"{len(files)} weather files staged"}
