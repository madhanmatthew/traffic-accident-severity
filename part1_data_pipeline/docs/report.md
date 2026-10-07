# Traffic Accident Severity Analytics – Part 1 Report: Data Pipeline

**Course:** Data Engineering and MLOps  **Project:** 4 – Traffic Accident Severity Analytics and Prediction
**Student:** _<your name / ID>_  **Submission:** Part 1 (data pipeline)

---

## 1. Problem understanding

Every year Great Britain records about 100,000 road collisions involving personal injury. About a quarter of them kill or seriously injure someone (KSI). Road-safety teams need to know **when, where and under which conditions** collisions become severe, so they can target enforcement, lighting, speed management and winter maintenance.

Police collision records already describe the road, the light and the weather as the officer saw it. They don't include **measured** weather (temperature, rain intensity, wind), and they are spread across three related files. The goal of Part 1 is a **reproducible, automated pipeline** that:

1. ingests the public STATS19 collision, vehicle and casualty files and enriches every collision with hourly weather from the Open-Meteo archive
2. validates, cleans and standardises the data, and keeps a full audit trail of what was extracted and rejected
3. stores it in a location- and time-aware analytical warehouse (PostgreSQL/PostGIS star schema plus an accident mart)
4. exposes the patterns through an interactive dashboard
5. produces a leakage-free model-ready table for the Part 2 severity classifier

**Scope:** all police-reported injury collisions in Great Britain for 2023 and 2024 (205,185 collisions, 373,329 vehicles, 261,249 casualties).

## 2. Data sources

| Source | Content | Access | Licence |
|---|---|---|---|
| DfT Road Safety Open Data (STATS19) | collision, vehicle and casualty CSVs per year | `https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-<table>-<year>.csv` | OGL v3.0 |
| Open-Meteo Historical Weather API | hourly temperature, precipitation, rain, snowfall, wind speed/gusts, cloud cover, humidity, WMO code | `https://archive-api.open-meteo.com/v1/archive` (no key) | CC BY 4.0 |

OpenStreetMap was considered for road-context enrichment. STATS19 already provides road class, road type, speed limit and junction detail for every collision, so it was left as future work. `docs/data_sources.md` gives full access instructions and known limitations, such as the 2024 renaming of `accident_*` to `collision_*` columns.

## 3. Architecture and pipeline design

![architecture](architecture.svg)

| Layer | Implementation | Output |
|---|---|---|
| Source | DfT CSV files, Open-Meteo REST API | – |
| Ingestion | Python `requests` with retry/back-off, rate-limit pacing, checksums; orchestrated by Airflow | `data/raw/<source>/<run_id>/`, `ingestion_log.csv` |
| Raw | immutable copy of each file / API response | CSV, JSON |
| Staging | column harmonisation, type casting, lineage column | Parquet |
| Cleaned | 22 data-quality rules, rejected-record log, quality gate | Parquet, `rejected_records.csv` |
| Transformation | lookups, date/time standardisation, weather join, vehicle/casualty features, dimensions, aggregates | Parquet (`analytics/<run_id>`) |
| Storage | PostgreSQL 16 + PostGIS 3 (SQLite fallback for laptops) | 6 dims, 3 facts, 6 mart tables, ML table, 3 audit tables |
| Analytics | Streamlit dashboard | 6 KPIs, 6 tabs |
| MLOps (Part 2) | consumes `ml_accident_features` | – |

**Orchestration.** `dags/traffic_accident_etl_dag.py` defines ten tasks:

`extract_stats19 → stage_stats19 → extract_weather → stage_weather → validate_and_clean → transform → build_marts → load_warehouse → verify_load → publish_run_log`

It runs at 02:00 on the 1st of each month, with `catchup=False` and `max_active_runs=1`. Tasks are retried twice; the weather task is retried three times with 30-minute delays because of API quotas. Every task receives the same `run_id` (`{{ ts_nodash }}Z`) and exchanges data through the run-specific layer folders, not XCom. As a result each task is **idempotent** and can be re-run on its own. `publish_run_log` uses `trigger_rule=ALL_DONE`, so failed runs are also recorded in the warehouse. The same steps are exposed through `traffic-pipeline run` / `traffic-pipeline step <name>` for environments without Airflow.

**Design decisions**

* *Layered files plus a database.* Parquet layers make every intermediate state inspectable and reproducible. The database only holds the analytical and audit layers.
* *Full refresh of analytical tables.* The warehouse is rebuilt from the cleaned layer on every run, so it always matches the output of one pipeline run and is never edited by hand.
* *Raw-file cache.* Annual STATS19 files and weather cell-years that already exist from an earlier run are reused (logged as `CACHED`). This makes monthly refreshes cheap while still writing a raw copy for every run.
* *Single schema definition.* `warehouse_schema.py` (SQLAlchemy metadata with column comments) generates the PostgreSQL DDL and the data dictionary, so documentation and database cannot drift apart.

