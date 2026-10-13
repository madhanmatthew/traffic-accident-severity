<div align="center">

# 🚦 Traffic Accident Severity Analytics & Prediction

**An end-to-end Data Engineering + MLOps project:**
police collision records + measured weather → validated PostGIS warehouse → dashboard → a monitored severity-prediction API

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Airflow](https://img.shields.io/badge/Apache_Airflow-017CEE?logo=apacheairflow&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostgreSQL_+_PostGIS-336791?logo=postgresql&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![LightGBM](https://img.shields.io/badge/LightGBM-2E8B57)
![MLflow](https://img.shields.io/badge/MLflow-0194E2?logo=mlflow&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)

*Data Engineering and MLOps course project · CMR Institute of Technology, Bengaluru · 2026-27*

</div>

---

## ✨ Highlights

| | Part 1 · Data pipeline | Part 2 · MLOps |
|---|---|---|
| **Goal** | Reproducible, auditable pipeline and analytics warehouse | Predict severity (Fatal / Serious / Slight) and keep the model healthy |
| **Data** | 205,185 collisions · 373,329 vehicles · 261,249 casualties (Great Britain, 2023–2024) | `ml_accident_features`: 205,173 rows × 44 columns, leakage-free |
| **Stack** | Python, Airflow, Parquet, PostgreSQL + PostGIS, Streamlit | LightGBM, MLflow, FastAPI, Docker, Airflow |
| **Result** | 22 validation rules · 0.006 % reject rate · 100 % weather match | **64.6 % KSI recall** · macro-F1 **0.431** · 83 % of fatal crashes flagged |

> **KSI** = killed or seriously injured. About 1 in 4 injury collisions is KSI, so plain accuracy is the wrong metric: a model that always predicts "Slight" scores 75.6 % and catches nothing.

---

## 📑 Contents

[Why](#-why-this-project) · [Architecture](#-architecture) · [Part 1](#-part-1--data-pipeline) · [Part 2](#-part-2--mlops) · [Results](#-results) · [Quick start](#-quick-start) · [Layout](#-repository-layout) · [Data & licences](#-data-sources--licences) · [Limitations & roadmap](#-limitations--roadmap) · [Author](#-author)

---

## 🎯 Why this project

Great Britain records about **100,000 injury collisions a year**. Road-safety teams want to know *when, where and under which conditions* collisions turn severe, but the public data has gaps:

- 🌦 Police records describe weather **as the officer saw it**; there is no measured temperature, rain or wind.
- 🧩 Data is split over **three linked files** (collision, vehicle, casualty) and **column names change between years**.
- ⚖️ Severity is **heavily imbalanced**: Slight 75.6 %, Serious 22.9 %, Fatal 1.5 %.

This project closes those gaps with an automated pipeline, then builds a severity model with a full lifecycle around it.

---

## 🏗 Architecture

**Part 1: data moves through layers**

```text
 Sources              Raw               Staging            Cleaned
┌───────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐
│ DfT STATS19   │──▶│ immutable   │──▶│ harmonised  │──▶│ 22 DQ rules      │
│ Open-Meteo API│   │ copy + SHA  │   │ names/types │   │ reject log, gate │
└───────────────┘   └─────────────┘   └─────────────┘   └────────┬─────────┘
                                                                  │
 Consumers                  Warehouse                 Analytics   ▼
┌──────────────────┐   ┌──────────────────┐   ┌─────────────────────────┐
│ Streamlit        │◀──│ PostgreSQL 16    │◀──│ weather join, features, │
│ dashboard        │   │ + PostGIS 3      │   │ dimensions, facts, marts│
│ ML table → Part 2│   │ (16 tables)      │   └─────────────────────────┘
└──────────────────┘   └──────────────────┘
```

**Part 2: the model lifecycle is a loop**

```text
 Part 1 features ─▶ Train ─▶ MLflow run ─▶ Model registry ─▶ FastAPI (Docker)
 (ml_accident_      (LightGBM)  params,      versions +          │
  features)                     metrics      @champion           ▼
      ▲                                                     Streamlit UI
      │                                                          │
      │ retrain?                                                 ▼
  Retraining policy ◀── Weekly monitoring ◀── Prediction log (model version per request)
  (Airflow, Mondays)    drift · recall · latency

  New model must beat the champion's macro-F1 by ≥ 0.005 on the same test window
```

| Layer | What happens | Output |
|---|---|---|
| **Raw** | Immutable copy of every file / API response, with SHA-256 | CSV, JSON |
| **Staging** | Harmonise column names, cast types, add lineage column | Parquet |
| **Cleaned** | 22 data-quality rules, reject log, quality gate | Parquet + `rejected_records.csv` |
| **Analytics** | Weather join, features, dimensions, facts, marts, ML table | Parquet |
| **Warehouse** | PostgreSQL 16 + PostGIS 3 (SQLite fallback for laptops) | 16 tables |

---

## 🔧 Part 1 · Data pipeline

### Two open sources, one warehouse

- **STATS19** (UK Department for Transport): collision, vehicle and casualty files for 2023 and 2024, 839,763 rows.
- **Open-Meteo** historical weather: hourly temperature, rain, snow, wind, cloud and humidity on a **1° grid (59 cells)**, 1,026,312 hourly rows, matched to **100 %** of collisions.

### Airflow runs ten idempotent tasks

```text
extract_stats19 → stage_stats19 → extract_weather → stage_weather → validate_and_clean
        → transform → build_marts → load_warehouse → verify_load → publish_run_log
```

| | |
|---|---|
| ⏰ **Schedule** | `02:00` on the 1st of each month, `catchup=False`, one run at a time |
| 🔁 **Retries** | 2 per task; weather gets 3, with 30-minute delays (API quota) |
| ♻️ **Idempotent** | Shared `run_id`; data passes through run folders (not XCom), so any task can be re-run alone |
| 🧾 **Always logged** | `publish_run_log` uses `trigger_rule=ALL_DONE`, so failed runs are recorded too |
| 🖥 **No Airflow?** | The same steps run through the `traffic-pipeline` CLI |

### Data quality you can audit

- **22 rules**: `REJECT` drops the row; `NULLIFY` keeps the row and blanks the bad value.
- Every hit is logged with record key, rule, field, value and source file.
- **Quality gate**: the run fails if more than **5 %** of collisions are rejected.
- Real-data result: **46 records rejected out of 1.87 million** (0.006 % of collisions).
- `verify_load` reconciles row counts for all 16 tables and checks foreign keys.

### Star schema (PostgreSQL + PostGIS)

```text
              dim_date      dim_time      dim_location (PostGIS point)
                  \            |            /
 fact_vehicle ──── fact_accident (1 row per collision) ──── fact_casualty
                  /            |            \
              dim_road     dim_weather     dim_severity
```

PostGIS `geometry(Point, 4326)` columns with a GiST index power hotspot and radius queries. A single SQLAlchemy definition generates both the DDL and the data dictionary, so documentation cannot drift from the database.

### Streamlit dashboard

Sidebar filters (year, nation, urban/rural, police force, severity), six KPIs and six tabs:
**Severity distribution · Time patterns · Weather & road conditions · Hotspot map · Vehicles & casualties · Pipeline & data quality**

<details>
<summary><b>🔎 Key findings from the data (2023–2024)</b></summary>

| Finding | Evidence |
|---|---|
| Severity is highly imbalanced | Slight 75.6 %, Serious 22.9 %, Fatal 1.5 % (KSI 24.4 %) |
| Volume peaks in the weekday evening rush | 15:00–17:59 busiest; Friday busiest (33.6k), Sunday quietest (23.1k) |
| Night collisions are fewer but more severe | KSI 30.5 % for 00–05 h vs 21.9 % in the morning peak |
| Unlit darkness is the riskiest light condition | KSI 34.5 % vs 23.3 % in daylight |
| Rural roads and 60 mph limits are most severe | Rural KSI 29.4 % vs urban 21.9 %; 60 mph 34.3 % vs 19.7 % at 20 mph |
| Rain raises volume, not severity | Heavy rain KSI 22.5 % vs 24.6 % when dry |
| Pedestrians are most vulnerable | 31.3 % KSI vs 20.2 % for drivers and riders |
| Hotspots are in central London | Top five 5 km cells are all in the Metropolitan Police area |

**Takeaway:** what makes crashes *severe* (unlit, rural, high-speed roads at night) differs from what makes them *frequent* (urban rush hour), so interventions should be prioritised differently.

</details>

---

## 🤖 Part 2 · MLOps

### The model

One scikit-learn `Pipeline`, so training and serving run identical code (no training/serving skew):

1. **`AccidentFeatureEngineer`**: cyclical hour/month, darkness and wet-road flags, high-speed road, vulnerable road user, and more
2. **`ColumnTransformer`**: median imputation + one-hot encoding with an infrequent-category bucket (unseen categories never crash)
3. **`LGBMClassifier`** with **balanced class weights** (Slight ≈ 0.44, Serious ≈ 1.5, Fatal ≈ 22), chosen over SMOTE so no synthetic collisions are created

### Chronological split: no peeking into the future

| Set | Period |
|---|---|
| Train | Jan 2023 – Jun 2024 (18 months) |
| Validation | Jul – Sep 2024 |
| Test | Oct – Dec 2024 |

### Tracked, versioned, gated

- Every run logs params, metrics (macro-F1, per-class recall, KSI false-negative rate), artefacts and the full pipeline to **MLflow**.
- Registered as `traffic-severity-classifier`. The **`@champion`** alias moves only if the new model beats the champion's macro-F1 by **≥ 0.005** on the same test window.
- Rollback = move the alias back. Versions are never deleted.

### Served with FastAPI + Docker

| Endpoint | Purpose |
|---|---|
| `POST /predict` | One collision → class, probabilities, KSI probability, model version |
| `POST /predict/batch` | Many collisions at once |
| `GET /health` | Service status and model version |
| `GET /model-info` | Version, run id, training/test windows, features, metrics |
| `GET /metrics` | Request/error counts, p50/p95/p99 latency, predicted class counts |

Inputs are validated with pydantic (bad payload → HTTP 422). Every request is logged with its model version.

### Monitored every week

Airflow DAG `severity_model_lifecycle` runs **monitor → branch → retrain or skip**.

| Signal | Method |
|---|---|
| Input data quality | Missing rate, out-of-range values, unseen categories |
| Feature drift | PSI per feature vs the training reference profile |
| Class drift | PSI of predicted (and actual) class mix |
| Location drift | Police-force / nation PSI + centroid shift in km |
| Performance | Macro-F1, per-class recall, KSI false-negative rate |
| Latency & failures | p50/p95 latency, error rate |

PSI guide: `< 0.1` stable · `0.1–0.2` moderate · `> 0.2` significant shift.

**Retrain if ANY of these holds**

1. More than 3 key features with PSI > 0.2
2. Class distribution PSI > 0.1
3. Location (police-force) PSI > 0.2
4. Macro-F1 drops by more than 0.05
5. KSI false-negative rate rises by more than 0.05
6. Champion is older than 180 days

A missing-rate jump, API error rate > 2 % or p95 latency > 300 ms raise **warnings only**: retraining on broken data would make the model worse.

---

## 📊 Results

Evaluated on the **unseen Oct–Dec 2024 test period**.

| Metric | Value |
|---|---|
| KSI recall (Fatal + Serious caught) | **0.646** |
| Macro-F1 (always-"Slight" baseline ≈ 0.29) | **0.431** |
| Accuracy (lower by design) | 0.621 |
| Recall: Fatal / Serious / Slight | 0.298 / 0.555 / 0.647 |

**Confusion matrix** (rows = actual, columns = predicted)

| Actual ↓ / Predicted → | Fatal | Serious | Slight |
|---|---:|---:|---:|
| **Fatal** (389) | **116** | 208 | 65 |
| **Serious** (5,851) | 458 | **3,248** | 2,145 |
| **Slight** (19,809) | 663 | 6,325 | **12,821** |

- 324 of 389 fatal collisions (**83 %**) were flagged as Fatal or Serious.
- The cost is false alarms: 6,325 slight collisions predicted Serious, so Fatal precision is only ≈ 9 %. This is the deliberate accuracy-for-recall trade-off.

**Monitor sanity check**

| Run | Rows | Decision |
|---|---:|---|
| Labelled batch, Oct–Dec 2024 | 26,342 | ✅ No retraining needed (macro-F1 stable at 0.431) |
| Simulated drift (rural, night, wet) | 9,361 | 🔴 **RETRAIN** (7 features with PSI > 0.2, location PSI 0.817, centroid moved 43.7 km) |

---

## 🚀 Quick start

> **Prerequisites:** Python 3, Docker + Docker Compose (for the full stack). Run the commands from each part's folder.

### Part 1: pipeline, warehouse, dashboard

```bash
# Option A: local run (SQLite fallback, no Docker needed)
pip install -e .
traffic-pipeline run                 # all ten steps
traffic-pipeline step <name>         # or a single step

# Option B: full stack (PostGIS + Airflow + dashboard)
docker compose up -d --build
```

Settings (environment variables / `.env`): `STATS19_YEARS`, `FORCE_DOWNLOAD`, `WEATHER_GRID_DEG` (default `1.0`), `MAX_REJECT_RATE` (default `0.05`).

<details>
<summary>Fetch the raw data by hand</summary>

```bash
curl -O https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2024.csv

curl "https://archive-api.open-meteo.com/v1/archive?latitude=51.5&longitude=-0.1&start_date=2024-01-01&end_date=2024-01-02&hourly=temperature_2m,precipitation&timezone=Europe%2FLondon"
```
</details>

### Part 2: train, serve, monitor

```bash
# 1. Part 1 must have produced ml_accident_features.parquet
#    (or set FEATURES_DATABASE_URL to read from the warehouse)
pip install -r requirements.txt && pip install -e .

# 2. Train, track, register and (if it wins the gate) promote
python -m severity_model.train

# 3. Browse experiments
mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

# 4. Serve the champion model
uvicorn severity_model.api:app --port 8000
#    or the whole stack: FastAPI :8000 · MLflow :5000 · Streamlit :8502
docker compose up -d --build

# 5. Monitor (add --simulate-drift to test the alarms)
python -m severity_model.monitoring --prediction-log logs/predictions.jsonl

# 6. Retrain only if the policy says so (--force for a scheduled refresh)
python -m severity_model.retrain
```

Open **http://localhost:8000/docs** for the interactive API, then check the service:

```bash
curl http://localhost:8000/health
# {"status": "ok", "model_version": 1}
```

### Tests

```bash
pytest
```

Part 1: 12 tests (rules, joins, banding, keys, calendar). Part 2: feature engineering, chronological split, class weights, end-to-end inference (incl. unseen categories), metrics, PSI/drift detection and the API.

---

## 🗂 Repository layout

> Adjust folder names to match your checkout.

```text
.
├── part1_data_pipeline/
│   ├── src/traffic_pipeline/          # ingestion, staging, quality.py (22 rules), lookups.py,
│   │                                  # transform, marts, warehouse_schema.py
│   ├── dags/traffic_accident_etl_dag.py
│   ├── dashboard/app.py               # Streamlit dashboard
│   ├── sql/schema_postgres.sql        # generated DDL
│   ├── data/                          # raw → staging → cleaned → analytics (per run_id)
│   └── docs/execution_evidence/       # logs and reports from the verified run
└── part2_mlops_pipeline/
    ├── src/severity_model/            # train, features, data, evaluate, api,
    │                                  # monitoring, config (RetrainingPolicy), retrain
    ├── dags/severity_model_lifecycle_dag.py
    ├── models/champion/               # model.joblib, metadata.json, reference_profile.json
    ├── Dockerfile
    └── docker-compose.yml             # FastAPI + MLflow + Streamlit
```

---

## 📚 Data sources & licences

| Source | Used for | Licence |
|---|---|---|
| [DfT Road Safety Data (STATS19)](https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data) | Collision, vehicle and casualty records | Open Government Licence v3.0 |
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5-based) | Hourly measured weather | CC BY 4.0 |
| OpenStreetMap | *Not used yet*; planned road-context enrichment | ODbL |

All sources are free, public and contain no personally identifiable information.

---

## ⚠️ Limitations & roadmap

**Limitations**

- The 1° weather grid gives **regional**, not street-level, weather.
- STATS19 covers only police-recorded injury collisions; some severity misclassification is known.
- No traffic-volume data, so rates are *share of collisions that are severe*, not risk per vehicle-km.
- Severity depends on things not recorded at report time (speed at impact, seatbelts), which caps achievable performance.
- Probabilities are not calibrated, and Fatal precision of ≈ 9 % means many false alarms.
- Only LightGBM is trained in the final pipeline.

**Roadmap**

- [ ] Probability calibration and threshold tuning for a target KSI recall
- [ ] OpenStreetMap road context (lighting, lanes) as extra features
- [ ] Tracked comparison with XGBoost / random forest
- [ ] Incremental loads instead of full refresh; Great Expectations-style data contracts
- [ ] Finer weather grid (paid API tier); canary deployment of new champions

---

## 👤 Author

**Madhan Matthew S** · B.E. Artificial Intelligence & Machine Learning, CMR Institute of Technology, Bengaluru
USN 1CR23AI052 · Section 7A · Individual project for *Data Engineering and MLOps* (2026-27)

<sub>Built on open data from the UK Department for Transport and Open-Meteo, and on open-source tools: Python, Apache Airflow, PostgreSQL/PostGIS, Streamlit, scikit-learn, LightGBM, MLflow, FastAPI and Docker.</sub>
