# Project 4 – Part 2: MLOps Pipeline for Accident Severity Prediction

This part extends the Part 1 warehouse into an end-to-end MLOps solution. It predicts whether a reported collision is **Fatal, Serious or Slight**, tracks every experiment in **MLflow**, versions models in the **MLflow Model Registry**, serves the champion with **FastAPI in Docker**, and monitors **input quality, feature/class/location drift, false-negative rate, latency and failures**, using an explicit retraining policy.

```
Part 1 ml_accident_features ─► train.py ─► MLflow (runs, metrics, artefacts, registry @champion)
                                              │ champion/challenger gate
                                              ▼
                              models/champion ─► Docker: FastAPI /predict ─► Streamlit UI
                                                          │ prediction log
                                                          ▼
                              monitoring.py (PSI drift, KSI FNR, latency) ─► retrain.py / Airflow DAG
```

## Assignment requirements → implementation

| Requirement | Where |
|---|---|
| Predict severity with LightGBM | `src/severity_model/train.py` |
| Address class imbalance | balanced per-sample class weights (`class_weights()`) |
| Track recall, macro-F1, confusion matrices with MLflow | `evaluate.py` + `train.py`: per-class recall/precision/F1, macro-F1, KSI false-negative rate, confusion-matrix PNG/CSV |
| Package preprocessing and model as one inference pipeline | `features.py`: `Pipeline(AccidentFeatureEngineer → ColumnTransformer → classifier)` |
| Reproducible feature-engineering and training pipelines | deterministic seeds, config by env, data fingerprint tag, `python -m severity_model.train` |
| Chronological split | `data.chronological_split`: train ≤ 2024-06-30 < validation ≤ 2024-09-30 < test |
| Register and version the model | MLflow Model Registry `traffic-severity-classifier`, alias `@champion` |
| FastAPI + Docker | `src/severity_model/api.py`, `Dockerfile`, `docker-compose.yml` |
| Integrate into Streamlit | `dashboard/app.py`: prediction form (calls the API), model card, monitoring view |
| Monitor class drift, location drift, false negatives, data quality, latency, failures | `src/severity_model/monitoring.py` |
| Retraining criteria and model lifecycle | `config.RetrainingPolicy`, `retrain.py`, `dags/severity_model_lifecycle_dag.py`, `docs/model_lifecycle.md` |

## Setup

Part 1 must have been run first, so that `../part1_data_pipeline/data/analytics/latest/ml_accident_features.parquet` exists. Alternatively, set `FEATURES_DATABASE_URL` to the Part 1 warehouse.

```bash
python -m venv .venv
```
```bash
.venv\Scripts\activate
```
```bash
pip install -r requirements.txt
```
```bash
pip install -e .
```

## 1. Train, track and register

```bash
python -m severity_model.train
```
This trains one LightGBM pipeline with balanced class weights and logs metrics and confusion matrices to MLflow. It then registers a new version and promotes it to `@champion` if it beats the current champion's test macro-F1, exporting `models/champion/` on promotion.

Browse the experiments:
```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000
```

## 2. Serve the model

Locally:
```bash
uvicorn severity_model.api:app --port 8000
```
With Docker (build after training, because the image bakes in `models/champion/`):
```bash
docker compose up -d --build
```
* Swagger UI: http://localhost:8000/docs. Endpoints: `/predict`, `/predict/batch`, `/health`, `/model-info`, `/metrics`.
* Streamlit UI: http://localhost:8502 (Docker), or run `streamlit run dashboard/app.py` locally.
* MLflow server: http://localhost:5000 (Docker).

Example request:
```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d "{\"hour\":23,\"month\":12,\"weekday\":\"Saturday\",\"latitude\":54.9,\"longitude\":-2.9,\"nation\":\"England\",\"urban_or_rural\":\"Rural\",\"first_road_class\":\"A\",\"road_type\":\"Single carriageway\",\"speed_limit\":60,\"light_conditions\":\"Darkness - no lighting\",\"road_surface_conditions\":\"Wet or damp\",\"number_of_vehicles\":1,\"number_of_casualties\":1,\"involves_motorcycle\":true,\"involves_car\":false}"
```

## 3. Monitor and retrain

```bash
python -m severity_model.monitoring
```
This checks the newest labelled period (after `VALID_END`) against the champion: data quality, PSI drift, class and location drift, macro-F1 and KSI false-negative rate.
```bash
python -m severity_model.monitoring --prediction-log logs/predictions.jsonl
```
This checks production traffic captured by the API, which is unlabelled: input drift, predicted-class drift, latency and failures.
```bash
python -m severity_model.monitoring --simulate-drift
```
This is a demo with a deliberately shifted batch, so you can see the alarms and the retraining decision fire.
```bash
python -m severity_model.retrain
```
This runs the monitor and retrains only if the policy says so. Add `--force` for a scheduled refresh.

Reports are written to `reports/` as JSON and Markdown. The latest one is also shown in the Streamlit "Monitoring" tab.

## Tests

```bash
pytest
```
Covers feature engineering, the chronological split, class weights, end-to-end pipeline inference (including unseen categories), the metric definitions, PSI and drift detection, and the API (predict, batch, validation errors, metrics, prediction log).

## Documentation
* `docs/report.docx`: Part 2 report (model development, evaluation, deployment, monitoring)
* `docs/model_lifecycle.md`: lifecycle and retraining criteria
* `docs/execution_evidence/`: champion metadata and metrics, confusion matrix, monitoring reports, API/MLflow/Streamlit screenshots
