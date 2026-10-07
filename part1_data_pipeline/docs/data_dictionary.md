# Data dictionary

Generated from `src/traffic_pipeline/warehouse_schema.py` by `scripts/export_schema_and_dictionary.py`. PK = primary key, FK = foreign key.

## Dimensions

### `dim_date`

Calendar dimension covering every day in the extracted period

| Column | Type | Key | Description |
|---|---|---|---|
| `date_key` | INTEGER | PK | Surrogate key yyyymmdd |
| `full_date` | DATE |  | Calendar date |
| `year` | INTEGER |  | Calendar year |
| `quarter` | INTEGER |  | Quarter 1-4 |
| `month` | INTEGER |  | Month number 1-12 |
| `month_name` | VARCHAR(12) |  | Month name |
| `day_of_month` | INTEGER |  | Day of month |
| `weekday_num` | INTEGER |  | ISO weekday, 1 = Monday ... 7 = Sunday |
| `weekday_name` | VARCHAR(10) |  | Weekday name |
| `is_weekend` | BOOLEAN |  | True for Saturday/Sunday |
| `season` | VARCHAR(10) |  | Meteorological season (Winter = Dec-Feb) |

### `dim_time`

Hour-of-day dimension

| Column | Type | Key | Description |
|---|---|---|---|
| `hour_key` | INTEGER | PK | Hour of day 0-23 (UK local time) |
| `hour_label` | VARCHAR(5) |  | Hour as HH:00 |
| `time_band` | VARCHAR(30) |  | Night / morning peak / daytime / evening peak / late evening |
| `is_peak_hour` | BOOLEAN |  | 07-09 or 16-18 |

### `dim_location`

Location dimension (police force, local authority, urban/rural, weather cell)

| Column | Type | Key | Description |
|---|---|---|---|
| `location_key` | INTEGER | PK | Surrogate key |
| `police_force_code` | VARCHAR(10) |  | STATS19 police force code |
| `police_force_name` | VARCHAR(40) |  | Police force name |
| `nation` | VARCHAR(10) |  | England / Wales / Scotland (derived from police force) |
| `local_authority_ons_district` | VARCHAR(12) |  | ONS local authority district code |
| `urban_rural_label` | VARCHAR(20) |  | Urban / Rural / Unallocated |
| `weather_cell_id` | VARCHAR(16) |  | Weather grid cell centre 'lat_lon' used for the Open-Meteo join |

### `dim_road`

Road dimension (junk dimension of road attributes)

| Column | Type | Key | Description |
|---|---|---|---|
| `road_key` | INTEGER | PK | Surrogate key |
| `first_road_class_label` | VARCHAR(20) |  | Motorway, A(M), A, B, C, Unclassified |
| `road_type_label` | VARCHAR(40) |  | Roundabout, single/dual carriageway, slip road, ... |
| `speed_limit_label` | VARCHAR(20) |  | Posted speed limit in mph (text, 'Unknown' if invalid) |
| `junction_detail_label` | VARCHAR(40) |  | Junction type at the collision site |
| `junction_control_label` | VARCHAR(40) |  | Junction control (signals, give way, ...) |

### `dim_weather`

Weather and environment dimension (police-recorded + measured weather bands)

| Column | Type | Key | Description |
|---|---|---|---|
| `weather_key` | INTEGER | PK | Surrogate key |
| `weather_conditions_label` | VARCHAR(40) |  | Weather recorded by police (STATS19) |
| `road_surface_label` | VARCHAR(30) |  | Road surface condition (STATS19) |
| `light_conditions_label` | VARCHAR(40) |  | Light conditions (STATS19) |
| `temperature_band` | VARCHAR(20) |  | Open-Meteo temperature band at the collision hour |
| `precipitation_band` | VARCHAR(30) |  | Open-Meteo precipitation band at the collision hour |
| `wind_band` | VARCHAR(30) |  | Open-Meteo wind-speed band at the collision hour |

### `dim_severity`

Collision severity dimension

