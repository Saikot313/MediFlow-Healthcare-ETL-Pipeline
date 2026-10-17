from __future__ import annotations

import pandas as pd

SCHEMAS: dict[str, list[str]] = {
    "patients": ["patient_id", "full_name", "gender", "date_of_birth", "city",
                 "insurance_type", "registered_date"],
    "doctors": ["doctor_id", "full_name", "department", "specialty", "hire_date", "is_active"],
    "visits": ["visit_id", "patient_id", "doctor_id", "visit_ts", "visit_type",
               "diagnosis_code", "status", "consultation_fee", "discount"],
    "lab_tests": ["lab_order_id", "visit_id", "test_code", "ordered_at", "resulted_at",
                  "result_value", "test_price"],
}

_GENDER = {"m": "M", "male": "M", "f": "F", "female": "F", "o": "O", "other": "O"}
_STATUS = {"completed": "Completed", "cancelled": "Cancelled", "canceled": "Cancelled",
           "no-show": "No-Show", "noshow": "No-Show", "no show": "No-Show"}
_VISIT_TYPE = {"opd": "OPD", "emergency": "Emergency", "follow-up": "Follow-up",
               "followup": "Follow-up", "follow up": "Follow-up", "telemedicine": "Telemedicine"}
_BOOL = {"true": True, "t": True, "1": True, "yes": True, "y": True,
         "false": False, "f": False, "0": False, "no": False, "n": False}


def _canon(series: pd.Series, mapping: dict) -> pd.Series:
    key = series.astype("string").str.strip().str.lower()
    mapped = key.map(mapping)
    return mapped.where(mapped.notna(), series)


def read_csv_raw(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def standardize(table: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        s = df[col].astype("object")
        s = s.where(s.isna(), s.astype(str).str.strip())
        df[col] = s.replace("", pd.NA)

    def upper(col):
        df[col] = df[col].str.upper()

    def title(col):
        df[col] = df[col].str.title()

    if table == "patients":
        upper("patient_id"); title("full_name"); title("city"); title("insurance_type")
        df["gender"] = _canon(df["gender"], _GENDER)
        df["gender"] = df["gender"].str.upper()
    elif table == "doctors":
        upper("doctor_id"); title("full_name"); title("department"); title("specialty")
        df["is_active"] = _canon(df["is_active"], _BOOL)
    elif table == "visits":
        for c in ("visit_id", "patient_id", "doctor_id", "diagnosis_code"):
            upper(c)
        df["status"] = _canon(df["status"], _STATUS)
        df["visit_type"] = _canon(df["visit_type"], _VISIT_TYPE)
    elif table == "lab_tests":
        for c in ("lab_order_id", "visit_id", "test_code"):
            upper(c)
    return df

def parse_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", format="ISO8601")


def parse_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def to_typed(table: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if table == "patients":
        df["date_of_birth"] = parse_ts(df["date_of_birth"]).dt.date
        df["registered_date"] = parse_ts(df["registered_date"]).dt.date
    elif table == "doctors":
        df["hire_date"] = parse_ts(df["hire_date"]).dt.date
        df["is_active"] = df["is_active"].astype(bool)
    elif table == "visits":
        df["visit_ts"] = parse_ts(df["visit_ts"])
        df["consultation_fee"] = parse_num(df["consultation_fee"]).round(2)
        df["discount"] = parse_num(df["discount"]).fillna(0).round(2)
        df["net_amount"] = (df["consultation_fee"] - df["discount"]).round(2)
    elif table == "lab_tests":
        df["ordered_at"] = parse_ts(df["ordered_at"])
        df["resulted_at"] = parse_ts(df["resulted_at"])
        df["result_value"] = parse_num(df["result_value"])
        df["test_price"] = parse_num(df["test_price"]).round(2)
    return df
