from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from .transform import SCHEMAS, parse_num, parse_ts, standardize, to_typed

GENDERS = {"M", "F", "O"}
INSURANCE_TYPES = {"None", "Basic", "Premium", "Corporate"}
VISIT_STATUSES = {"Completed", "Cancelled", "No-Show"}
VISIT_TYPES = {"OPD", "Emergency", "Follow-up", "Telemedicine"}


class DataQualityError(Exception):
    """Raised when a batch is too dirty to load (schema break or reject ratio exceeded)."""


@dataclass
class DQResult:
    table: str
    check: str
    severity: str
    failed: int
    total: int

    @property
    def passed(self) -> bool:
        return self.failed == 0


@dataclass
class KnownIds:
    """Keys that already exist in the warehouse (or reference data)."""
    patient_ids: set = field(default_factory=set)
    doctor_ids: set = field(default_factory=set)
    visit_ids: set = field(default_factory=set)
    test_codes: set = field(default_factory=set)
    diagnosis_codes: set = field(default_factory=set)


@dataclass
class ValidationOutcome:
    clean: dict[str, pd.DataFrame]
    rejected: dict[str, pd.DataFrame]
    results: list[DQResult]


class _Checker:
    def __init__(self, table: str, df: pd.DataFrame):
        self.table = table
        self.df = df
        self.results: list[DQResult] = []
        self._reject = pd.Series(False, index=df.index)
        self._reasons = pd.Series("", index=df.index, dtype="object")

    def check(self, name: str, bad: pd.Series, severity: str = "reject") -> None:
        bad = bad.fillna(False).astype(bool)
        self.results.append(
            DQResult(self.table, name, severity, int(bad.sum()), len(self.df))
        )
        if severity == "reject" and bad.any():
            self._reject |= bad
            self._reasons.loc[bad] = self._reasons.loc[bad] + name + ";"

    def dedupe(self, name: str, key: str, keep: str) -> None:
        alive = ~self._reject & self.df[key].notna()
        dup = pd.Series(False, index=self.df.index)
        if alive.any():
            dup.loc[alive] = self.df.loc[alive].duplicated(key, keep=keep)
        self.check(name, dup)

    def split(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        clean = self.df.loc[~self._reject]
        rejected = self.df.loc[self._reject].copy()
        rejected["reject_reasons"] = self._reasons.loc[self._reject].str.rstrip(";")
        return clean, rejected


def _check_schema(table: str, df: pd.DataFrame) -> None:
    missing = [c for c in SCHEMAS[table] if c not in df.columns]
    if missing:
        raise DataQualityError(f"{table}: missing required column(s) {missing}")


def _validate_patients(df, batch_date, known: KnownIds):
    c = _Checker("patients", df)
    dob = parse_ts(df["date_of_birth"])
    c.check("patient_id_not_null", df["patient_id"].isna())
    c.check("full_name_not_null", df["full_name"].isna())
    c.check("gender_valid", ~df["gender"].isin(GENDERS))
    c.check("dob_parseable", dob.isna())
    c.check("dob_not_in_future", dob > pd.Timestamp(batch_date))
    c.check("age_at_most_120",
            dob < pd.Timestamp(batch_date - timedelta(days=120 * 366)))
    c.check("insurance_type_valid", ~df["insurance_type"].isin(INSURANCE_TYPES))
    c.check("registered_date_parseable", parse_ts(df["registered_date"]).isna())
    c.check("city_missing", df["city"].isna(), severity="warn")
    c.dedupe("duplicate_patient_id", "patient_id", keep="last")   # newest valid state wins
    return c


def _validate_doctors(df, batch_date, known: KnownIds):
    c = _Checker("doctors", df)
    c.check("doctor_id_not_null", df["doctor_id"].isna())
    c.check("full_name_not_null", df["full_name"].isna())
    c.check("department_not_null", df["department"].isna())
    c.check("is_active_valid", ~df["is_active"].isin([True, False]))
    c.dedupe("duplicate_doctor_id", "doctor_id", keep="last")
    return c


def _validate_visits(df, batch_date, known: KnownIds):
    c = _Checker("visits", df)
    ts = parse_ts(df["visit_ts"])
    fee = parse_num(df["consultation_fee"])
    disc = parse_num(df["discount"])
    c.check("visit_id_not_null", df["visit_id"].isna())
    c.check("patient_id_not_null", df["patient_id"].isna())
    c.check("patient_fk_unknown", df["patient_id"].notna()
            & ~df["patient_id"].isin(known.patient_ids))
    c.check("doctor_id_not_null", df["doctor_id"].isna())
    c.check("doctor_fk_unknown", df["doctor_id"].notna()
            & ~df["doctor_id"].isin(known.doctor_ids))
    c.check("visit_ts_parseable", ts.isna())
    c.check("visit_date_outside_batch",
            ts.notna() & (ts.dt.normalize() != pd.Timestamp(batch_date)))
    c.check("fee_invalid", fee.isna() | (fee < 0))
    c.check("discount_invalid", (df["discount"].notna() & disc.isna())
            | (disc < 0) | (disc > fee))
    c.check("status_invalid", ~df["status"].isin(VISIT_STATUSES))
    c.check("visit_type_invalid", ~df["visit_type"].isin(VISIT_TYPES))
    c.check("diagnosis_code_unknown", df["diagnosis_code"].notna()
            & ~df["diagnosis_code"].isin(known.diagnosis_codes), severity="warn")
    c.dedupe("duplicate_visit_id", "visit_id", keep="first")
    return c


def _validate_labs(df, batch_date, known: KnownIds):
    c = _Checker("lab_tests", df)
    ordered = parse_ts(df["ordered_at"])
    resulted = parse_ts(df["resulted_at"])
    value = parse_num(df["result_value"])
    price = parse_num(df["test_price"])
    c.check("lab_order_id_not_null", df["lab_order_id"].isna())
    c.check("visit_id_not_null", df["visit_id"].isna())
    c.check("visit_fk_unknown", df["visit_id"].notna() & ~df["visit_id"].isin(known.visit_ids))
    c.check("test_code_unknown", ~df["test_code"].isin(known.test_codes))
    c.check("ordered_at_parseable", ordered.isna())
    c.check("resulted_at_unparseable", df["resulted_at"].notna() & resulted.isna())
    c.check("resulted_before_ordered", resulted.notna() & ordered.notna() & (resulted < ordered))
    c.check("result_value_not_numeric", df["result_value"].notna() & value.isna())
    c.check("test_price_invalid", price.isna() | (price < 0))
    c.dedupe("duplicate_lab_order_id", "lab_order_id", keep="first")
    return c


_RULES = {
    "patients": _validate_patients,
    "doctors": _validate_doctors,
    "visits": _validate_visits,
    "lab_tests": _validate_labs,
}


def validate_batch(raw: dict[str, pd.DataFrame], batch_date: date,
                   known: KnownIds) -> ValidationOutcome:
    known = KnownIds(set(known.patient_ids), set(known.doctor_ids), set(known.visit_ids),
                     set(known.test_codes), set(known.diagnosis_codes))
    clean: dict[str, pd.DataFrame] = {}
    rejected: dict[str, pd.DataFrame] = {}
    results: list[DQResult] = []

    for table in ("patients", "doctors", "visits", "lab_tests"):
        df = raw[table]
        _check_schema(table, df)
        df = standardize(table, df[SCHEMAS[table]])
        checker = _RULES[table](df, batch_date, known)
        ok, bad = checker.split()
        clean[table] = to_typed(table, ok).reset_index(drop=True)
        rejected[table] = bad.reset_index(drop=True)
        results.extend(checker.results)

        # make this batch's good parents visible to its children
        if table == "patients":
            known.patient_ids |= set(clean[table]["patient_id"])
        elif table == "doctors":
            known.doctor_ids |= set(clean[table]["doctor_id"])
        elif table == "visits":
            known.visit_ids |= set(clean[table]["visit_id"])

    return ValidationOutcome(clean, rejected, results)


def enforce_thresholds(outcome: ValidationOutcome, raw_counts: dict[str, int],
                       max_reject_ratio: float) -> None:
    """Fail the run if too large a share of any table was rejected."""
    problems = []
    for table, total in raw_counts.items():
        if total == 0:
            continue
        ratio = len(outcome.rejected[table]) / total
        if ratio > max_reject_ratio:
            problems.append(f"{table}: {ratio:.0%} rejected (limit {max_reject_ratio:.0%})")
    if problems:
        raise DataQualityError("Reject threshold exceeded: " + "; ".join(problems))