| Column | Type | Key | Description |
|---|---|---|---|
| `severity_key` | INTEGER | PK | 1 Fatal, 2 Serious, 3 Slight |
| `severity_label` | VARCHAR(10) |  | Severity label |
| `is_ksi` | BOOLEAN |  | Killed or seriously injured (Fatal or Serious) |
| `severity_rank` | INTEGER |  | 1 = most severe |

## Facts

### `fact_accident`

One row per reported road collision (grain: collision)

| Column | Type | Key | Description |
|---|---|---|---|
| `collision_index` | VARCHAR(20) | PK | DfT unique collision id |
| `date_key` | INTEGER | FK → dim_date.date_key | FK dim_date |
| `hour_key` | INTEGER | FK → dim_time.hour_key | FK dim_time |
| `location_key` | INTEGER | FK → dim_location.location_key | FK dim_location |
| `road_key` | INTEGER | FK → dim_road.road_key | FK dim_road |
| `weather_key` | INTEGER | FK → dim_weather.weather_key | FK dim_weather |
| `severity_key` | INTEGER | FK → dim_severity.severity_key | FK dim_severity |
| `collision_datetime` | TIMESTAMP WITHOUT TIME ZONE |  | Local date and time of the collision |
| `latitude` | FLOAT |  | WGS84 latitude |
| `longitude` | FLOAT |  | WGS84 longitude |
| `lsoa_code` | VARCHAR(12) |  | Lower Super Output Area of the collision |
| `number_of_vehicles` | INTEGER |  | Vehicles involved |
| `number_of_casualties` | INTEGER |  | Casualties |
| `n_pedestrian_casualties` | INTEGER |  | Pedestrian casualties |
| `n_fatal_casualties` | INTEGER |  | Fatal casualties |
| `n_serious_casualties` | INTEGER |  | Seriously injured casualties |
| `n_child_casualties` | INTEGER |  | Casualties aged under 16 |
| `involves_pedal_cycle` | BOOLEAN |  | At least one pedal cycle involved |
| `involves_motorcycle` | BOOLEAN |  | At least one motorcycle involved |
| `involves_car` | BOOLEAN |  | At least one car/taxi involved |
| `involves_bus` | BOOLEAN |  | At least one bus/minibus involved |
| `involves_goods_vehicle` | BOOLEAN |  | At least one goods vehicle involved |
| `mean_driver_age` | FLOAT |  | Mean age of drivers (known ages only) |
| `youngest_driver_age` | FLOAT |  | Youngest driver age |
| `weather_matched` | BOOLEAN |  | True when an Open-Meteo reading was joined |
| `temperature_c` | FLOAT |  | Air temperature at 2 m (C), Open-Meteo |
| `precipitation_mm` | FLOAT |  | Precipitation in the hour (mm), Open-Meteo |
| `rain_mm` | FLOAT |  | Rain in the hour (mm), Open-Meteo |
| `snowfall_cm` | FLOAT |  | Snowfall in the hour (cm), Open-Meteo |
| `wind_speed_kmh` | FLOAT |  | Wind speed at 10 m (km/h), Open-Meteo |
| `wind_gusts_kmh` | FLOAT |  | Wind gusts at 10 m (km/h), Open-Meteo |
| `cloud_cover_pct` | FLOAT |  | Cloud cover (%), Open-Meteo |
| `humidity_pct` | FLOAT |  | Relative humidity at 2 m (%), Open-Meteo |
| `wmo_weather_code` | FLOAT |  | WMO weather code, Open-Meteo |
| `police_attended_label` | VARCHAR(30) |  | Whether a police officer attended the scene |

### `fact_vehicle`

One row per vehicle involved in a collision

