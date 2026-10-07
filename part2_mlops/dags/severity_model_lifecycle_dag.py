"""Airflow DAG: weekly monitoring + conditional retraining of the severity model.

Runs after the Part 1 ETL has refreshed `ml_accident_features`.
  monitor  -> builds the drift / performance report and decides
  branch   -> retrain only when the retraining policy is triggered
  retrain  -> train candidates, register, champion/challenger promotion
Deploy this file to the Part 1 Airflow `dags/` folder (with `part2_mlops/src`
on PYTHONPATH) to orchestrate both parts from one scheduler.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator


def _monitor(**_):
    from severity_model.monitoring import main
    main([])  # labelled data newer than the training window vs. the champion's reference profile


def _decide(**_):
    from severity_model.config import get_settings
    report = json.loads((get_settings().reports_dir / "latest_monitoring.json").read_text())
    return "retrain" if report["retraining"]["required"] else "no_retraining_needed"


def _retrain(**_):
    from severity_model.train import run_training
    run_training()


with DAG(
    dag_id="severity_model_lifecycle",
    start_date=datetime(2026, 9, 1),
    schedule="0 6 * * 1",  # Mondays 06:00
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=10)},
    tags=["project4", "mlops"],
) as dag:
    monitor = PythonOperator(task_id="monitor", python_callable=_monitor)
    decide = BranchPythonOperator(task_id="decide", python_callable=_decide)
    retrain = PythonOperator(task_id="retrain", python_callable=_retrain)
    skip = EmptyOperator(task_id="no_retraining_needed")
    monitor >> decide >> [retrain, skip]
