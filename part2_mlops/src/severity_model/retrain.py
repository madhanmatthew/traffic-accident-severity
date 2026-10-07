"""Retraining job: monitor -> decide -> (re)train -> champion/challenger promotion.

    python -m severity_model.retrain            # retrain only if the policy says so
    python -m severity_model.retrain --force    # scheduled refresh

The newest labelled data from Part 1 (collisions after the champion's test
window start) is used as the monitoring batch. Training always uses the latest
model-ready table, and a challenger is promoted only if it beats the champion
on the same test window (see train.run_training).
"""
from __future__ import annotations

import argparse

import pandas as pd

from .config import get_settings
from .data import load_features
from .features import RAW_FEATURES, TARGET
from .monitoring import build_report, save_report
from .registry import load_champion
from .train import run_training


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor and retrain if needed")
    parser.add_argument("--force", action="store_true", help="retrain regardless of the monitoring result")
    args = parser.parse_args(argv)
    settings = get_settings()

    try:
        champion = load_champion()
    except FileNotFoundError:
        print("no champion yet - training the first model")
        run_training()
        return 0

    df = load_features()
    recent = df[df["collision_datetime"] >= pd.Timestamp(champion.metadata["test_window"][0])]
    X, y = recent[RAW_FEATURES], recent[TARGET].astype(int) - 1
    report = build_report(X, champion.model.predict(X), champion.profile, champion.metadata["metrics"], y_true=y,
                          api_log=settings.prediction_log_path, model_trained_at=champion.metadata["trained_at"])
    path = save_report(report, "retrain_check")
    decision = report["retraining"]
    print(f"monitoring report: {path}")
    print("retraining required:", decision["required"], decision["reasons"], decision["warnings"])

    if decision["required"] or args.force:
        result = run_training()
        print("training result:", result["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
