"""Accident mart: pre-aggregated tables that feed the dashboard.

  agg_accidents_by_hour      - year x weekday x hour
  agg_accidents_by_day       - calendar day with daily weather
  agg_accidents_by_road      - road class x road type x speed limit
  agg_condition_impact       - long table: factor/level -> counts and KSI rate
  mart_location_hotspots     - ~5 km grid cells with counts and KSI rate
  agg_vehicle_casualty       - vehicle category x casualty class x severity
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .audit import pipeline_step
from .config import get_settings


def _severity_counts(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    df = df.assign(_fatal=df["severity_key"].eq(1), _serious=df["severity_key"].eq(2),
                   _slight=df["severity_key"].eq(3))
    out = df.groupby(by, dropna=False).agg(
        accidents=("collision_index", "size"),
        fatal=("_fatal", "sum"),
        serious=("_serious", "sum"),
        slight=("_slight", "sum"),
        casualties=("number_of_casualties", "sum"),
    ).reset_index()
    out["ksi_rate"] = ((out["fatal"] + out["serious"]) / out["accidents"]).round(4)
    return out


def accident_view(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Denormalised fact + dimensions (also useful for ad-hoc analysis)."""
    f = tables["fact_accident"]
    return (f.merge(tables["dim_date"], on="date_key")
            .merge(tables["dim_time"], on="hour_key")
            .merge(tables["dim_location"], on="location_key")
            .merge(tables["dim_road"], on="road_key")
            .merge(tables["dim_weather"], on="weather_key")
            .merge(tables["dim_severity"], on="severity_key"))


def build_marts(tables: dict[str, pd.DataFrame], hotspot_grid_deg: float) -> dict[str, pd.DataFrame]:
    a = accident_view(tables)

    by_hour = _severity_counts(a, ["year", "weekday_num", "weekday_name", "hour_key"])

    by_day = _severity_counts(a, ["full_date", "year", "weekday_name", "is_weekend"])
    daily_weather = a.groupby("full_date").agg(mean_temperature_c=("temperature_c", "mean"),
                                               mean_precipitation_mm=("precipitation_mm", "mean")).reset_index()
    by_day = by_day.merge(daily_weather, on="full_date", how="left")

    by_road = _severity_counts(a, ["first_road_class_label", "road_type_label", "speed_limit_label",
                                   "urban_rural_label"])

    factors = {
        "Weather condition (police)": "weather_conditions_label",
        "Road surface": "road_surface_label",
        "Light conditions": "light_conditions_label",
        "Precipitation (Open-Meteo)": "precipitation_band",
        "Temperature (Open-Meteo)": "temperature_band",
        "Wind (Open-Meteo)": "wind_band",
        "Speed limit": "speed_limit_label",
        "Urban / rural": "urban_rural_label",
        "Junction": "junction_detail_label",
        "Time band": "time_band",
    }
    impact = []
    for factor, column in factors.items():
        part = _severity_counts(a, [column]).rename(columns={column: "level"})
        part.insert(0, "factor", factor)
        impact.append(part)
    condition_impact = pd.concat(impact, ignore_index=True)
    condition_impact["level"] = condition_impact["level"].astype(str)

    g = hotspot_grid_deg
    a["hotspot_lat"] = ((a["latitude"] / g).apply(np.floor) * g + g / 2).round(4)
    a["hotspot_lon"] = ((a["longitude"] / g).apply(np.floor) * g + g / 2).round(4)
    hotspots = _severity_counts(a, ["hotspot_lat", "hotspot_lon"])
    top_force = (a.groupby(["hotspot_lat", "hotspot_lon"])["police_force_name"]
                 .agg(lambda s: s.mode().iat[0]).rename("police_force_name").reset_index())
    hotspots = hotspots.merge(top_force, on=["hotspot_lat", "hotspot_lon"])
    hotspots["hotspot_id"] = hotspots["hotspot_lat"].astype(str) + "_" + hotspots["hotspot_lon"].astype(str)

    veh = tables["fact_vehicle"][["collision_index", "vehicle_reference", "vehicle_category"]]
    cas = tables["fact_casualty"]
    vc = cas.merge(veh, on=["collision_index", "vehicle_reference"], how="left")
    vc["vehicle_category"] = vc["vehicle_category"].fillna("Unknown")
    vehicle_casualty = (vc.groupby(["vehicle_category", "casualty_class", "casualty_severity"])
                        .size().rename("casualties").reset_index())

    return {
        "agg_accidents_by_hour": by_hour,
        "agg_accidents_by_day": by_day,
        "agg_accidents_by_road": by_road,
        "agg_condition_impact": condition_impact,
        "mart_location_hotspots": hotspots,
        "agg_vehicle_casualty": vehicle_casualty,
    }


STAR_TABLES = ["dim_date", "dim_time", "dim_location", "dim_road", "dim_weather", "dim_severity",
               "fact_accident", "fact_vehicle", "fact_casualty"]


@pipeline_step("build_marts")
def build_marts_step(run_id: str) -> dict:
    settings = get_settings()
    out_dir = settings.analytics_dir / run_id
    tables = {name: pd.read_parquet(out_dir / f"{name}.parquet") for name in STAR_TABLES}
    marts = build_marts(tables, settings.hotspot_grid_deg)
    for name, df in marts.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return {"rows_in": len(tables["fact_accident"]), "rows_out": sum(len(m) for m in marts.values()),
            "message": ", ".join(f"{k}={len(v)}" for k, v in marts.items())}
