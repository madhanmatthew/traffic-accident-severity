"""MLflow Model Registry helpers + the local champion bundle used by the API image.

The registry is the source of truth (`models:/traffic-severity-classifier@champion`).
On promotion the champion is also exported to `models/champion/`:
    model.joblib            - the full sklearn Pipeline (features + preprocessing + classifier)
    metadata.json           - version, run id, training window, test metrics
    reference_profile.json  - training-time statistics for drift monitoring
so the Docker image can serve the model without access to the tracking server.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import mlflow
from mlflow.tracking import MlflowClient

from .config import get_settings


@dataclass
class Champion:
    model: object
    metadata: dict
    profile: dict


def setup_mlflow() -> MlflowClient:
    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    if mlflow.get_experiment_by_name(settings.experiment_name) is None:
        settings.mlflow_artifact_root.mkdir(parents=True, exist_ok=True)
        mlflow.create_experiment(settings.experiment_name, artifact_location=settings.mlflow_artifact_root.as_uri())
    mlflow.set_experiment(settings.experiment_name)
    return MlflowClient()


def get_registered_champion(client: MlflowClient):
    """Return (model_version, sklearn pipeline) for the current champion alias, or (None, None)."""
    settings = get_settings()
    try:
        version = client.get_model_version_by_alias(settings.model_name, settings.champion_alias)
    except Exception:
        return None, None
    model = mlflow.sklearn.load_model(f"models:/{settings.model_name}@{settings.champion_alias}")
    return version, model


def promote(client: MlflowClient, version: str, pipeline, metadata: dict, profile: dict) -> None:
    settings = get_settings()
    client.set_registered_model_alias(settings.model_name, settings.champion_alias, version)
    client.set_model_version_tag(settings.model_name, version, "stage", "champion")
    export_champion(pipeline, metadata, profile)


def export_champion(pipeline, metadata: dict, profile: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or get_settings().champion_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out_dir / "model.joblib", compress=3)
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    (out_dir / "reference_profile.json").write_text(json.dumps(profile, default=str), encoding="utf-8")
    return out_dir


def load_champion(model_dir: Path | None = None) -> Champion:
    model_dir = model_dir or get_settings().champion_dir
    if not (model_dir / "model.joblib").exists():
        raise FileNotFoundError(f"No champion model in {model_dir} - run `python -m severity_model.train` first")
    return Champion(
        model=joblib.load(model_dir / "model.joblib"),
        metadata=json.loads((model_dir / "metadata.json").read_text(encoding="utf-8")),
        profile=json.loads((model_dir / "reference_profile.json").read_text(encoding="utf-8")),
    )
