from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from . import validate as V
from .config import get_settings
from .db import copy_dataframe, get_engine, log_step, run_blocks, run_sql_script
from .transform import SCHEMAS, read_csv_raw

log = logging.getLogger("mediflow.pipeline")

TABLES = ("patients", "doctors", "visits", "lab_tests")
REFERENCE_FILES = ("lab_catalog.csv", "diagnoses.csv")
STAGING_COLUMNS = {
    "patients": SCHEMAS["patients"],
    "doctors": SCHEMAS["doctors"],
    "visits": SCHEMAS["visits"] + ["net_amount"],
    "lab_tests": SCHEMAS["lab_tests"],
}


class ReconciliationError(Exception):
    """Raised when staging and warehouse row counts / totals do not agree."""


def as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])



def init_warehouse(engine=None) -> None:
    """Create schemas, tables and views (idempotent)."""
    engine = engine or get_engine()
    for path in sorted(get_settings().sql_dir.glob("0*.sql")):
        run_sql_script(engine, path)


def check_source_files(batch_date) -> bool:
    s = get_settings()
    folder = s.raw_dir / as_date(batch_date).isoformat()
    missing = [f"{t}.csv" for t in TABLES if not (folder / f"{t}.csv").exists()]
    missing += [f"reference/{f}" for f in REFERENCE_FILES if not (s.reference_dir / f).exists()]
    if missing:
        log.info("batch %s: waiting for %s", batch_date, missing)
    return not missing


def _known_ids(engine, batch_date: date) -> V.KnownIds:
    s = get_settings()
    with engine.connect() as conn:
        patients = {r[0] for r in conn.execute(text("SELECT DISTINCT patient_id FROM dwh.dim_patient"))}
        doctors = {r[0] for r in conn.execute(text("SELECT doctor_id FROM dwh.dim_doctor"))}
        visits = {r[0] for r in conn.execute(
            text("SELECT visit_id FROM dwh.fact_visits WHERE batch_date >= :d"),
            {"d": batch_date - timedelta(days=30)})}
    tests = set(pd.read_csv(s.reference_dir / "lab_catalog.csv", dtype=str)["test_code"])
    dx = set(pd.read_csv(s.reference_dir / "diagnoses.csv", dtype=str)["diagnosis_code"])
    return V.KnownIds(patients, doctors, visits, tests, dx)


def extract_and_validate(batch_date, engine=None) -> dict:
    engine = engine or get_engine()
    s = get_settings()
    d = as_date(batch_date)
    raw_folder = s.raw_dir / d.isoformat()
    with log_step(engine, d, "extract_and_validate") as stats:
        raw = {t: read_csv_raw(raw_folder / f"{t}.csv") for t in TABLES}
        raw_counts = {t: len(df) for t, df in raw.items()}
        outcome = V.validate_batch(raw, d, _known_ids(engine, d))

        clean_folder = s.clean_dir / d.isoformat()
        rej_folder = s.rejected_dir / d.isoformat()
        clean_folder.mkdir(parents=True, exist_ok=True)
        rej_folder.mkdir(parents=True, exist_ok=True)
        for t in TABLES:
            outcome.clean[t][STAGING_COLUMNS[t]].to_csv(clean_folder / f"{t}.csv", index=False)
            outcome.rejected[t].to_csv(rej_folder / f"{t}_rejected.csv", index=False)

        _persist_audit(engine, d, outcome)          # evidence is saved BEFORE any failure
        V.enforce_thresholds(outcome, raw_counts, s.max_reject_ratio)

        stats.rows_in = sum(raw_counts.values())
        stats.rows_out = sum(len(df) for df in outcome.clean.values())
        stats.rows_rejected = sum(len(df) for df in outcome.rejected.values())
        stats.message = "; ".join(f"{t}: {len(outcome.rejected[t])}/{raw_counts[t]} rejected"
                                  for t in TABLES)
    log.info("validated %s: %s in, %s clean, %s rejected", d, stats.rows_in, stats.rows_out,
             stats.rows_rejected)
    return {"rows_in": stats.rows_in, "rows_clean": stats.rows_out,
            "rows_rejected": stats.rows_rejected}


