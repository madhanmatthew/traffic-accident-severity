"""Warehouse schema (single source of truth).

The SQLAlchemy metadata below is used to
  * create the tables in PostgreSQL/PostGIS (or SQLite for local runs),
  * export `sql/schema_postgres.sql` (scripts/export_schema.py),
  * generate `docs/data_dictionary.md` from the column comments.
"""
from __future__ import annotations

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, MetaData, String,
                        Table, Text)

metadata = MetaData()


def C(name, type_, comment, *args, **kw):  # noqa: N802 - short alias keeps the table definitions readable
    return Column(name, type_, *args, comment=comment, **kw)


# ------------------------------------------------------------------ dimensions
dim_date = Table(
    "dim_date", metadata,
    C("date_key", Integer, "Surrogate key yyyymmdd", primary_key=True, autoincrement=False),
    C("full_date", Date, "Calendar date"),
    C("year", Integer, "Calendar year"),
    C("quarter", Integer, "Quarter 1-4"),
    C("month", Integer, "Month number 1-12"),
    C("month_name", String(12), "Month name"),
    C("day_of_month", Integer, "Day of month"),
    C("weekday_num", Integer, "ISO weekday, 1 = Monday ... 7 = Sunday"),
    C("weekday_name", String(10), "Weekday name"),
    C("is_weekend", Boolean, "True for Saturday/Sunday"),
    C("season", String(10), "Meteorological season (Winter = Dec-Feb)"),
    comment="Calendar dimension covering every day in the extracted period",
)

dim_time = Table(
    "dim_time", metadata,
    C("hour_key", Integer, "Hour of day 0-23 (UK local time)", primary_key=True, autoincrement=False),
    C("hour_label", String(5), "Hour as HH:00"),
    C("time_band", String(30), "Night / morning peak / daytime / evening peak / late evening"),
    C("is_peak_hour", Boolean, "07-09 or 16-18"),
    comment="Hour-of-day dimension",
)

dim_location = Table(
    "dim_location", metadata,
    C("location_key", Integer, "Surrogate key", primary_key=True, autoincrement=False),
    C("police_force_code", String(10), "STATS19 police force code"),
    C("police_force_name", String(40), "Police force name"),
    C("nation", String(10), "England / Wales / Scotland (derived from police force)"),
    C("local_authority_ons_district", String(12), "ONS local authority district code"),
    C("urban_rural_label", String(20), "Urban / Rural / Unallocated"),
    C("weather_cell_id", String(16), "Weather grid cell centre 'lat_lon' used for the Open-Meteo join"),
    comment="Location dimension (police force, local authority, urban/rural, weather cell)",
)

dim_road = Table(
    "dim_road", metadata,
    C("road_key", Integer, "Surrogate key", primary_key=True, autoincrement=False),
    C("first_road_class_label", String(20), "Motorway, A(M), A, B, C, Unclassified"),
    C("road_type_label", String(40), "Roundabout, single/dual carriageway, slip road, ..."),
    C("speed_limit_label", String(20), "Posted speed limit in mph (text, 'Unknown' if invalid)"),
    C("junction_detail_label", String(40), "Junction type at the collision site"),
    C("junction_control_label", String(40), "Junction control (signals, give way, ...)"),
    comment="Road dimension (junk dimension of road attributes)",
)

dim_weather = Table(
    "dim_weather", metadata,
    C("weather_key", Integer, "Surrogate key", primary_key=True, autoincrement=False),
    C("weather_conditions_label", String(40), "Weather recorded by police (STATS19)"),
    C("road_surface_label", String(30), "Road surface condition (STATS19)"),
    C("light_conditions_label", String(40), "Light conditions (STATS19)"),
    C("temperature_band", String(20), "Open-Meteo temperature band at the collision hour"),
    C("precipitation_band", String(30), "Open-Meteo precipitation band at the collision hour"),
    C("wind_band", String(30), "Open-Meteo wind-speed band at the collision hour"),
    comment="Weather and environment dimension (police-recorded + measured weather bands)",
)

dim_severity = Table(
    "dim_severity", metadata,
    C("severity_key", Integer, "1 Fatal, 2 Serious, 3 Slight", primary_key=True, autoincrement=False),
    C("severity_label", String(10), "Severity label"),
    C("is_ksi", Boolean, "Killed or seriously injured (Fatal or Serious)"),
    C("severity_rank", Integer, "1 = most severe"),
    comment="Collision severity dimension",
)

