"""Airflow DAG: monthly refresh of the traffic accident warehouse.

Each task calls one step of the `traffic_pipeline` package with the same
run id ({{ ts_nodash }}Z), so tasks share data through the layered folders
(raw -> staging -> cleaned -> analytics) instead of XCom. Re-running a task
for the same logical date is idempotent.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

from traffic_pipeline.cli import get_step

RUN_ID = "{{ ts_nodash }}Z"

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


def _run(step_name: str, run_id: str) -> None:
    get_step(step_name)(run_id)


with DAG(
    dag_id="traffic_accident_etl",
    description="STATS19 + Open-Meteo -> PostgreSQL/PostGIS accident warehouse",
    default_args=default_args,
    start_date=datetime(2026, 8, 1),
    schedule="0 2 1 * *",  # 02:00 on the 1st of every month
    catchup=False,
    max_active_runs=1,
    tags=["project4", "etl", "road-safety"],
) as dag:

    def task(step_name: str, **kwargs) -> PythonOperator:
        return PythonOperator(task_id=step_name, python_callable=_run,
                              op_kwargs={"step_name": step_name, "run_id": RUN_ID}, **kwargs)

    extract_stats19 = task("extract_stats19")
    stage_stats19 = task("stage_stats19")
    extract_weather = task("extract_weather", retries=3, retry_delay=timedelta(minutes=30))
    stage_weather = task("stage_weather")
    validate = task("validate_and_clean")
    transform = task("transform")
    marts = task("build_marts")
    load = task("load_warehouse")
    verify = task("verify_load")
    publish_log = task("publish_run_log", trigger_rule=TriggerRule.ALL_DONE)

    extract_stats19 >> stage_stats19 >> extract_weather >> stage_weather >> validate
    validate >> transform >> marts >> load >> verify >> publish_log