| Column | Type | Key | Description |
|---|---|---|---|
| `collision_index` | VARCHAR(20) | PK FK → fact_accident.collision_index | FK fact_accident |
| `vehicle_reference` | INTEGER | PK | Vehicle number within the collision |
| `date_key` | INTEGER | FK → dim_date.date_key | FK dim_date |
| `collision_severity_key` | INTEGER | FK → dim_severity.severity_key | Severity of the collision |
| `vehicle_type` | VARCHAR(40) |  | Vehicle type label |
| `vehicle_category` | VARCHAR(30) |  | Grouped vehicle type |
| `sex_of_driver` | VARCHAR(20) |  | Driver sex |
| `age_of_driver` | FLOAT |  | Driver age (null if unknown/invalid) |
| `age_band_of_driver` | VARCHAR(20) |  | Driver age band |
| `engine_capacity_cc` | FLOAT |  | Engine capacity (cc) |
| `age_of_vehicle` | FLOAT |  | Vehicle age (years) |

### `fact_casualty`

One row per casualty

| Column | Type | Key | Description |
|---|---|---|---|
| `collision_index` | VARCHAR(20) | PK FK → fact_accident.collision_index | FK fact_accident |
| `casualty_reference` | INTEGER | PK | Casualty number within the collision |
| `vehicle_reference` | INTEGER |  | Vehicle the casualty was in / hit by |
| `date_key` | INTEGER | FK → dim_date.date_key | FK dim_date |
| `casualty_severity_key` | INTEGER | FK → dim_severity.severity_key | FK dim_severity |
| `casualty_severity` | VARCHAR(10) |  | Casualty severity label |
| `casualty_class` | VARCHAR(30) |  | Driver or rider / Passenger / Pedestrian |
| `casualty_type_group` | VARCHAR(30) |  | Pedestrian or road-user group of the casualty |
| `sex_of_casualty` | VARCHAR(20) |  | Casualty sex |
| `age_of_casualty` | FLOAT |  | Casualty age |
| `age_band_of_casualty` | VARCHAR(20) |  | Casualty age band |

## Accident mart / aggregates

### `agg_accidents_by_hour`

Collisions by year, weekday and hour

| Column | Type | Key | Description |
|---|---|---|---|
| `year` | INTEGER |  | Year |
| `weekday_num` | INTEGER |  | 1 = Monday |
| `weekday_name` | VARCHAR(10) |  | Weekday |
| `hour_key` | INTEGER |  | Hour 0-23 |
| `accidents` | INTEGER |  | Number of collisions |
| `fatal` | INTEGER |  | Fatal collisions |
| `serious` | INTEGER |  | Serious collisions |
| `slight` | INTEGER |  | Slight collisions |
| `casualties` | INTEGER |  | Total casualties |
| `ksi_rate` | FLOAT |  | (fatal + serious) / accidents |

### `agg_accidents_by_day`

Daily collision counts with weather

| Column | Type | Key | Description |
|---|---|---|---|
| `full_date` | DATE |  | Date |
| `year` | INTEGER |  | Year |
| `weekday_name` | VARCHAR(10) |  | Weekday |
| `is_weekend` | BOOLEAN |  | Weekend flag |
| `accidents` | INTEGER |  | Number of collisions |
| `fatal` | INTEGER |  | Fatal collisions |
| `serious` | INTEGER |  | Serious collisions |
| `slight` | INTEGER |  | Slight collisions |
| `casualties` | INTEGER |  | Total casualties |
| `ksi_rate` | FLOAT |  | (fatal + serious) / accidents |
| `mean_temperature_c` | FLOAT |  | Mean temperature at collision hours |
| `mean_precipitation_mm` | FLOAT |  | Mean hourly precipitation at collision hours |

### `agg_accidents_by_road`

Collisions by road class, road type, speed limit and urban/rural

| Column | Type | Key | Description |
|---|---|---|---|
| `first_road_class_label` | VARCHAR(20) |  | Road class |
| `road_type_label` | VARCHAR(40) |  | Road type |
| `speed_limit_label` | VARCHAR(20) |  | Speed limit |
| `urban_rural_label` | VARCHAR(20) |  | Urban/rural |
| `accidents` | INTEGER |  | Number of collisions |
| `fatal` | INTEGER |  | Fatal collisions |
| `serious` | INTEGER |  | Serious collisions |
| `slight` | INTEGER |  | Slight collisions |
| `casualties` | INTEGER |  | Total casualties |
| `ksi_rate` | FLOAT |  | (fatal + serious) / accidents |

