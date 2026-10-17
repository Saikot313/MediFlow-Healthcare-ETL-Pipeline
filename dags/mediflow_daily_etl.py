from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor

BATCH_DATE = "{{ ds }}"


def _end_date() -> datetime | None:
    value = os.environ.get("MEDIFLOW_DAG_END_DATE", "").strip()
    return datetime.fromisoformat(value) if value else None



def _init_warehouse():
    from mediflow import pipeline
    pipeline.init_warehouse()


def _files_ready(batch_date: str) -> bool:
    from mediflow import pipeline
    return pipeline.check_source_files(batch_date)


def _extract_and_validate(batch_date: str):
    from mediflow import pipeline
    from mediflow.validate import DataQualityError
    try:
        return pipeline.extract_and_validate(batch_date)
    except DataQualityError as exc:                    
        raise AirflowFailException(str(exc)) from exc


def _load_staging(batch_date: str):
    from mediflow import pipeline
    return pipeline.load_staging(batch_date)


def _load_dimensions(batch_date: str):
    from mediflow import pipeline
    return pipeline.load_dimensions(batch_date)


def _load_facts(batch_date: str):
    from mediflow import pipeline
    return pipeline.load_facts(batch_date)


def _reconcile(batch_date: str):
    from mediflow import pipeline
    try:
        return pipeline.reconcile(batch_date)
    except pipeline.ReconciliationError as exc:
        raise AirflowFailException(str(exc)) from exc


with DAG(
    dag_id="mediflow_daily_etl",
    description="Daily healthcare ETL: CSV sources -> staging -> star-schema DWH (PostgreSQL)",
    doc_md=__doc__,
    start_date=datetime(2026, 9, 1),
    end_date=_end_date(),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    default_args={
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["healthcare", "etl", "dwh", "postgres"],
) as dag:

    init_warehouse = PythonOperator(
        task_id="init_warehouse",
        python_callable=_init_warehouse,
    )

    wait_for_source_files = PythonSensor(
        task_id="wait_for_source_files",
        python_callable=_files_ready,
        op_kwargs={"batch_date": BATCH_DATE},
        mode="reschedule",              # frees the worker slot between checks
        poke_interval=60,
        timeout=6 * 60 * 60,
    )

    extract_and_validate = PythonOperator(
        task_id="extract_and_validate",
        python_callable=_extract_and_validate,
        op_kwargs={"batch_date": BATCH_DATE},
    )

    load_staging = PythonOperator(
        task_id="load_staging",
        python_callable=_load_staging,
        op_kwargs={"batch_date": BATCH_DATE},
    )

    load_dimensions = PythonOperator(
        task_id="load_dimensions",
        python_callable=_load_dimensions,
        op_kwargs={"batch_date": BATCH_DATE},
    )

    load_facts = PythonOperator(
        task_id="load_facts",
        python_callable=_load_facts,
        op_kwargs={"batch_date": BATCH_DATE},
    )

    reconcile = PythonOperator(
        task_id="reconcile",
        python_callable=_reconcile,
        op_kwargs={"batch_date": BATCH_DATE},
    )

    (init_warehouse >> wait_for_source_files >> extract_and_validate >> load_staging
     >> load_dimensions >> load_facts >> reconcile)