# ------------------------------------------------------------------ facts
fact_accident = Table(
    "fact_accident", metadata,
    C("collision_index", String(20), "DfT unique collision id", primary_key=True),
    C("date_key", Integer, "FK dim_date", ForeignKey("dim_date.date_key")),
    C("hour_key", Integer, "FK dim_time", ForeignKey("dim_time.hour_key")),
    C("location_key", Integer, "FK dim_location", ForeignKey("dim_location.location_key")),
    C("road_key", Integer, "FK dim_road", ForeignKey("dim_road.road_key")),
    C("weather_key", Integer, "FK dim_weather", ForeignKey("dim_weather.weather_key")),
    C("severity_key", Integer, "FK dim_severity", ForeignKey("dim_severity.severity_key")),
    C("collision_datetime", DateTime, "Local date and time of the collision"),
    C("latitude", Float, "WGS84 latitude"),
    C("longitude", Float, "WGS84 longitude"),
    C("lsoa_code", String(12), "Lower Super Output Area of the collision"),
    C("number_of_vehicles", Integer, "Vehicles involved"),
    C("number_of_casualties", Integer, "Casualties"),
    C("n_pedestrian_casualties", Integer, "Pedestrian casualties"),
    C("n_fatal_casualties", Integer, "Fatal casualties"),
    C("n_serious_casualties", Integer, "Seriously injured casualties"),
    C("n_child_casualties", Integer, "Casualties aged under 16"),
    C("involves_pedal_cycle", Boolean, "At least one pedal cycle involved"),
    C("involves_motorcycle", Boolean, "At least one motorcycle involved"),
    C("involves_car", Boolean, "At least one car/taxi involved"),
    C("involves_bus", Boolean, "At least one bus/minibus involved"),
    C("involves_goods_vehicle", Boolean, "At least one goods vehicle involved"),
    C("mean_driver_age", Float, "Mean age of drivers (known ages only)"),
    C("youngest_driver_age", Float, "Youngest driver age"),
    C("weather_matched", Boolean, "True when an Open-Meteo reading was joined"),
    C("temperature_c", Float, "Air temperature at 2 m (C), Open-Meteo"),
    C("precipitation_mm", Float, "Precipitation in the hour (mm), Open-Meteo"),
    C("rain_mm", Float, "Rain in the hour (mm), Open-Meteo"),
    C("snowfall_cm", Float, "Snowfall in the hour (cm), Open-Meteo"),
    C("wind_speed_kmh", Float, "Wind speed at 10 m (km/h), Open-Meteo"),
    C("wind_gusts_kmh", Float, "Wind gusts at 10 m (km/h), Open-Meteo"),
    C("cloud_cover_pct", Float, "Cloud cover (%), Open-Meteo"),
    C("humidity_pct", Float, "Relative humidity at 2 m (%), Open-Meteo"),
    C("wmo_weather_code", Float, "WMO weather code, Open-Meteo"),
    C("police_attended_label", String(30), "Whether a police officer attended the scene"),
    comment="One row per reported road collision (grain: collision)",
)

fact_vehicle = Table(
    "fact_vehicle", metadata,
    C("collision_index", String(20), "FK fact_accident", ForeignKey("fact_accident.collision_index"),
      primary_key=True),
    C("vehicle_reference", Integer, "Vehicle number within the collision", primary_key=True,
      autoincrement=False),
    C("date_key", Integer, "FK dim_date", ForeignKey("dim_date.date_key")),
    C("collision_severity_key", Integer, "Severity of the collision", ForeignKey("dim_severity.severity_key")),
    C("vehicle_type", String(40), "Vehicle type label"),
    C("vehicle_category", String(30), "Grouped vehicle type"),
    C("sex_of_driver", String(20), "Driver sex"),
    C("age_of_driver", Float, "Driver age (null if unknown/invalid)"),
    C("age_band_of_driver", String(20), "Driver age band"),
    C("engine_capacity_cc", Float, "Engine capacity (cc)"),
    C("age_of_vehicle", Float, "Vehicle age (years)"),
    comment="One row per vehicle involved in a collision",
)

fact_casualty = Table(
    "fact_casualty", metadata,
    C("collision_index", String(20), "FK fact_accident", ForeignKey("fact_accident.collision_index"),
      primary_key=True),
    C("casualty_reference", Integer, "Casualty number within the collision", primary_key=True,
      autoincrement=False),
    C("vehicle_reference", Integer, "Vehicle the casualty was in / hit by"),
    C("date_key", Integer, "FK dim_date", ForeignKey("dim_date.date_key")),
    C("casualty_severity_key", Integer, "FK dim_severity", ForeignKey("dim_severity.severity_key")),
    C("casualty_severity", String(10), "Casualty severity label"),
    C("casualty_class", String(30), "Driver or rider / Passenger / Pedestrian"),
    C("casualty_type_group", String(30), "Pedestrian or road-user group of the casualty"),
    C("sex_of_casualty", String(20), "Casualty sex"),
    C("age_of_casualty", Float, "Casualty age"),
    C("age_band_of_casualty", String(20), "Casualty age band"),
    comment="One row per casualty",
)

