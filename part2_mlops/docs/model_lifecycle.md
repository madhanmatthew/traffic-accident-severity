# Model lifecycle and retraining criteria

```
Part 1 ETL (monthly) ──► ml_accident_features ──► train (LightGBM) ──► MLflow run + registry version
                                                        │
                                   champion/challenger gate on the same test window
                                                        │
                       alias @champion ──► export models/champion ──► Docker image ──► FastAPI
                                                                                     │
                                         prediction log (JSONL) ◄────────────────────┘
                                                        │
               weekly monitoring (labelled batch + prediction log) ──► report ──► retrain?
```

## 1. Development
* **Data**: the `ml_accident_features` table from Part 1. Columns that are only known after the outcome (casualty severity counts, police attendance) are excluded upstream, so they can't leak the target.
* **Split**: chronological. With the default settings: train = Jan 2023 → Jun 2024, validation = Jul → Sep 2024, test = Oct → Dec 2024. A random split would leak seasonal patterns from the future into training.
* **Model**: one LightGBM classifier with balanced class weights. Fatal collisions are only about 1.5 % of rows, so without weighting the model would almost never predict them.
* **Packaging**: one `sklearn.Pipeline` contains `AccidentFeatureEngineer` → `ColumnTransformer` (imputation + one-hot encoding with an infrequent-category bucket) → classifier. Training and serving therefore run exactly the same transformation code.

## 2. Tracking and registry (MLflow)
| What | Where |
|---|---|
| params | split dates, LightGBM hyper-parameters, weighting |
| metrics | macro-F1, weighted-F1, balanced accuracy, accuracy, per-class recall/precision/F1, **KSI recall and false-negative rate** |
| artifacts | confusion matrices and classification reports (validation + test), split summary, reference profile |
| model | full inference pipeline with signature and input example, registered as `traffic-severity-classifier` version *n* |

Every training run creates a new registry version. The `@champion` alias moves to a new version only when its test macro-F1 beats the current champion's **on the same test window** by at least `PROMOTION_MIN_DELTA` (0.005). The decision is stored as the run tag `promotion_decision`.

## 3. Deployment
* `models/champion/` holds `model.joblib`, `metadata.json` and `reference_profile.json`, and is baked into the Docker image (`Dockerfile`).
* Setting `MODEL_URI=models:/traffic-severity-classifier@champion` makes the API load straight from the registry instead.
* Rollback means moving the alias back: `client.set_registered_model_alias(name, "champion", <old version>)`, then re-exporting or restarting the service.

## 4. Monitoring (`python -m severity_model.monitoring`)
| Signal | Method | Source |
|---|---|---|
| Input data quality | missing-rate increase, out-of-range numerics, unseen categories | labelled batch or API log |
| Feature drift | PSI per feature against the training reference profile | both |
| Class drift | PSI of the predicted class mix, plus the actual class mix when labels exist | both |
| Location drift | PSI of the police-force and nation distributions, plus centroid shift in km | both |
| Performance | macro-F1, per-class recall, **KSI false-negative rate** against the champion's baseline | labelled batch |
| Latency / failures | p50/p95 latency and error rate (including invalid payloads) | API log and `/metrics` |

## 5. Retraining criteria (`RetrainingPolicy` in `config.py`)
Retraining is triggered when **any** of these holds:
1. more than 3 key features have PSI > 0.2
2. class distribution PSI > 0.1
3. location (police-force) PSI > 0.2
4. macro-F1 has dropped by more than 0.05 from the champion baseline
5. KSI false-negative rate has risen by more than 0.05 (absolute)
6. the champion is older than 180 days (scheduled refresh)

These conditions only raise **warnings** and don't trigger retraining: an input missing-rate increase above 10 points, an API error rate above 2 %, or p95 latency above 300 ms. They point to upstream or infrastructure faults, and retraining on broken data would make things worse.

The Airflow DAG `severity_model_lifecycle` (`dags/`) runs every Monday: monitor → branch → retrain or skip. `python -m severity_model.retrain` does the same thing by hand.

## 6. Retirement
A model version is retired when it is no longer the champion and a newer champion has been in service for one full monitoring cycle without being rolled back. Versions are never deleted, so every past prediction can still be traced to its version through `model_version` in the prediction log.
