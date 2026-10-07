# Validation rules

Rules are implemented in `src/traffic_pipeline/quality.py` (the `RULES` registry) and run in the `validate_and_clean` step, between the staging layer and the cleaned layer. Every rule hit is written to `data/rejected/<run_id>/rejected_records.csv` and the `dq_rejected_records` table. Each hit records the record key, rule, field, offending value and source file. Per-rule counts go to `quality_summary.json`.

* **REJECT**: the row is removed from the cleaned layer.
* **NULLIFY**: the row is kept, but the implausible value is set to NULL.

| Rule | Table | Action | Check |
|---|---|---|---|
| DQ001 | collisions | REJECT | `collision_index` is missing |
| DQ002 | collisions | REJECT | duplicate `collision_index` (the first occurrence is kept) |
| DQ003 | collisions | REJECT | `date` is missing or not `dd/mm/yyyy` |
| DQ004 | collisions | REJECT | date is outside the configured extraction years |
| DQ005 | collisions | REJECT | `time` is missing or not `HH:MM` |
| DQ006 | collisions | REJECT | severity is not 1/2/3 |
| DQ007 | collisions | REJECT | latitude or longitude is missing |
| DQ008 | collisions | REJECT | coordinates are outside the UK bounding box (lat 49.8–61.0, lon −8.7–1.9) |
| DQ009 | collisions | REJECT | `number_of_vehicles` is missing or < 1 |
| DQ010 | collisions | REJECT | `number_of_casualties` is missing or < 1 |
| DQ011 | collisions | NULLIFY | `speed_limit` is not a valid UK limit (15, 20, 30, 40, 50, 60, 70); −1 is treated as missing |
| DQ101 | vehicles | REJECT | orphan: no matching cleaned collision |
| DQ102 | vehicles | REJECT | duplicate (`collision_index`, `vehicle_reference`) |
| DQ103 | vehicles | NULLIFY | `age_of_driver` is outside 0–110; −1 is treated as missing and not logged |
| DQ201 | casualties | REJECT | orphan: no matching cleaned collision |
| DQ202 | casualties | REJECT | duplicate (`collision_index`, `casualty_reference`) |
| DQ203 | casualties | REJECT | `casualty_severity` is not 1/2/3 |
| DQ204 | casualties | NULLIFY | `age_of_casualty` is outside 0–110 |
| DQ301 | weather | NULLIFY | temperature is outside −35..45 °C |
| DQ302 | weather | NULLIFY | precipitation is outside 0..150 mm/h |
| DQ303 | weather | NULLIFY | wind speed is outside 0..250 km/h |
| DQ304 | weather | NULLIFY | relative humidity is outside 0..100 % |

## Pipeline-level checks

| Check | Where | Behaviour |
|---|---|---|
| Quality gate | `validate_and_clean` | The run fails if more than `MAX_REJECT_RATE` (default 5 %) of collisions are rejected, so a broken source file never reaches the warehouse. |
| Mandatory source | `extract_stats19` | A failed STATS19 download fails the task, and Airflow retries it twice. |
| Optional source | `extract_weather` | A failed weather request is logged as `FAILED` and the run continues with `weather_matched = false`. |
| Weather join integrity | `transform` | `merge(validate="many_to_one")` guarantees that a weather hour can never duplicate a collision. |
| Load reconciliation | `verify_load` | Row counts in Parquet and the database must match for all 16 tables. Every `fact_accident.date_key` must exist in `dim_date`. |
| No manual edits | design | Analytical tables are dropped and rebuilt from the cleaned layer on every run. The raw layer is never modified. |