def _persist_audit(engine, d: date, outcome: V.ValidationOutcome) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit.dq_results WHERE batch_date = :d "
                          "AND table_name <> 'reconcile'"), {"d": d})
        conn.execute(text("DELETE FROM audit.rejected_rows WHERE batch_date = :d"), {"d": d})
        if outcome.results:
            conn.execute(
                text("INSERT INTO audit.dq_results (batch_date, table_name, check_name, severity, "
                     "failed_rows, total_rows, passed) VALUES (:d, :t, :c, :s, :f, :n, :p)"),
                [{"d": d, "t": r.table, "c": r.check, "s": r.severity, "f": r.failed,
                  "n": r.total, "p": r.passed} for r in outcome.results])
        rows = []
        for table, df in outcome.rejected.items():
            for rec in df.to_dict(orient="records"):
                reasons = rec.pop("reject_reasons", "")
                rec = {k: (None if pd.isna(v) else v) for k, v in rec.items()}  # NaN is not JSON
                rows.append({"d": d, "t": table, "r": reasons,
                             "j": json.dumps(rec, default=str)})
        if rows:
            conn.execute(
                text("INSERT INTO audit.rejected_rows (batch_date, table_name, reasons, row_data) "
                     "VALUES (:d, :t, :r, CAST(:j AS jsonb))"), rows)


def load_staging(batch_date, engine=None) -> dict:
    engine = engine or get_engine()
    s = get_settings()
    d = as_date(batch_date)
    loaded: dict[str, int] = {}
    with log_step(engine, d, "load_staging") as stats:
        with engine.begin() as conn:
            for t in TABLES:
                df = pd.read_csv(s.clean_dir / d.isoformat() / f"{t}.csv", dtype=str,
                                 keep_default_na=False, na_values=[""])
                df["_batch_date"] = d.isoformat()
                conn.execute(text(f"DELETE FROM staging.{t} WHERE _batch_date = :d"), {"d": d})
                loaded[t] = copy_dataframe(conn, df, f"staging.{t}",
                                           STAGING_COLUMNS[t] + ["_batch_date"])
            for name, table in (("lab_catalog.csv", "staging.ref_lab_catalog"),
                                ("diagnoses.csv", "staging.ref_diagnoses")):
                ref = pd.read_csv(s.reference_dir / name, dtype=str,
                                  keep_default_na=False, na_values=[""])
                conn.execute(text(f"TRUNCATE {table}"))
                copy_dataframe(conn, ref, table, list(ref.columns))
        stats.rows_out = sum(loaded.values())
        stats.message = str(loaded)
    return loaded


def load_dimensions(batch_date, engine=None) -> dict:
    engine = engine or get_engine()
    d = as_date(batch_date)
    with log_step(engine, d, "load_dimensions") as stats:
        counts = run_blocks(engine, get_settings().sql_dir / "10_load_dimensions.sql",
                            {"batch_date": d})
        stats.rows_out = sum(counts.values())
        stats.message = str(counts)
    return counts


def load_facts(batch_date, engine=None) -> dict:
    engine = engine or get_engine()
    d = as_date(batch_date)
    with log_step(engine, d, "load_facts") as stats:
        counts = run_blocks(engine, get_settings().sql_dir / "20_load_facts.sql",
                            {"batch_date": d})
        stats.rows_out = sum(counts.values())
        stats.message = str(counts)
    return counts

