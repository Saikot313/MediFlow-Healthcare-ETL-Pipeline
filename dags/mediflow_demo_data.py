
from __future__ import annotations

from datetime import date, datetime

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator


def _generate(start_date: str, days: int):
    from mediflow.config import get_settings
    from mediflow.generate_data import generate

    s = get_settings()
    folders = generate(date.fromisoformat(start_date), int(days), s.raw_dir, s.reference_dir)
    return f"generated {len(folders)} daily batches in {s.raw_dir}"


with DAG(
    dag_id="mediflow_demo_data",
    description="Generate synthetic daily hospital source files (demo only)",
    doc_md=__doc__,
    start_date=datetime(2026, 9, 1),
    schedule=None,
    catchup=False,
    params={
        "start_date": Param("2026-09-01", type="string", description="First batch date"),
        "days": Param(14, type="integer", minimum=1, maximum=60),
    },
    tags=["healthcare", "demo"],
) as dag:
    PythonOperator(
        task_id="generate_demo_files",
        python_callable=_generate,
        op_kwargs={"start_date": "{{ params.start_date }}", "days": "{{ params.days }}"},
    )
