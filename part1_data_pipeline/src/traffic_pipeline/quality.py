"""Data-quality layer: staging -> cleaned (+ rejected-record log).

Each rule has an id, a target table and an action:
  REJECT   - the row is removed from the cleaned layer and written to the
             rejected-record log with the offending field/value.
  NULLIFY  - the row is kept but the implausible value is set to null and the
             change is logged.
The full rule catalogue is documented in docs/validation_rules.md.
A quality gate fails the run when the collision reject rate exceeds
MAX_REJECT_RATE (default 5 %), so a broken source file never reaches the
warehouse silently.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import pandas as pd

from .audit import get_logger, pipeline_step
from .config import get_settings

logger = get_logger()

VALID_SPEED_LIMITS = {15, 20, 30, 40, 50, 60, 70}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    table: str
    action: str
    description: str


RULES = {r.rule_id: r for r in [
    Rule("DQ001", "collisions", "REJECT", "collision_index is missing"),
    Rule("DQ002", "collisions", "REJECT", "duplicate collision_index (first occurrence kept)"),
    Rule("DQ003", "collisions", "REJECT", "date missing or not dd/mm/yyyy"),
    Rule("DQ004", "collisions", "REJECT", "date outside the configured extraction years"),
    Rule("DQ005", "collisions", "REJECT", "time missing or not HH:MM"),
    Rule("DQ006", "collisions", "REJECT", "severity not in {1 Fatal, 2 Serious, 3 Slight}"),
    Rule("DQ007", "collisions", "REJECT", "latitude/longitude missing"),
    Rule("DQ008", "collisions", "REJECT", "latitude/longitude outside the UK bounding box"),
    Rule("DQ009", "collisions", "REJECT", "number_of_vehicles missing or < 1"),
    Rule("DQ010", "collisions", "REJECT", "number_of_casualties missing or < 1"),
    Rule("DQ011", "collisions", "NULLIFY", "speed_limit not a valid UK limit (15-70 mph)"),
    Rule("DQ101", "vehicles", "REJECT", "vehicle has no matching cleaned collision (orphan)"),
    Rule("DQ102", "vehicles", "REJECT", "duplicate (collision_index, vehicle_reference)"),
    Rule("DQ103", "vehicles", "NULLIFY", "age_of_driver outside 0-110"),
    Rule("DQ201", "casualties", "REJECT", "casualty has no matching cleaned collision (orphan)"),
    Rule("DQ202", "casualties", "REJECT", "duplicate (collision_index, casualty_reference)"),
    Rule("DQ203", "casualties", "REJECT", "casualty_severity not in {1, 2, 3}"),
    Rule("DQ204", "casualties", "NULLIFY", "age_of_casualty outside 0-110"),
    Rule("DQ301", "weather_hourly", "NULLIFY", "temperature_2m outside -35..45 C"),
    Rule("DQ302", "weather_hourly", "NULLIFY", "precipitation outside 0..150 mm/h"),
    Rule("DQ303", "weather_hourly", "NULLIFY", "wind_speed_10m outside 0..250 km/h"),
    Rule("DQ304", "weather_hourly", "NULLIFY", "relative_humidity_2m outside 0..100 %"),
]}


class QualityLog:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.rows: list[pd.DataFrame] = []

    def add(self, rule_id: str, df: pd.DataFrame, mask: pd.Series, field: str, id_cols: list[str]) -> int:
        hits = df.loc[mask.fillna(False)]
        if hits.empty:
            return 0
        rule = RULES[rule_id]
        record_id = hits[id_cols].astype("string").fillna("<null>").agg("|".join, axis=1)
        self.rows.append(pd.DataFrame({
            "run_id": self.run_id,
            "table_name": rule.table,
            "record_id": record_id.values,
            "rule_id": rule_id,
            "action": rule.action,
            "field": field,
            "value": hits[field].astype("string").fillna("<null>").values if field in hits else "",
            "description": rule.description,
            "source_file": hits["_source_file"].values if "_source_file" in hits else "open-meteo",
        }))
        return len(hits)

    def frame(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame(columns=["run_id", "table_name", "record_id", "rule_id", "action",
                                         "field", "value", "description", "source_file"])
        return pd.concat(self.rows, ignore_index=True)


def _reject(df: pd.DataFrame, log: QualityLog, rule_id: str, mask: pd.Series, field: str,
            id_cols: list[str]) -> pd.DataFrame:
    log.add(rule_id, df, mask, field, id_cols)
    return df.loc[~mask.fillna(False)]


def _nullify(df: pd.DataFrame, log: QualityLog, rule_id: str, mask: pd.Series, field: str,
             id_cols: list[str]) -> pd.DataFrame:
    log.add(rule_id, df, mask, field, id_cols)
    df = df.copy()
    df.loc[mask.fillna(False), field] = pd.NA
    return df


def clean_collisions(df: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    s = get_settings()
    ids = ["collision_index"]
    df = _reject(df, log, "DQ001", df["collision_index"].isna(), "collision_index", ids)
    df = _reject(df, log, "DQ002", df.duplicated("collision_index", keep="first"), "collision_index", ids)
    df = _reject(df, log, "DQ003", df["collision_date"].isna(), "date", ids)
    df = _reject(df, log, "DQ004", ~df["collision_date"].dt.year.isin(s.stats19_years), "date", ids)
    df = _reject(df, log, "DQ005", df["collision_hour"].isna(), "time", ids)
    df = _reject(df, log, "DQ006", ~df["collision_severity"].isin([1, 2, 3]), "collision_severity", ids)
    df = _reject(df, log, "DQ007", df["latitude"].isna() | df["longitude"].isna(), "latitude", ids)
    outside = ~(df["latitude"].between(s.uk_lat_min, s.uk_lat_max)
                & df["longitude"].between(s.uk_lon_min, s.uk_lon_max))
    df = _reject(df, log, "DQ008", outside, "latitude", ids)
    df = _reject(df, log, "DQ009", ~(df["number_of_vehicles"] >= 1).fillna(False), "number_of_vehicles", ids)
    df = _reject(df, log, "DQ010", ~(df["number_of_casualties"] >= 1).fillna(False), "number_of_casualties", ids)
    bad_speed = (df["speed_limit"].notna() & ~df["speed_limit"].isin(VALID_SPEED_LIMITS)
                 & df["speed_limit"].ne(-1)).fillna(False)
    df = _nullify(df, log, "DQ011", bad_speed, "speed_limit", ids)
    df.loc[df["speed_limit"].eq(-1).fillna(False), "speed_limit"] = pd.NA  # -1 is the documented "missing" code
    return df.reset_index(drop=True)


def _age_out_of_range(age: pd.Series) -> pd.Series:
    return (age.notna() & age.ne(-1) & ~age.between(0, 110)).fillna(False)


def clean_vehicles(df: pd.DataFrame, valid_ids: pd.Series, log: QualityLog) -> pd.DataFrame:
    ids = ["collision_index", "vehicle_reference"]
    df = _reject(df, log, "DQ101", ~df["collision_index"].isin(valid_ids), "collision_index", ids)
    df = _reject(df, log, "DQ102", df.duplicated(ids, keep="first"), "vehicle_reference", ids)
    df = _nullify(df, log, "DQ103", _age_out_of_range(df["age_of_driver"]), "age_of_driver", ids)
    df.loc[df["age_of_driver"].eq(-1).fillna(False), "age_of_driver"] = pd.NA
    return df.reset_index(drop=True)


def clean_casualties(df: pd.DataFrame, valid_ids: pd.Series, log: QualityLog) -> pd.DataFrame:
    ids = ["collision_index", "casualty_reference"]
    df = _reject(df, log, "DQ201", ~df["collision_index"].isin(valid_ids), "collision_index", ids)
    df = _reject(df, log, "DQ202", df.duplicated(ids, keep="first"), "casualty_reference", ids)
    df = _reject(df, log, "DQ203", ~df["casualty_severity"].isin([1, 2, 3]), "casualty_severity", ids)
    df = _nullify(df, log, "DQ204", _age_out_of_range(df["age_of_casualty"]), "age_of_casualty", ids)
    df.loc[df["age_of_casualty"].eq(-1).fillna(False), "age_of_casualty"] = pd.NA
    return df.reset_index(drop=True)


def clean_weather(df: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    ids = ["weather_cell_id", "weather_time"]
    checks = [
        ("DQ301", "temperature_2m", -35, 45),
        ("DQ302", "precipitation", 0, 150),
        ("DQ303", "wind_speed_10m", 0, 250),
        ("DQ304", "relative_humidity_2m", 0, 100),
    ]
    for rule_id, field, low, high in checks:
        mask = df[field].notna() & ~df[field].between(low, high)
        df = _nullify(df, log, rule_id, mask, field, ids)
    return df.reset_index(drop=True)


@pipeline_step("validate_and_clean")
def validate_and_clean(run_id: str) -> dict:
    settings = get_settings()
    staging = settings.staging_dir / run_id
    out_dir = settings.run_dir("cleaned", run_id)
    log = QualityLog(run_id)

    collisions = pd.read_parquet(staging / "collisions.parquet")
    vehicles = pd.read_parquet(staging / "vehicles.parquet")
    casualties = pd.read_parquet(staging / "casualties.parquet")
    weather = pd.read_parquet(staging / "weather_hourly.parquet")
    rows_in = len(collisions) + len(vehicles) + len(casualties) + len(weather)

    clean_c = clean_collisions(collisions, log)
    clean_v = clean_vehicles(vehicles, clean_c["collision_index"], log)
    clean_k = clean_casualties(casualties, clean_c["collision_index"], log)
    clean_w = clean_weather(weather, log) if len(weather) else weather

    clean_c.to_parquet(out_dir / "collisions.parquet", index=False)
    clean_v.to_parquet(out_dir / "vehicles.parquet", index=False)
    clean_k.to_parquet(out_dir / "casualties.parquet", index=False)
    clean_w.to_parquet(out_dir / "weather_hourly.parquet", index=False)

    rejected = log.frame()
    reject_dir = settings.run_dir("rejected", run_id)
    rejected.to_csv(reject_dir / "rejected_records.csv", index=False)

    summary = {
        "run_id": run_id,
        "input_rows": {"collisions": len(collisions), "vehicles": len(vehicles),
                       "casualties": len(casualties), "weather_hourly": len(weather)},
        "clean_rows": {"collisions": len(clean_c), "vehicles": len(clean_v),
                       "casualties": len(clean_k), "weather_hourly": len(clean_w)},
        "rule_hits": (rejected.groupby(["rule_id", "action"]).size().rename("rows").reset_index()
                      .assign(description=lambda d: d["rule_id"].map(lambda r: RULES[r].description))
                      .to_dict(orient="records")),
    }
    (reject_dir / "quality_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    reject_rate = 1 - len(clean_c) / max(len(collisions), 1)
    max_rate = float(os.getenv("MAX_REJECT_RATE", "0.05"))
    if reject_rate > max_rate:
        raise ValueError(f"Quality gate failed: {reject_rate:.2%} of collisions rejected (limit {max_rate:.0%}). "
                         f"See {reject_dir / 'rejected_records.csv'}")

    n_rejected = int((rejected["action"] == "REJECT").sum())
    n_nullified = int((rejected["action"] == "NULLIFY").sum())
    return {"rows_in": rows_in, "rows_out": len(clean_c) + len(clean_v) + len(clean_k) + len(clean_w),
            "message": f"rejected={n_rejected} nullified={n_nullified} collision_reject_rate={reject_rate:.3%}"}