_RECONCILE_CHECKS = {
    "visits_staged_but_missing_in_fact": (
        "SELECT count(*) FROM staging.visits s WHERE s._batch_date = :d "
        "AND NOT EXISTS (SELECT 1 FROM dwh.fact_visits f WHERE f.visit_id = s.visit_id)"),
    "visits_in_fact_but_not_staged": (
        "SELECT count(*) FROM dwh.fact_visits f WHERE f.batch_date = :d "
        "AND NOT EXISTS (SELECT 1 FROM staging.visits s "
        "WHERE s._batch_date = :d AND s.visit_id = f.visit_id)"),
    "visit_net_amount_mismatch": (
        "SELECT count(*) FROM staging.visits s JOIN dwh.fact_visits f ON f.visit_id = s.visit_id "
        "WHERE s._batch_date = :d AND f.batch_date = :d AND f.net_amount <> s.net_amount"),
    "lab_orders_staged_but_missing_in_fact": (
        "SELECT count(*) FROM staging.lab_tests s WHERE s._batch_date = :d "
        "AND NOT EXISTS (SELECT 1 FROM dwh.fact_lab_tests f WHERE f.lab_order_id = s.lab_order_id)"),
    "lab_orders_in_fact_but_not_staged": (
        "SELECT count(*) FROM dwh.fact_lab_tests f WHERE f.batch_date = :d "
        "AND NOT EXISTS (SELECT 1 FROM staging.lab_tests s "
        "WHERE s._batch_date = :d AND s.lab_order_id = f.lab_order_id)"),
    "lab_price_mismatch": (
        "SELECT count(*) FROM staging.lab_tests s "
        "JOIN dwh.fact_lab_tests f ON f.lab_order_id = s.lab_order_id "
        "WHERE s._batch_date = :d AND f.batch_date = :d AND f.test_price <> s.test_price"),
    "patients_without_single_current_version": (
        "SELECT count(*) FROM (SELECT patient_id FROM dwh.dim_patient GROUP BY patient_id "
        "HAVING count(*) FILTER (WHERE is_current) <> 1) x"),
    "patient_versions_with_bad_dates": (
        "SELECT count(*) FROM dwh.dim_patient WHERE valid_from >= valid_to"),
    "patient_version_gaps_or_overlaps": (
        "SELECT count(*) FROM (SELECT valid_to, lead(valid_from) OVER "
        "(PARTITION BY patient_id ORDER BY valid_from) AS next_from FROM dwh.dim_patient) t "
        "WHERE next_from IS NOT NULL AND next_from <> valid_to"),
}

def reconcile(batch_date, engine=None) -> dict:
    """Prove the warehouse agrees with what was staged. Raises if anything differs."""
    engine = engine or get_engine()
    d = as_date(batch_date)
    with log_step(engine, d, "reconcile") as stats:
        results = {}
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM audit.dq_results WHERE batch_date = :d "
                              "AND table_name = 'reconcile'"), {"d": d})
            for name, sql in _RECONCILE_CHECKS.items():
                diff = int(conn.execute(text(sql), {"d": d}).scalar() or 0)
                results[name] = diff
                conn.execute(
                    text("INSERT INTO audit.dq_results (batch_date, table_name, check_name, "
                         "severity, failed_rows, total_rows, passed) "
                         "VALUES (:d, 'reconcile', :c, 'fail', :f, 0, :p)"),
                    {"d": d, "c": name, "f": abs(diff), "p": diff == 0})
        bad = {k: v for k, v in results.items() if v != 0}
        stats.message = "all checks passed" if not bad else f"FAILED: {bad}"
        if bad:
            raise ReconciliationError(f"Reconciliation failed for {d}: {bad}")
    return results



def run_batch(batch_date, engine=None) -> dict:
    """Run every step for one date (used by the CLI)."""
    engine = engine or get_engine()
    d = as_date(batch_date)
    if not check_source_files(d):
        raise FileNotFoundError(f"Source files for {d} are not all present")
    summary = {"batch_date": d.isoformat()}
    summary["validate"] = extract_and_validate(d, engine)
    summary["staging"] = load_staging(d, engine)
    summary["dimensions"] = load_dimensions(d, engine)
    summary["facts"] = load_facts(d, engine)
    summary["reconcile"] = reconcile(d, engine)
    return summary


def backfill(start, end, engine=None) -> list[dict]:
    """Run consecutive dates in order (SCD2 history needs chronological order)."""
    engine = engine or get_engine()
    init_warehouse(engine)
    out = []
    d, last = as_date(start), as_date(end)
    while d <= last:
        out.append(run_batch(d, engine))
        d += timedelta(days=1)
    return out
