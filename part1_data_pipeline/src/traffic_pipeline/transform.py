"""Transformation layer: cleaned -> star schema + model-ready table.

Outputs (Parquet, `data/analytics/<run_id>/`):
  dim_date, dim_time, dim_location, dim_road, dim_weather, dim_severity
  fact_accident   - one row per collision, joined with hourly weather
  fact_vehicle    - one row per vehicle involved
  fact_casualty   - one row per casualty
  ml_accident_features - model-ready table consumed by Part 2
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import lookups as lk
from .audit import get_logger, pipeline_step
from .config import get_settings
from .extract import assign_weather_cell

logger = get_logger()

WEATHER_RENAME = {
    "temperature_2m": "temperature_c", "precipitation": "precipitation_mm", "rain": "rain_mm",
    "snowfall": "snowfall_cm", "wind_speed_10m": "wind_speed_kmh", "wind_gusts_10m": "wind_gusts_kmh",
    "cloud_cover": "cloud_cover_pct", "relative_humidity_2m": "humidity_pct", "weather_code": "wmo_weather_code",
}


# --------------------------------------------------------------------------- banding helpers
def temperature_band(t: pd.Series) -> pd.Series:
    bins = [-np.inf, 0, 5, 10, 15, 20, np.inf]
    names = ["Below 0C", "0-5C", "5-10C", "10-15C", "15-20C", "Above 20C"]
    return pd.cut(t, bins=bins, labels=names, right=False).astype("object").fillna("Unknown")


def precipitation_band(p: pd.Series) -> pd.Series:
    bins = [-np.inf, 0, 0.5, 2, np.inf]
    names = ["Dry (0 mm/h)", "Light (<0.5 mm/h)", "Moderate (0.5-2 mm/h)", "Heavy (>2 mm/h)"]
    return pd.cut(p, bins=bins, labels=names, right=True).astype("object").fillna("Unknown")


def wind_band(w: pd.Series) -> pd.Series:
    bins = [-np.inf, 20, 40, 60, np.inf]
    names = ["Calm/light (<20 km/h)", "Moderate (20-40 km/h)", "Strong (40-60 km/h)", "Gale (60+ km/h)"]
    return pd.cut(w, bins=bins, labels=names, right=False).astype("object").fillna("Unknown")


def time_band(hour: pd.Series) -> pd.Series:
    bins = [-1, 5, 9, 15, 19, 23]
    names = ["Night (00-05)", "Morning peak (06-09)", "Daytime (10-15)", "Evening peak (16-19)", "Late evening (20-23)"]
    return pd.cut(hour, bins=bins, labels=names).astype("object")


def season(month: pd.Series) -> pd.Series:
    return month.map({12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
                      6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"})


def _surrogate_key(df: pd.DataFrame, columns: list[str], key_name: str) -> tuple[pd.DataFrame, pd.Series]:
    """Build a dimension from the distinct combinations of `columns` and return (dim, key per row)."""
    filled = df[columns].astype("string").fillna("Unknown")
    dim = filled.drop_duplicates().sort_values(columns).reset_index(drop=True)
    dim.insert(0, key_name, np.arange(1, len(dim) + 1))
    keys = filled.merge(dim, on=columns, how="left")[key_name].to_numpy()
    return dim, pd.Series(keys, index=df.index)


# --------------------------------------------------------------------------- enrichment
def standardise_collisions(c: pd.DataFrame) -> pd.DataFrame:
    c = c.copy()
    c["collision_datetime"] = c["collision_date"] + pd.to_timedelta(c["collision_hour"].astype(int), unit="h") \
        + pd.to_timedelta(c["collision_minute"].fillna(0).astype(int), unit="m")
    c["weather_join_time"] = c["collision_datetime"].dt.floor("h")
    c["severity_label"] = lk.label(c["collision_severity"], lk.SEVERITY)
    c["first_road_class_label"] = lk.label(c["first_road_class"], lk.FIRST_ROAD_CLASS)
    c["road_type_label"] = lk.label(c["road_type"], lk.ROAD_TYPE)
    c["junction_detail_label"] = lk.label(c["junction_detail"], lk.JUNCTION_DETAIL)
    c["junction_control_label"] = lk.label(c["junction_control"], lk.JUNCTION_CONTROL)
    c["light_conditions_label"] = lk.label(c["light_conditions"], lk.LIGHT_CONDITIONS)
    c["weather_conditions_label"] = lk.label(c["weather_conditions"], lk.WEATHER_CONDITIONS)
    c["road_surface_label"] = lk.label(c["road_surface_conditions"], lk.ROAD_SURFACE)
    c["special_conditions_label"] = lk.label(c["special_conditions_at_site"], lk.SPECIAL_CONDITIONS)
    c["carriageway_hazards_label"] = lk.label(c["carriageway_hazards"], lk.CARRIAGEWAY_HAZARDS)
    c["urban_rural_label"] = lk.label(c["urban_or_rural_area"], lk.URBAN_RURAL)
    c["police_attended_label"] = lk.label(c["did_police_officer_attend_scene_of_accident"], lk.POLICE_ATTENDED)
    c["police_force_name"] = lk.police_force_name(c["police_force"])
    c["nation"] = lk.nation(c["police_force"])
    c["speed_limit_label"] = c["speed_limit"].astype("string").fillna("Unknown")
    return c


def join_weather(c: pd.DataFrame, w: pd.DataFrame, grid_deg: float) -> pd.DataFrame:
    c = assign_weather_cell(c, grid_deg)
    w = w.rename(columns={"weather_time": "weather_join_time", **WEATHER_RENAME})
    merged = c.merge(w, on=["weather_cell_id", "weather_join_time"], how="left", validate="many_to_one")
    merged["weather_matched"] = merged["temperature_c"].notna()
    for col in WEATHER_RENAME.values():
        if col not in merged:
            merged[col] = np.nan
    merged["temperature_band"] = temperature_band(merged["temperature_c"])
    merged["precipitation_band"] = precipitation_band(merged["precipitation_mm"])
    merged["wind_band"] = wind_band(merged["wind_speed_kmh"])
    return merged


def vehicle_features(v: pd.DataFrame) -> pd.DataFrame:
    v = v.copy()
    v["vehicle_category"] = lk.label(v["vehicle_type"], lk.VEHICLE_CATEGORY, unknown="Unknown")
    flags = {
        "involves_pedal_cycle": "Pedal cycle", "involves_motorcycle": "Motorcycle", "involves_car": "Car",
        "involves_bus": "Bus", "involves_goods_vehicle": "Goods vehicle",
    }
    for column, category in flags.items():
        v[column] = v["vehicle_category"].eq(category)
    agg = v.groupby("collision_index").agg(
        **{c: (c, "max") for c in flags},
        mean_driver_age=("age_of_driver", "mean"),
        youngest_driver_age=("age_of_driver", "min"),
    )
    return agg.reset_index()


def casualty_features(k: pd.DataFrame) -> pd.DataFrame:
    k = k.assign(
        is_pedestrian=k["casualty_class"].eq(3),
        is_fatal=k["casualty_severity"].eq(1),
        is_serious=k["casualty_severity"].eq(2),
        is_child=k["age_of_casualty"].lt(16),
    )
    agg = k.groupby("collision_index").agg(
        n_pedestrian_casualties=("is_pedestrian", "sum"),
        n_fatal_casualties=("is_fatal", "sum"),
        n_serious_casualties=("is_serious", "sum"),
        n_child_casualties=("is_child", "sum"),
    )
    return agg.reset_index()


# --------------------------------------------------------------------------- dimensions
def build_dim_date(dates: pd.Series) -> pd.DataFrame:
    days = pd.date_range(dates.min(), dates.max(), freq="D")
    dim = pd.DataFrame({"full_date": days})
    dim.insert(0, "date_key", dim["full_date"].dt.strftime("%Y%m%d").astype(int))
    dim["year"] = days.year
    dim["quarter"] = days.quarter
    dim["month"] = days.month
    dim["month_name"] = days.month_name()
    dim["day_of_month"] = days.day
    dim["weekday_num"] = days.dayofweek + 1  # 1 = Monday
    dim["weekday_name"] = days.day_name()
    dim["is_weekend"] = dim["weekday_num"] >= 6
    dim["season"] = season(dim["month"])
    return dim


def build_dim_time() -> pd.DataFrame:
    hours = pd.Series(range(24))
    return pd.DataFrame({"hour_key": hours, "hour_label": hours.map(lambda h: f"{h:02d}:00"),
                         "time_band": time_band(hours), "is_peak_hour": hours.isin([7, 8, 9, 16, 17, 18])})


def build_dim_severity() -> pd.DataFrame:
    return pd.DataFrame({"severity_key": [1, 2, 3], "severity_label": ["Fatal", "Serious", "Slight"],
                         "is_ksi": [True, True, False], "severity_rank": [1, 2, 3]})


# --------------------------------------------------------------------------- main step
@pipeline_step("transform")
def transform(run_id: str) -> dict:
    settings = get_settings()
    cleaned = settings.cleaned_dir / run_id
    out_dir = settings.run_dir("analytics", run_id)

    c = pd.read_parquet(cleaned / "collisions.parquet")
    v = pd.read_parquet(cleaned / "vehicles.parquet")
    k = pd.read_parquet(cleaned / "casualties.parquet")
    w = pd.read_parquet(cleaned / "weather_hourly.parquet")

    c = standardise_collisions(c)
    c = join_weather(c, w, settings.weather_grid_deg)
    c = c.merge(vehicle_features(v), on="collision_index", how="left")
    c = c.merge(casualty_features(k), on="collision_index", how="left")
    for col in ["involves_pedal_cycle", "involves_motorcycle", "involves_car", "involves_bus",
                "involves_goods_vehicle"]:
        c[col] = c[col].fillna(False).astype(bool)
    for col in ["n_pedestrian_casualties", "n_fatal_casualties", "n_serious_casualties", "n_child_casualties"]:
        c[col] = c[col].fillna(0).astype(int)

    # ---- dimensions
    dim_date = build_dim_date(c["collision_date"])
    dim_time = build_dim_time()
    dim_severity = build_dim_severity()
    dim_location, c["location_key"] = _surrogate_key(
        c, ["police_force", "police_force_name", "nation", "local_authority_ons_district",
            "urban_rural_label", "weather_cell_id"], "location_key")
    dim_location = dim_location.rename(columns={"police_force": "police_force_code"})
    dim_road, c["road_key"] = _surrogate_key(
        c, ["first_road_class_label", "road_type_label", "speed_limit_label", "junction_detail_label",
            "junction_control_label"], "road_key")
    dim_weather, c["weather_key"] = _surrogate_key(
        c, ["weather_conditions_label", "road_surface_label", "light_conditions_label",
            "temperature_band", "precipitation_band", "wind_band"], "weather_key")

    c["date_key"] = c["collision_date"].dt.strftime("%Y%m%d").astype(int)
    c["hour_key"] = c["collision_hour"].astype(int)
    c["severity_key"] = c["collision_severity"].astype(int)

    fact_accident = c[[
        "collision_index", "date_key", "hour_key", "location_key", "road_key", "weather_key", "severity_key",
        "collision_datetime", "latitude", "longitude", "lsoa_of_accident_location",
        "number_of_vehicles", "number_of_casualties", "n_pedestrian_casualties", "n_fatal_casualties",
        "n_serious_casualties", "n_child_casualties", "involves_pedal_cycle", "involves_motorcycle",
        "involves_car", "involves_bus", "involves_goods_vehicle", "mean_driver_age", "youngest_driver_age",
        "weather_matched", *WEATHER_RENAME.values(), "police_attended_label",
    ]].rename(columns={"lsoa_of_accident_location": "lsoa_code"})

    date_lookup = c[["collision_index", "date_key", "severity_key"]]
    v = v.merge(date_lookup, on="collision_index", how="inner")
    fact_vehicle = pd.DataFrame({
        "collision_index": v["collision_index"], "vehicle_reference": v["vehicle_reference"],
        "date_key": v["date_key"], "collision_severity_key": v["severity_key"],
        "vehicle_type": lk.label(v["vehicle_type"], lk.VEHICLE_TYPE),
        "vehicle_category": lk.label(v["vehicle_type"], lk.VEHICLE_CATEGORY),
        "sex_of_driver": lk.label(v["sex_of_driver"], lk.SEX),
        "age_of_driver": v["age_of_driver"],
        "age_band_of_driver": lk.label(v["age_band_of_driver"], lk.AGE_BAND),
        "engine_capacity_cc": v["engine_capacity_cc"].where(v["engine_capacity_cc"] > 0),
        "age_of_vehicle": v["age_of_vehicle"].where(v["age_of_vehicle"] >= 0),
    })

    k = k.merge(date_lookup, on="collision_index", how="inner")
    casualty_type_labels = {0: "Pedestrian", **lk.VEHICLE_CATEGORY}
    fact_casualty = pd.DataFrame({
        "collision_index": k["collision_index"], "casualty_reference": k["casualty_reference"],
        "vehicle_reference": k["vehicle_reference"], "date_key": k["date_key"],
        "casualty_severity_key": k["casualty_severity"].astype(int),
        "casualty_severity": lk.label(k["casualty_severity"], lk.SEVERITY),
        "casualty_class": lk.label(k["casualty_class"], lk.CASUALTY_CLASS),
        "casualty_type_group": lk.label(k["casualty_type"], casualty_type_labels),
        "sex_of_casualty": lk.label(k["sex_of_casualty"], lk.SEX),
        "age_of_casualty": k["age_of_casualty"],
        "age_band_of_casualty": lk.label(k["age_band_of_casualty"], lk.AGE_BAND),
    })

    # ---- model-ready table (Part 2). Only information available when a
    # collision is reported is included; casualty-severity counts and police
    # attendance are excluded to avoid target leakage.
    ml = pd.DataFrame({
        "collision_index": c["collision_index"],
        "collision_datetime": c["collision_datetime"],
        "year": c["collision_date"].dt.year,
        "month": c["collision_date"].dt.month,
        "weekday": c["collision_date"].dt.day_name(),
        "hour": c["collision_hour"].astype(int),
        "latitude": c["latitude"], "longitude": c["longitude"],
        "weather_cell_id": c["weather_cell_id"],
        "police_force": c["police_force_name"], "nation": c["nation"],
        "local_authority_ons_district": c["local_authority_ons_district"],
        "urban_or_rural": c["urban_rural_label"],
        "first_road_class": c["first_road_class_label"], "road_type": c["road_type_label"],
        "speed_limit": c["speed_limit"].astype("float"),
        "junction_detail": c["junction_detail_label"], "junction_control": c["junction_control_label"],
        "light_conditions": c["light_conditions_label"], "weather_conditions": c["weather_conditions_label"],
        "road_surface_conditions": c["road_surface_label"],
        "special_conditions_at_site": c["special_conditions_label"],
        "carriageway_hazards": c["carriageway_hazards_label"],
        "number_of_vehicles": c["number_of_vehicles"].astype(int),
        "number_of_casualties": c["number_of_casualties"].astype(int),
        "temperature_c": c["temperature_c"], "precipitation_mm": c["precipitation_mm"],
        "snowfall_cm": c["snowfall_cm"], "wind_speed_kmh": c["wind_speed_kmh"],
        "wind_gusts_kmh": c["wind_gusts_kmh"], "cloud_cover_pct": c["cloud_cover_pct"],
        "humidity_pct": c["humidity_pct"], "weather_matched": c["weather_matched"],
        "involves_pedal_cycle": c["involves_pedal_cycle"], "involves_motorcycle": c["involves_motorcycle"],
        "involves_car": c["involves_car"], "involves_bus": c["involves_bus"],
        "involves_goods_vehicle": c["involves_goods_vehicle"],
        "pedestrian_involved": c["n_pedestrian_casualties"] > 0,
        "mean_driver_age": c["mean_driver_age"], "youngest_driver_age": c["youngest_driver_age"],
        "severity": c["collision_severity"].astype(int), "severity_label": c["severity_label"],
    }).sort_values("collision_datetime").reset_index(drop=True)

    tables = {
        "dim_date": dim_date, "dim_time": dim_time, "dim_location": dim_location, "dim_road": dim_road,
        "dim_weather": dim_weather, "dim_severity": dim_severity, "fact_accident": fact_accident,
        "fact_vehicle": fact_vehicle, "fact_casualty": fact_casualty, "ml_accident_features": ml,
    }
    for name, df in tables.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)

    match_rate = float(c["weather_matched"].mean()) if len(c) else 0.0
    return {"rows_in": len(c), "rows_out": len(fact_accident),
            "message": f"{len(tables)} tables built; weather match rate {match_rate:.1%}"}
