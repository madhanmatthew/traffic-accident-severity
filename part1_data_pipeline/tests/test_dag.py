from pathlib import Path

import pytest

from traffic_pipeline.cli import STEP_ORDER, get_step


def test_every_cli_step_is_callable():
    for name in [*STEP_ORDER, "publish_run_log"]:
        assert callable(get_step(name))


def test_dag_structure():
    pytest.importorskip("airflow")
    from airflow.models import DagBag

    bag = DagBag(dag_folder=str(Path(__file__).resolve().parents[1] / "dags"), include_examples=False)
    assert not bag.import_errors
    dag = bag.get_dag("traffic_accident_etl")
    assert set(STEP_ORDER) <= set(dag.task_ids)