### `agg_condition_impact`

Long-format table: severity profile for each level of each contributing factor

| Column | Type | Key | Description |
|---|---|---|---|
| `factor` | VARCHAR(40) |  | Contributing factor (weather, surface, light, ...) |
| `level` | VARCHAR(60) |  | Factor level |
| `accidents` | INTEGER |  | Number of collisions |
| `fatal` | INTEGER |  | Fatal collisions |
| `serious` | INTEGER |  | Serious collisions |
| `slight` | INTEGER |  | Slight collisions |
| `casualties` | INTEGER |  | Total casualties |
| `ksi_rate` | FLOAT |  | (fatal + serious) / accidents |

### `mart_location_hotspots`

Collision hotspots on a ~5 km grid

| Column | Type | Key | Description |
|---|---|---|---|
| `hotspot_id` | VARCHAR(24) | PK | Grid cell id |
| `hotspot_lat` | FLOAT |  | Cell centre latitude (0.05 deg grid) |
| `hotspot_lon` | FLOAT |  | Cell centre longitude (0.05 deg grid) |
| `accidents` | INTEGER |  | Number of collisions |
| `fatal` | INTEGER |  | Fatal collisions |
| `serious` | INTEGER |  | Serious collisions |
| `slight` | INTEGER |  | Slight collisions |
| `casualties` | INTEGER |  | Total casualties |
| `ksi_rate` | FLOAT |  | (fatal + serious) / accidents |
| `police_force_name` | VARCHAR(40) |  | Most frequent police force in the cell |

### `agg_vehicle_casualty`

Casualties by vehicle category, casualty class and severity

| Column | Type | Key | Description |
|---|---|---|---|
| `vehicle_category` | VARCHAR(30) |  | Vehicle category linked to the casualty |
| `casualty_class` | VARCHAR(30) |  | Casualty class |
| `casualty_severity` | VARCHAR(10) |  | Casualty severity |
| `casualties` | INTEGER |  | Number of casualties |

## Model-ready table (input to Part 2)

### `ml_accident_features`

Model-ready table for Part 2 (no post-outcome / leakage columns)

