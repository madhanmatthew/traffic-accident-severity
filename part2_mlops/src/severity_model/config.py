"""Configuration for the Part 2 MLOps pipeline (all values overridable by env vars / .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")

CLASS_NAMES = ["Fatal", "Serious", "Slight"]  # model label = severity code - 1
KSI_CLASSES = [0, 1]  # Fatal, Serious = "killed or seriously injured"


def _path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    path = Path(value) if value else default
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


@dataclass(frozen=True)
class Settings:
    # Input: the model-ready table produced by Part 1 (Parquet export or warehouse table).
    features_path: Path = field(default_factory=lambda: _path(
        "FEATURES_PATH",
        PROJECT_ROOT.parent / "part1_data_pipeline" / "data" / "analytics" / "latest" / "ml_accident_features.parquet"))
    features_database_url: str = field(default_factory=lambda: os.getenv("FEATURES_DATABASE_URL", ""))

    # Chronological split: train <= train_end < valid <= valid_end < test
    train_end: str = field(default_factory=lambda: os.getenv("TRAIN_END", "2024-06-30"))
    valid_end: str = field(default_factory=lambda: os.getenv("VALID_END", "2024-09-30"))

    mlflow_tracking_uri: str = field(default_factory=lambda: os.getenv(
        "MLFLOW_TRACKING_URI", f"sqlite:///{(PROJECT_ROOT / 'mlflow.db').as_posix()}"))
    mlflow_artifact_root: Path = field(default_factory=lambda: _path("MLFLOW_ARTIFACT_ROOT", PROJECT_ROOT / "mlartifacts"))
    experiment_name: str = field(default_factory=lambda: os.getenv("MLFLOW_EXPERIMENT", "traffic-severity"))
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "traffic-severity-classifier"))
    champion_alias: str = "champion"

    champion_dir: Path = field(default_factory=lambda: _path("CHAMPION_DIR", PROJECT_ROOT / "models" / "champion"))
    reports_dir: Path = field(default_factory=lambda: _path("REPORTS_DIR", PROJECT_ROOT / "reports"))
    prediction_log_path: Path = field(default_factory=lambda: _path(
        "PREDICTION_LOG_PATH", PROJECT_ROOT / "logs" / "predictions.jsonl"))

    random_state: int = 42
    # A challenger replaces the champion only if test macro-F1 improves by at least this much.
    promotion_min_delta: float = field(default_factory=lambda: float(os.getenv("PROMOTION_MIN_DELTA", "0.005")))


@dataclass(frozen=True)
class RetrainingPolicy:
    """Retraining criteria (documented in docs/model_lifecycle.md)."""
    feature_psi_threshold: float = 0.2      # any key feature with PSI above this = significant drift
    max_drifted_features: int = 3           # retrain when more features than this drift
    class_psi_threshold: float = 0.1        # predicted/actual class mix shift
    location_psi_threshold: float = 0.2     # police-force distribution shift
    macro_f1_drop: float = 0.05             # absolute drop vs. champion baseline
    ksi_fnr_increase: float = 0.05          # absolute increase of KSI false-negative rate
    max_missing_rate_increase: float = 0.10 # input data-quality alarm
    max_error_rate: float = 0.02            # API failures / requests
    max_p95_latency_ms: float = 300.0
    max_model_age_days: int = 180           # scheduled refresh even without drift


def get_settings() -> Settings:
    return Settings()