## 4. Data ingestion

**STATS19.** Six files (three tables × two years) are streamed to disk. Each extraction is logged with source, URL, UTC timestamp, status (`SUCCESS`, `CACHED` or `FAILED`), HTTP status, row count, byte size, SHA-256 and local path. A failed STATS19 download fails the task, because collisions are mandatory.

**Weather.** Every collision is snapped to a 1° grid cell, which gives 59 cells covering Great Britain. For every (cell, year), the API is asked for 8,760 hourly readings in `Europe/London` local time, which matches STATS19 times. Ten cells are batched per call.

Open-Meteo's free tier weights a request by locations × days/14. The first attempt used a 0.5° grid (192 cells), would have needed about 10,000 weighted calls, hit the per-minute limit, and received HTTP 429 responses. The pipeline handled them: it backed off and retried. The design was then changed to:

1. a 1° grid, about 3,000 weighted calls for two years
2. computing the weight of every request and sleeping long enough to stay under 500 calls per minute
3. waiting at least 65 s after any 429

A weather request that still fails is logged as `FAILED`, and the pipeline continues. Those collisions keep `weather_matched = false` and still have the police-recorded weather fields. This failure path is part of the design, so a quota problem degrades the enrichment instead of stopping the warehouse refresh.

**Verified run `20261007T050603Z`:** 6 STATS19 files (839,763 rows, reused from the cache) and 117 weather cell-year responses (1,026,312 hourly rows, 0 failures, 430 s including pacing). See `execution_evidence/ingestion_log_20261007T050603Z.csv`.

## 5. ETL, validation and storage

### 5.1 Staging
* Column names are harmonised across releases (`accident_index` → `collision_index`, and so on), and only the needed columns are kept.
* Codes are cast to nullable integers, and blank, `NULL` or `-1` strings become nulls.
* `date` (`dd/mm/yyyy`) and `time` (`HH:MM`) are parsed. Unparseable values become null, so validation can reject them with a reason.
* A `_source_file` lineage column is added.

### 5.2 Validation (cleaned layer)
Twenty-two rules (see `validation_rules.md`) cover keys, duplicates, dates, times, severity domain, missing or out-of-UK coordinates, vehicle and casualty counts, valid UK speed limits, orphaned child records, ages and weather plausibility. Each rule either **rejects** the row or **nullifies** the value. Every hit is written to `rejected_records.csv` and the `dq_rejected_records` table with the record key, rule, field, value and source file. A **quality gate** fails the run if more than 5 % of collisions are rejected.

Results on the real data: 12 collisions without coordinates (DQ007) and the 34 vehicles and casualties attached to them (DQ101/DQ201). That is 46 records in total, a collision reject rate of 0.006 %. No duplicates, invalid dates or out-of-range values were found. The DfT data is well curated, and the rules mainly act as safeguards for future refreshes.

### 5.3 Transformation
* **Standardisation:** collision datetime, hour, weekday, month, season and time band. Over 20 coded fields are mapped to labels through `lookups.py`; an unknown code becomes `Unknown (code N)` instead of an error. Police force is mapped to its nation.
* **Weather join:** on (`weather_cell_id`, collision time floored to the hour). It uses `validate="many_to_one"`, so one weather hour can never duplicate a collision. **Match rate: 100 %.** Measured values are also banded (temperature, precipitation, wind).
* **Vehicle and casualty features:** per collision, whether a pedal cycle, motorcycle, car, bus or goods vehicle was involved; mean and youngest driver age; pedestrian, child, fatal and serious casualty counts.
* **Dimensions:** `dim_date` (continuous calendar), `dim_time` (24 hours), `dim_location` (police force, nation, local authority, urban/rural, weather cell), `dim_road`, `dim_weather` (police-recorded plus measured bands) and `dim_severity`. Keys are deterministic surrogate keys.
* **Facts:** `fact_accident` (one row per collision, with coordinates, measures and weather), `fact_vehicle`, `fact_casualty`.
* **Accident mart:** `agg_accidents_by_hour`, `agg_accidents_by_day`, `agg_accidents_by_road`, `agg_condition_impact` (a long table covering 10 factors), `mart_location_hotspots` (0.05° grid) and `agg_vehicle_casualty`.
* **Model-ready table:** `ml_accident_features`, 205,173 rows and 44 columns. It contains **only information available when a collision is reported**. Casualty-severity counts and police attendance are deliberately excluded to prevent target leakage in Part 2.

