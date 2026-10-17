import os
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import text

TEST_URL = os.environ.get("MEDIFLOW_TEST_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="MEDIFLOW_TEST_URL not set")

START = date(2026, 9, 1)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    from mediflow import pipeline
    from mediflow.db import get_engine
    from mediflow.generate_data import generate

    root = tmp_path_factory.mktemp("mediflow")
    mp = pytest.MonkeyPatch()
    mp.setenv("MEDIFLOW_WAREHOUSE_URL", TEST_URL)
    mp.setenv("MEDIFLOW_DATA_DIR", str(root))
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS staging, dwh, audit, mart CASCADE"))
    generate(START, 4, root / "raw", root / "reference", n_patients=300)
    pipeline.backfill(START, START + timedelta(days=3), engine)
    yield engine, root, pipeline
    mp.undo()


def scalar(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def test_facts_loaded_and_reconciled(env):
    engine, _, _ = env
    assert scalar(engine, "SELECT count(*) FROM dwh.fact_visits") > 300
    assert scalar(engine, "SELECT count(*) FROM dwh.fact_lab_tests") > 50
    failed = scalar(engine, "SELECT count(*) FROM audit.dq_results "
                            "WHERE table_name = 'reconcile' AND NOT passed")
    assert failed == 0


def test_bad_rows_are_quarantined_not_loaded(env):
    engine, _, _ = env
    assert scalar(engine, "SELECT count(*) FROM audit.rejected_rows") > 0
    assert scalar(engine, "SELECT count(*) FROM dwh.fact_visits WHERE consultation_fee < 0") == 0


def test_scd2_history_is_contiguous_and_single_current(env):
    engine, _, _ = env
    assert scalar(engine, "SELECT count(*) FROM dwh.dim_patient WHERE valid_from >= valid_to") == 0
    assert scalar(engine, """
        SELECT count(*) FROM (SELECT patient_id FROM dwh.dim_patient GROUP BY patient_id
                              HAVING count(*) FILTER (WHERE is_current) <> 1) x""") == 0
    assert scalar(engine, """
        SELECT count(*) FROM (
            SELECT valid_to, lead(valid_from) OVER (PARTITION BY patient_id ORDER BY valid_from) nxt
            FROM dwh.dim_patient) t WHERE nxt IS NOT NULL AND nxt <> valid_to""") == 0
    assert scalar(engine, "SELECT count(*) FROM (SELECT patient_id FROM dwh.dim_patient "
                          "GROUP BY 1 HAVING count(*) > 1) x") > 0      # history really exists


def test_visits_point_to_the_patient_version_valid_on_the_visit_date(env):
    engine, _, _ = env
    assert scalar(engine, """
        SELECT count(*) FROM dwh.fact_visits f JOIN dwh.dim_patient p USING (patient_key)
        WHERE f.visit_ts::date < p.valid_from OR f.visit_ts::date >= p.valid_to""") == 0


def test_rerunning_every_day_changes_nothing(env):
    engine, _, pipeline = env
    snap = """SELECT (SELECT count(*) FROM dwh.fact_visits) || '/' ||
                     (SELECT count(*) FROM dwh.fact_lab_tests) || '/' ||
                     (SELECT count(*) FROM dwh.dim_patient) || '/' ||
                     (SELECT coalesce(sum(net_amount), 0) FROM dwh.fact_visits)"""
    before = scalar(engine, snap)
    pipeline.backfill(START, START + timedelta(days=3), engine)     # includes OLD days
    assert scalar(engine, snap) == before


def test_too_dirty_batch_fails_and_loads_nothing(env):
    from mediflow.validate import DataQualityError
    engine, root, pipeline = env
    day = START + timedelta(days=4)
    folder = root / "raw" / day.isoformat()
    folder.mkdir(parents=True)
    src = root / "raw" / START.isoformat()
    for name in ("patients", "doctors", "lab_tests"):
        pd.read_csv(src / f"{name}.csv", dtype=str).head(0).to_csv(folder / f"{name}.csv", index=False)
    visits = pd.read_csv(src / "visits.csv", dtype=str).head(50)
    visits["visit_id"] = [f"V{day:%Y%m%d}-{i:04d}" for i in range(len(visits))]
    visits["visit_ts"] = f"{day} 10:00:00"
    visits["patient_id"] = "P999999"                                 # every row is an orphan
    visits.to_csv(folder / "visits.csv", index=False)

    before = scalar(engine, "SELECT count(*) FROM dwh.fact_visits")
    with pytest.raises(DataQualityError):
        pipeline.extract_and_validate(day, engine)
    assert scalar(engine, "SELECT count(*) FROM dwh.fact_visits") == before
    assert scalar(engine, "SELECT count(*) FROM audit.rejected_rows WHERE batch_date = :d",
                  d=day) == 50                                       # evidence is kept
    assert scalar(engine, "SELECT status FROM audit.etl_run_log WHERE batch_date = :d "
                          "ORDER BY run_id DESC LIMIT 1", d=day) == "failed"


def _late_resolved_orders(engine, root):
    """Day-1 orders that were still pending and were re-sent (resulted) on day 2."""
    raw1 = pd.read_csv(root / "raw" / START.isoformat() / "lab_tests.csv", dtype=str)
    raw2 = pd.read_csv(root / "raw" / (START + timedelta(days=1)).isoformat() / "lab_tests.csv",
                       dtype=str)
    pending = set(raw1.loc[raw1["resulted_at"].isna(), "lab_order_id"])
    resent = sorted(pending & set(raw2["lab_order_id"]))
    with engine.connect() as c:
        return c.execute(text(
            "SELECT lab_order_id, count(*) AS n, max(result_flag) AS flag, "
            "max(turnaround_minutes) AS tat, max(batch_date) AS batch "
            "FROM dwh.fact_lab_tests WHERE lab_order_id = ANY(:ids) GROUP BY 1"),
            {"ids": resent}).fetchall()


def test_late_lab_results_complete_the_existing_order_instead_of_duplicating(env):
    engine, root, _ = env
    rows = _late_resolved_orders(engine, root)
    assert rows, "generator should produce late results"
    for lab_order_id, n, flag, tat, batch in rows:
        assert n == 1, lab_order_id
        assert flag != "Pending" and tat is not None and tat > 0
        assert batch == START + timedelta(days=1)          # last written by the day-2 batch


def test_rerunning_an_old_day_does_not_revert_newer_data(env):
    engine, root, pipeline = env
    before = _late_resolved_orders(engine, root)
    pipeline.run_batch(START, engine)          # day 1 still contains the PENDING versions
    assert _late_resolved_orders(engine, root) == before
    assert scalar(engine, "SELECT count(*) FROM audit.dq_results "
                          "WHERE batch_date = :d AND table_name = 'reconcile' AND NOT passed",
                  d=START) == 0


def test_old_rerun_does_not_revert_a_newer_doctor_change(env):
    engine, _, pipeline = env
    original = scalar(engine, "SELECT department FROM dwh.dim_doctor WHERE doctor_id = 'D001'")
    with engine.begin() as c:                  # pretend day 4 moved doctor D001 to another dept
        c.execute(text("UPDATE dwh.dim_doctor SET department = 'Palliative Care', batch_date = :d "
                       "WHERE doctor_id = 'D001'"), {"d": START + timedelta(days=3)})
    pipeline.run_batch(START, engine)          # the day-1 roster still lists the old department
    assert scalar(engine, "SELECT department FROM dwh.dim_doctor "
                          "WHERE doctor_id = 'D001'") == "Palliative Care"
    with engine.begin() as c:                  # same-day rerun is allowed to (re)apply its data
        c.execute(text("UPDATE dwh.dim_doctor SET batch_date = :d WHERE doctor_id = 'D001'"),
                  {"d": START})
    pipeline.run_batch(START, engine)
    assert scalar(engine, "SELECT department FROM dwh.dim_doctor "
                          "WHERE doctor_id = 'D001'") == original


def test_reconcile_detects_a_row_missing_from_the_warehouse_and_heals(env):
    engine, _, pipeline = env
    day = START + timedelta(days=1)
    with engine.begin() as c:
        c.execute(text(
            "DELETE FROM dwh.fact_lab_tests WHERE lab_order_id = "
            "(SELECT lab_order_id FROM dwh.fact_lab_tests WHERE batch_date = :d "
            "ORDER BY lab_order_id LIMIT 1)"), {"d": day})
    with pytest.raises(pipeline.ReconciliationError, match="lab_orders_staged_but_missing_in_fact"):
        pipeline.reconcile(day, engine)
    pipeline.load_facts(day, engine)           # re-running the load repairs the gap
    pipeline.reconcile(day, engine)


def _as_bi_reader(engine):
    from contextlib import contextmanager

    from sqlalchemy.exc import DBAPIError

    @contextmanager
    def ctx():
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text("SET LOCAL ROLE bi_reader"))
            except DBAPIError:
                trans.rollback()
                pytest.skip("test user cannot assume the bi_reader role")
            try:
                yield conn
            finally:
                trans.rollback()
    return ctx()


def test_bi_reader_sees_the_mart_but_never_patient_pii(env):
    from sqlalchemy.exc import DBAPIError

    engine, _, _ = env
    with _as_bi_reader(engine) as conn:
        assert conn.execute(text("SELECT count(*) FROM mart.fact_visits")).scalar() > 0
        assert conn.execute(text("SELECT count(*) FROM mart.v_daily_visits")).scalar() > 0
        cols = set(conn.execute(text("SELECT * FROM mart.dim_patient LIMIT 1")).keys())
        assert {"patient_token", "age_band", "city"} <= cols
        assert not cols & {"full_name", "date_of_birth", "patient_id"}
    for forbidden in ("dwh.dim_patient", "dwh.fact_visits", "staging.patients",
                      "audit.rejected_rows"):
        with _as_bi_reader(engine) as conn, pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text(f"SELECT 1 FROM {forbidden} LIMIT 1"))


def test_every_documented_sample_query_runs(env):
    from pathlib import Path

    engine, _, _ = env
    sql = (Path(__file__).resolve().parents[1] / "docs" / "sample_queries.sql").read_text()
    statements = [chunk.strip() for chunk in sql.split(";")
                  if any(line.strip() and not line.strip().startswith("--")
                         for line in chunk.splitlines())]
    assert len(statements) >= 6
    with engine.connect() as conn:
        for stmt in statements:
            conn.exec_driver_sql(stmt).fetchall()