# ------------------------------------------------------------------ mart / aggregates
_sev_cols = lambda: [  # noqa: E731
    C("accidents", Integer, "Number of collisions"),
    C("fatal", Integer, "Fatal collisions"),
    C("serious", Integer, "Serious collisions"),
    C("slight", Integer, "Slight collisions"),
    C("casualties", Integer, "Total casualties"),
    C("ksi_rate", Float, "(fatal + serious) / accidents"),
]

agg_accidents_by_hour = Table(
    "agg_accidents_by_hour", metadata,
    C("year", Integer, "Year"), C("weekday_num", Integer, "1 = Monday"), C("weekday_name", String(10), "Weekday"),
    C("hour_key", Integer, "Hour 0-23"), *_sev_cols(),
    comment="Collisions by year, weekday and hour",
)

agg_accidents_by_day = Table(
    "agg_accidents_by_day", metadata,
    C("full_date", Date, "Date"), C("year", Integer, "Year"), C("weekday_name", String(10), "Weekday"),
    C("is_weekend", Boolean, "Weekend flag"), *_sev_cols(),
    C("mean_temperature_c", Float, "Mean temperature at collision hours"),
    C("mean_precipitation_mm", Float, "Mean hourly precipitation at collision hours"),
    comment="Daily collision counts with weather",
)

agg_accidents_by_road = Table(
    "agg_accidents_by_road", metadata,
    C("first_road_class_label", String(20), "Road class"), C("road_type_label", String(40), "Road type"),
    C("speed_limit_label", String(20), "Speed limit"), C("urban_rural_label", String(20), "Urban/rural"),
    *_sev_cols(),
    comment="Collisions by road class, road type, speed limit and urban/rural",
)

agg_condition_impact = Table(
    "agg_condition_impact", metadata,
    C("factor", String(40), "Contributing factor (weather, surface, light, ...)"),
    C("level", String(60), "Factor level"), *_sev_cols(),
    comment="Long-format table: severity profile for each level of each contributing factor",
)

mart_location_hotspots = Table(
    "mart_location_hotspots", metadata,
    C("hotspot_id", String(24), "Grid cell id", primary_key=True),
    C("hotspot_lat", Float, "Cell centre latitude (0.05 deg grid)"),
    C("hotspot_lon", Float, "Cell centre longitude (0.05 deg grid)"),
    *_sev_cols(),
    C("police_force_name", String(40), "Most frequent police force in the cell"),
    comment="Collision hotspots on a ~5 km grid",
)

agg_vehicle_casualty = Table(
    "agg_vehicle_casualty", metadata,
    C("vehicle_category", String(30), "Vehicle category linked to the casualty"),
    C("casualty_class", String(30), "Casualty class"),
    C("casualty_severity", String(10), "Casualty severity"),
    C("casualties", Integer, "Number of casualties"),
    comment="Casualties by vehicle category, casualty class and severity",
)