### 5.4 Storage
Tables are created from the SQLAlchemy metadata, with primary keys, foreign keys, indexes and column comments; the DDL is in `sql/schema_postgres.sql`. On PostgreSQL, the load step adds PostGIS `geometry(Point, 4326)` columns with a GiST index to `fact_accident` and `mart_location_hotspots`, which enables radius and hotspot queries. `verify_load` reconciles Parquet and database row counts for all 16 tables and checks referential integrity. The verified run loaded 1,061,721 rows in 51 s.

## 6. Visualisation and interpretation

The Streamlit dashboard (`dashboard/app.py`) queries the star schema. It has sidebar filters (year, nation, urban/rural, police force, severity), six KPIs (collisions, fatal, serious, KSI rate, casualties, weather match rate) and six tabs:

1. **Severity distribution:** bar chart and monthly stacked area
2. **Time patterns:** hour × weekday heat map, KSI rate by hour, collisions by weekday
3. **Weather and road conditions:** selectable factor showing volume and KSI rate; KSI rate by speed limit and area
4. **Hotspot map:** adjustable grid and threshold, sized by volume and coloured by KSI rate
5. **Vehicles and casualties:** casualties by vehicle category, KSI share by road-user class, age bands
6. **Pipeline and data quality:** latest step log, ingestion log, rule hits and rejected records

_Insert dashboard screenshots here (execution_evidence/)._

**Key findings (2023–2024, 205,173 collisions)**

| Finding | Evidence |
|---|---|
| Severity is highly imbalanced | Slight 75.6 %, Serious 22.9 %, Fatal 1.5 % (KSI 24.4 %) |
| Volume peaks in the weekday evening rush | 15:00–17:59 is the busiest period (≈17–18k collisions per hour of day); Friday is the busiest day (33.6k), Sunday the quietest (23.1k) |
| Night collisions are fewer but more severe | KSI 30.5 % for 00–05 h (32.6 % at 02:00) vs 21.9 % in the morning peak |
| Darkness without street lighting is the riskiest light condition | KSI 34.5 % vs 23.3 % in daylight |
| Rural roads and 60 mph limits are the most severe | rural KSI 29.4 % vs urban 21.9 %; 60 mph KSI 34.3 % vs 19.7 % at 20 mph |
| Rain increases volume but not severity | measured heavy rain (>2 mm/h) KSI 22.5 % vs 24.6 % when dry, consistent with lower speeds in poor weather |
| Pedestrians are the most vulnerable road users | 31.3 % of pedestrian casualties are KSI vs 20.2 % of drivers/riders |
| Hotspots are concentrated in central London | the five busiest 5 km cells are all in the Metropolitan Police area (up to 2,256 collisions) |

**Interpretation for road safety:** the conditions that make collisions *severe* (unlit rural high-speed roads at night) are different from those that make them *frequent* (urban rush hour). Interventions should be prioritised differently for each, and this distinction motivates the Part 2 severity model.

## 7. Data quality and reliability

* Every extraction, step and rejection is logged as CSV and in database tables, and is visible on the dashboard.
* Analytical tables are rebuilt from code and are never edited by hand.
* Tests (`pytest`, 12 passing) cover the rules, joins, banding, keys and calendar.
* The quality gate, load verification, retries and cache make reruns safe.
* Credentials only come from environment variables (`.env`, git-ignored).

## 8. Limitations and future work

* The 1° weather grid gives regional rather than street-level weather. A 0.5° grid is supported but needs about 3× more API quota, or a paid tier.
* STATS19 only covers injury collisions that police recorded, and some severity misclassification is known (DfT publishes adjusted severity, which is not used here).
* No traffic-volume exposure data, so rates are "share of collisions that are severe", not risk per vehicle-km.
* Future work: OpenStreetMap road context (lighting, lanes), incremental loads instead of full refresh, and Great Expectations-style data contracts.

## 9. How to reproduce

See `README.md`: `traffic-pipeline run` (local, SQLite) or `docker compose up` (PostGIS + Airflow + dashboard). The evidence for the verified run is in `docs/execution_evidence/`.

## References
* Department for Transport (2025). *Road Safety Data*. data.gov.uk, OGL v3.0.
* Zippenfenig, P. (2023). *Open-Meteo.com Weather API*. Zenodo. CC BY 4.0.
* Hersbach, H. et al. (2020). The ERA5 global reanalysis. *QJRMS* 146(730).
