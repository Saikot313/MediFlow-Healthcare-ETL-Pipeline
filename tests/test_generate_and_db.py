from datetime import date

import pandas as pd

from mediflow.db import split_blocks
from mediflow.generate_data import generate


def test_generator_is_deterministic_and_complete(tmp_path):
    a = generate(date(2026, 9, 1), 3, tmp_path / "a", tmp_path / "ref_a", seed=7, n_patients=200)
    b = generate(date(2026, 9, 1), 3, tmp_path / "b", tmp_path / "ref_b", seed=7, n_patients=200)
    for fa, fb in zip(a, b):
        for name in ("patients", "doctors", "visits", "lab_tests"):
            assert (fa / f"{name}.csv").read_text() == (fb / f"{name}.csv").read_text()
    assert len(pd.read_csv(a[0] / "patients.csv")) == 200          # full load on day 1
    assert len(pd.read_csv(a[1] / "patients.csv")) < 200           # deltas afterwards
    assert (tmp_path / "ref_a" / "lab_catalog.csv").exists()


def test_generator_injects_dirty_rows_only_when_asked(tmp_path):
    clean = generate(date(2026, 9, 1), 1, tmp_path / "c", tmp_path / "rc", n_patients=100,
                     dirty_rate=0.0)
    visits = pd.read_csv(clean[0] / "visits.csv", dtype=str)
    assert not visits["visit_id"].duplicated().any()
    assert (visits["consultation_fee"].astype(float) >= 0).all()


def test_split_blocks_ignores_trailing_marker_comment():
    sql = "-- header\n-- @@ first   (some note)\nSELECT 1;\n\n-- @@ second\nSELECT 2;\n"
    assert split_blocks(sql) == [("first", "SELECT 1;"), ("second", "SELECT 2;")]


def test_check_source_files_needs_daily_and_reference_files(tmp_path, monkeypatch):
    from mediflow import pipeline

    monkeypatch.setenv("MEDIFLOW_DATA_DIR", str(tmp_path))
    assert pipeline.check_source_files("2026-09-01") is False          # nothing there yet
    generate(date(2026, 9, 1), 1, tmp_path / "raw", tmp_path / "reference", n_patients=50)
    assert pipeline.check_source_files("2026-09-01") is True
    (tmp_path / "reference" / "lab_catalog.csv").unlink()
    assert pipeline.check_source_files("2026-09-01") is False          # reference data missing
    (tmp_path / "reference").joinpath("lab_catalog.csv").write_text("x")
    (tmp_path / "raw" / "2026-09-01" / "visits.csv").unlink()
    assert pipeline.check_source_files("2026-09-01") is False          # a daily file missing


def test_pending_lab_orders_are_resent_with_results_the_next_day(tmp_path):
    folders = generate(date(2026, 9, 1), 3, tmp_path / "raw", tmp_path / "ref", n_patients=300)
    day1 = pd.read_csv(folders[0] / "lab_tests.csv", dtype=str)
    day2 = pd.read_csv(folders[1] / "lab_tests.csv", dtype=str)
    pending = set(day1.loc[day1["resulted_at"].isna(), "lab_order_id"])
    resent = day2[day2["lab_order_id"].isin(pending)]
    assert len(pending) > 0 and len(resent) == len(pending)
    assert resent["resulted_at"].notna().all() and resent["result_value"].notna().all()
