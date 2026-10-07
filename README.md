# Project 4 – Traffic Accident Severity Analytics and Prediction

Data Engineering and MLOps – individual project. The repository is split into the two assignment parts. Each part is a self-contained project with its own README, requirements, Docker setup, tests and report.

| Part | Folder | Deliverable |
|---|---|---|
| **Part 1 – Data pipeline** (50 marks) | [`part1_data_pipeline/`](part1_data_pipeline/README.md) | STATS19 + Open-Meteo ingestion → Airflow ETL → raw/staging/cleaned/analytical layers → PostgreSQL/PostGIS star schema and accident mart → Streamlit dashboard |
| **Part 2 – MLOps extension** (50 marks) | [`part2_mlops/`](part2_mlops/README.md) | severity classifier (RF / XGBoost / LightGBM with class weighting) → MLflow tracking + registry → FastAPI in Docker → drift / false-negative monitoring → retraining policy |

Part 2 consumes exactly one artefact from Part 1: the model-ready table `ml_accident_features`. It reads it from `part1_data_pipeline/data/analytics/latest/` or straight from the warehouse via `FEATURES_DATABASE_URL`.

## Quick start (end-to-end, local)

```bash
python -m venv .venv
```
```bash
.venv\Scripts\activate
```
```bash
pip install -r part1_data_pipeline/requirements.txt -r part2_mlops/requirements.txt
```
```bash
cd part1_data_pipeline && python -m traffic_pipeline.cli run && cd ..
```
(set `PYTHONPATH=src`, or run `pip install -e part1_data_pipeline` first)
```bash
cd part2_mlops && python -m severity_model.train
```

Then follow each part's README for the dashboards, the API and Docker.

## Data sources
* UK Department for Transport – Road Safety Open Data (STATS19), Open Government Licence v3.0
* Open-Meteo Historical Weather API, CC BY 4.0

No personal or confidential data is used. Credentials only ever come from environment variables, through `.env` files that are git-ignored.
