from pathlib import Path

import pytest

pytest.importorskip("airflow")
from airflow.models import DagBag  # noqa: E402

DAGS = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="module")
def dagbag():
    return DagBag(dag_folder=str(DAGS), include_examples=False)


def test_dags_import_without_errors(dagbag):
    assert dagbag.import_errors == {}
    assert {"mediflow_daily_etl", "mediflow_demo_data"} <= set(dagbag.dag_ids)


def test_etl_dag_runs_steps_in_order(dagbag):
    dag = dagbag.dags["mediflow_daily_etl"]
    order = ["init_warehouse", "wait_for_source_files", "extract_and_validate",
             "load_staging", "load_dimensions", "load_facts", "reconcile"]
    assert [t.task_id for t in dag.topological_sort()] == order


def test_etl_dag_is_safe_for_scd2_and_backfills(dagbag):
    dag = dagbag.dags["mediflow_daily_etl"]
    assert dag.max_active_runs == 1          # SCD2 history must be applied chronologically
    assert dag.catchup is True
    assert dag.default_args["retries"] >= 1
    assert dag.get_task("wait_for_source_files").mode == "reschedule"


def test_demo_data_dag_is_manual_only(dagbag):
    dag = dagbag.dags["mediflow_demo_data"]
    assert dag.schedule_interval is None
    assert set(dag.params) == {"start_date", "days"}


def test_end_date_comes_from_environment(monkeypatch):
    import importlib.util

    monkeypatch.setenv("MEDIFLOW_DAG_END_DATE", "2026-09-14")
    spec = importlib.util.spec_from_file_location("etl_dag_probe", DAGS / "mediflow_daily_etl.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.dag.end_date.date().isoformat() == "2026-09-14"

    monkeypatch.setenv("MEDIFLOW_DAG_END_DATE", "")
    spec.loader.exec_module(module)
    assert module.dag.end_date is None