| Column | Type | Key | Description |
|---|---|---|---|
| `collision_index` | VARCHAR(20) | PK | DfT unique collision id |
| `collision_datetime` | TIMESTAMP WITHOUT TIME ZONE |  | Local date/time (used for the chronological split) |
| `year` | INTEGER |  | Year |
| `month` | INTEGER |  | Month |
| `weekday` | VARCHAR(10) |  | Weekday name |
| `hour` | INTEGER |  | Hour 0-23 |
| `latitude` | FLOAT |  | Latitude |
| `longitude` | FLOAT |  | Longitude |
| `weather_cell_id` | VARCHAR(16) |  | Weather grid cell |
| `police_force` | VARCHAR(40) |  | Police force name |
| `nation` | VARCHAR(10) |  | Nation |
| `local_authority_ons_district` | VARCHAR(12) |  | ONS district code |
| `urban_or_rural` | VARCHAR(20) |  | Urban/rural |
| `first_road_class` | VARCHAR(20) |  | Road class |
| `road_type` | VARCHAR(40) |  | Road type |
| `speed_limit` | FLOAT |  | Speed limit (mph) |
| `junction_detail` | VARCHAR(40) |  | Junction type |
| `junction_control` | VARCHAR(40) |  | Junction control |
| `light_conditions` | VARCHAR(40) |  | Light conditions |
| `weather_conditions` | VARCHAR(40) |  | Police-recorded weather |
| `road_surface_conditions` | VARCHAR(30) |  | Road surface |
| `special_conditions_at_site` | VARCHAR(40) |  | Special conditions |
| `carriageway_hazards` | VARCHAR(40) |  | Carriageway hazards |
| `number_of_vehicles` | INTEGER |  | Vehicles involved |
| `number_of_casualties` | INTEGER |  | Casualties |
| `temperature_c` | FLOAT |  | Temperature (C) |
| `precipitation_mm` | FLOAT |  | Precipitation (mm/h) |
| `snowfall_cm` | FLOAT |  | Snowfall (cm/h) |
| `wind_speed_kmh` | FLOAT |  | Wind speed (km/h) |
| `wind_gusts_kmh` | FLOAT |  | Wind gusts (km/h) |
| `cloud_cover_pct` | FLOAT |  | Cloud cover (%) |
| `humidity_pct` | FLOAT |  | Relative humidity (%) |
| `weather_matched` | BOOLEAN |  | Measured weather available |
| `involves_pedal_cycle` | BOOLEAN |  | Pedal cycle involved |
| `involves_motorcycle` | BOOLEAN |  | Motorcycle involved |
| `involves_car` | BOOLEAN |  | Car involved |
| `involves_bus` | BOOLEAN |  | Bus involved |
| `involves_goods_vehicle` | BOOLEAN |  | Goods vehicle involved |
| `pedestrian_involved` | BOOLEAN |  | At least one pedestrian casualty |
| `mean_driver_age` | FLOAT |  | Mean driver age |
| `youngest_driver_age` | FLOAT |  | Youngest driver age |
| `severity` | INTEGER |  | TARGET: 1 Fatal, 2 Serious, 3 Slight |
| `severity_label` | VARCHAR(10) |  | TARGET label |

## Audit and data-quality tables

### `etl_ingestion_log`

One row per file or API extraction

| Column | Type | Key | Description |
|---|---|---|---|
| `run_id` | VARCHAR(20) |  | Pipeline run id |
| `source` | VARCHAR(30) |  | Source system |
| `dataset` | VARCHAR(40) |  | Dataset / file |
| `url` | TEXT |  | Source URL |
| `extracted_at_utc` | VARCHAR(30) |  | Extraction timestamp (UTC) |
| `status` | VARCHAR(10) |  | SUCCESS / CACHED / FAILED / SKIPPED |
| `http_status` | VARCHAR(5) |  | HTTP status code |
| `row_count` | INTEGER |  | Rows in the extracted file |
| `bytes` | INTEGER |  | File size |
| `sha256` | VARCHAR(64) |  | File checksum |
| `local_path` | TEXT |  | Raw landing-zone path |
| `message` | TEXT |  | Details / error |

### `etl_run_log`

One row per pipeline step execution

| Column | Type | Key | Description |
|---|---|---|---|
| `run_id` | VARCHAR(20) |  | Pipeline run id |
| `step` | VARCHAR(30) |  | Pipeline step |
| `status` | VARCHAR(10) |  | SUCCESS / FAILED |
| `started_at_utc` | VARCHAR(30) |  | Start |
| `finished_at_utc` | VARCHAR(30) |  | End |
| `duration_s` | FLOAT |  | Duration (s) |
| `rows_in` | INTEGER |  | Rows read |
| `rows_out` | INTEGER |  | Rows written |
| `message` | TEXT |  | Details |

### `dq_rejected_records`

Rejected-record / error log produced by the data-quality step

| Column | Type | Key | Description |
|---|---|---|---|
| `run_id` | VARCHAR(20) |  | Pipeline run id |
| `table_name` | VARCHAR(20) |  | Table the record belongs to |
| `record_id` | VARCHAR(60) |  | Business key of the record |
| `rule_id` | VARCHAR(6) |  | Validation rule id |
| `action` | VARCHAR(8) |  | REJECT (row removed) or NULLIFY (value set to null) |
| `field` | VARCHAR(40) |  | Offending field |
| `value` | TEXT |  | Offending value |
| `description` | TEXT |  | Rule description |
| `source_file` | TEXT |  | Raw file the record came from |
