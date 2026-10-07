"""Train the severity model and track it with MLflow.

    python -m severity_model.train

1. load the Part 1 table, split chronologically (train / valid / test)
2. fit one LightGBM pipeline with balanced class weights (handles imbalance)
3. log metrics (macro-F1, per-class recall, KSI false-negative rate) and confusion matrices
4. register the model; promote to @champion if it beats the current champion on test macro-F1
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import skops.io as skops_io
from lightgbm import LGBMClassifier
from mlflow.models import infer_signature

from . import evaluate as ev
from .config import CLASS_NAMES, get_settings
from .data import chronological_split, load_features, to_xy
from .features import NUMERIC_FEATURES, RAW_FEATURES, build_pipeline
from .monitoring import build_profile
from .registry import get_registered_champion, promote, setup_mlflow

PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=50,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=42, verbose=-1)


def class_weights(y: pd.Series, power: float = 1.0) -> np.ndarray:
    """Per-sample weights (n / (k * n_c)) ** power; power=1 is 'balanced'."""
    counts = y.value_counts()
    per_class = {c: (len(y) / (len(counts) * n)) ** power for c, n in counts.items()}
    return y.map(per_class).to_numpy()


def run_training() -> dict:
    settings = get_settings()
    client = setup_mlflow()
    splits = chronological_split(load_features())
    X_train, y_train = to_xy(splits.train)
    X_valid, y_valid = to_xy(splits.valid)
    X_test, y_test = to_xy(splits.test)

    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with mlflow.start_run(run_name="lightgbm-balanced") as run, tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        model = build_pipeline(LGBMClassifier(**PARAMS))
        model.fit(X_train, y_train, model__sample_weight=class_weights(y_train))

        metrics = {}
        for name, X, y in [("valid", X_valid, y_valid), ("test", X_test, y_test)]:
            pred = model.predict(X)
            metrics |= ev.compute_metrics(y, pred, prefix=f"{name}_")
            ev.plot_confusion_matrix(y, pred, tmp / f"confusion_matrix_{name}.png", f"Confusion matrix ({name})")
            (tmp / f"classification_report_{name}.txt").write_text(ev.report_text(y, pred))
        mlflow.log_params({**PARAMS, "class_weighting": "balanced",
                           "train_end": settings.train_end, "valid_end": settings.valid_end})
        mlflow.log_metrics(metrics)
        mlflow.log_dict(splits.describe(), "split_summary.json")
        mlflow.log_artifacts(str(tmp), "evaluation")

        profile = build_profile(X_train, y_train, y_pred=model.predict(X_test))
        mlflow.log_dict(profile, "reference_profile.json")

        example = X_test.head(5).astype({c: "float64" for c in NUMERIC_FEATURES})
        info = mlflow.sklearn.log_model(
            sk_model=model, name="model", input_example=example,
            signature=infer_signature(example, model.predict_proba(example)),
            skops_trusted_types=skops_io.get_untrusted_types(data=skops_io.dumps(model)))
        version = mlflow.register_model(info.model_uri, settings.model_name).version

        decision = "promoted (first model)"
        champ_version, champ_model = get_registered_champion(client)
        if champ_version is not None:
            champ_f1 = ev.compute_metrics(y_test, champ_model.predict(X_test))["macro_f1"]
            delta = metrics["test_macro_f1"] - champ_f1
            decision = (f"promoted (macro-F1 {delta:+.4f})" if delta >= settings.promotion_min_delta
                        else f"kept champion v{champ_version.version} (delta {delta:+.4f})")
        mlflow.set_tag("promotion_decision", decision)

        metadata = {"model_name": settings.model_name, "version": version, "run_id": run.info.run_id,
                    "model_family": "lightgbm", "class_weighting": "balanced", "trained_at": trained_at,
                    "train_window": [splits.describe()["train_start"], splits.describe()["train_end"]],
                    "test_window": [splits.describe()["test_start"], splits.describe()["test_end"]],
                    "class_names": CLASS_NAMES, "features": RAW_FEATURES,
                    "metrics": {k: v for k, v in metrics.items() if k.startswith("test_")},
                    "promotion_decision": decision}
        if decision.startswith("promoted"):
            promote(client, version, model, metadata, profile)

    print(json.dumps({"version": version, "decision": decision, **metrics}, indent=2))
    return {"version": version, "decision": decision, "metrics": metrics}


if __name__ == "__main__":
    run_training()