ml_accident_features = Table(
    "ml_accident_features", metadata,
    C("collision_index", String(20), "DfT unique collision id", primary_key=True),
    C("collision_datetime", DateTime, "Local date/time (used for the chronological split)"),
    C("year", Integer, "Year"), C("month", Integer, "Month"), C("weekday", String(10), "Weekday name"),
    C("hour", Integer, "Hour 0-23"),
    C("latitude", Float, "Latitude"), C("longitude", Float, "Longitude"),
    C("weather_cell_id", String(16), "Weather grid cell"),
    C("police_force", String(40), "Police force name"), C("nation", String(10), "Nation"),
    C("local_authority_ons_district", String(12), "ONS district code"),
    C("urban_or_rural", String(20), "Urban/rural"),
    C("first_road_class", String(20), "Road class"), C("road_type", String(40), "Road type"),
    C("speed_limit", Float, "Speed limit (mph)"),
    C("junction_detail", String(40), "Junction type"), C("junction_control", String(40), "Junction control"),
    C("light_conditions", String(40), "Light conditions"),
    C("weather_conditions", String(40), "Police-recorded weather"),
    C("road_surface_conditions", String(30), "Road surface"),
    C("special_conditions_at_site", String(40), "Special conditions"),
    C("carriageway_hazards", String(40), "Carriageway hazards"),
    C("number_of_vehicles", Integer, "Vehicles involved"),
    C("number_of_casualties", Integer, "Casualties"),
    C("temperature_c", Float, "Temperature (C)"), C("precipitation_mm", Float, "Precipitation (mm/h)"),
    C("snowfall_cm", Float, "Snowfall (cm/h)"), C("wind_speed_kmh", Float, "Wind speed (km/h)"),
    C("wind_gusts_kmh", Float, "Wind gusts (km/h)"), C("cloud_cover_pct", Float, "Cloud cover (%)"),
    C("humidity_pct", Float, "Relative humidity (%)"),
    C("weather_matched", Boolean, "Measured weather available"),
    C("involves_pedal_cycle", Boolean, "Pedal cycle involved"),
    C("involves_motorcycle", Boolean, "Motorcycle involved"),
    C("involves_car", Boolean, "Car involved"), C("involves_bus", Boolean, "Bus involved"),
    C("involves_goods_vehicle", Boolean, "Goods vehicle involved"),
    C("pedestrian_involved", Boolean, "At least one pedestrian casualty"),
    C("mean_driver_age", Float, "Mean driver age"), C("youngest_driver_age", Float, "Youngest driver age"),
    C("severity", Integer, "TARGET: 1 Fatal, 2 Serious, 3 Slight"),
    C("severity_label", String(10), "TARGET label"),
    comment="Model-ready table for Part 2 (no post-outcome / leakage columns)",
)

# ------------------------------------------------------------------ audit / data quality
etl_ingestion_log = Table(
    "etl_ingestion_log", metadata,
    C("run_id", String(20), "Pipeline run id"), C("source", String(30), "Source system"),
    C("dataset", String(40), "Dataset / file"), C("url", Text, "Source URL"),
    C("extracted_at_utc", String(30), "Extraction timestamp (UTC)"),
    C("status", String(10), "SUCCESS / CACHED / FAILED / SKIPPED"),
    C("http_status", String(5), "HTTP status code"), C("row_count", Integer, "Rows in the extracted file"),
    C("bytes", Integer, "File size"), C("sha256", String(64), "File checksum"),
    C("local_path", Text, "Raw landing-zone path"), C("message", Text, "Details / error"),
    comment="One row per file or API extraction",
)

etl_run_log = Table(
    "etl_run_log", metadata,
    C("run_id", String(20), "Pipeline run id"), C("step", String(30), "Pipeline step"),
    C("status", String(10), "SUCCESS / FAILED"), C("started_at_utc", String(30), "Start"),
    C("finished_at_utc", String(30), "End"), C("duration_s", Float, "Duration (s)"),
    C("rows_in", Integer, "Rows read"), C("rows_out", Integer, "Rows written"), C("message", Text, "Details"),
    comment="One row per pipeline step execution",
)

dq_rejected_records = Table(
    "dq_rejected_records", metadata,
    C("run_id", String(20), "Pipeline run id"), C("table_name", String(20), "Table the record belongs to"),
    C("record_id", String(60), "Business key of the record"), C("rule_id", String(6), "Validation rule id"),
    C("action", String(8), "REJECT (row removed) or NULLIFY (value set to null)"),
    C("field", String(40), "Offending field"), C("value", Text, "Offending value"),
    C("description", Text, "Rule description"), C("source_file", Text, "Raw file the record came from"),
    comment="Rejected-record / error log produced by the data-quality step",
)

Index("ix_fact_accident_date", fact_accident.c.date_key)
Index("ix_fact_accident_location", fact_accident.c.location_key)
Index("ix_fact_accident_severity", fact_accident.c.severity_key)
Index("ix_ml_features_datetime", ml_accident_features.c.collision_datetime)
Index("ix_dq_rejected_run", dq_rejected_records.c.run_id)

AUDIT_TABLES = ["etl_ingestion_log", "etl_run_log", "dq_rejected_records"]
# Load order respects foreign keys.
ANALYTICS_TABLES = [
    "dim_date", "dim_time", "dim_location", "dim_road", "dim_weather", "dim_severity",
    "fact_accident", "fact_vehicle", "fact_casualty",
    "agg_accidents_by_hour", "agg_accidents_by_day", "agg_accidents_by_road", "agg_condition_impact",
    "mart_location_hotspots", "agg_vehicle_casualty", "ml_accident_features",
]
