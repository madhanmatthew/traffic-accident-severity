"""Command-line entry point - runs the same steps as the Airflow DAG.

    python -m traffic_pipeline.cli run                 # full end-to-end run
    python -m traffic_pipeline.cli run --skip-weather  # no API calls
    python -m traffic_pipeline.cli step transform --run-id 20260901T020000Z
"""
from __future__ import annotations

import argparse
import os
import sys

from .audit import get_logger, new_run_id

STEP_ORDER = [
    "extract_stats19", "stage_stats19", "extract_weather", "stage_weather",
    "validate_and_clean", "transform", "build_marts", "load_warehouse", "verify_load",
]


def get_step(name: str):
    from . import extract, load, marts, quality, staging, transform
    steps = {
        "extract_stats19": extract.extract_stats19,
        "stage_stats19": staging.stage_stats19,
        "extract_weather": extract.extract_weather,
        "stage_weather": staging.stage_weather,
        "validate_and_clean": quality.validate_and_clean,
        "transform": transform.transform,
        "build_marts": marts.build_marts_step,
        "load_warehouse": load.load_warehouse,
        "verify_load": load.verify_load,
        "publish_run_log": load.load_audit_tables,
    }
    return steps[name]


def run_all(run_id: str | None = None) -> str:
    run_id = run_id or new_run_id()
    logger = get_logger()
    logger.info("=== pipeline run %s started ===", run_id)
    try:
        for name in STEP_ORDER:
            get_step(name)(run_id)
    finally:
        # Always publish the step log, including failed steps.
        try:
            get_step("publish_run_log")(run_id)
        except Exception as exc:  # pragma: no cover - logging must never mask the real error
            logger.warning("could not publish run log: %s", exc)
    logger.info("=== pipeline run %s finished successfully ===", run_id)
    return run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Traffic accident ETL pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run every step end-to-end")
    run.add_argument("--run-id")
    run.add_argument("--skip-weather", action="store_true", help="set WEATHER_ENABLED=false for this run")
    run.add_argument("--max-collisions", type=int, help="work on a reproducible sample")
    one = sub.add_parser("step", help="run a single step for an existing run id")
    one.add_argument("name", choices=[*STEP_ORDER, "publish_run_log"])
    one.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    if args.command == "run":
        if args.skip_weather:
            os.environ["WEATHER_ENABLED"] = "false"
        if args.max_collisions:
            os.environ["MAX_COLLISIONS"] = str(args.max_collisions)
        run_all(args.run_id)
    else:
        get_step(args.name)(args.run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
