import pandas as pd

from mediflow import transform as T


def test_standardize_visits_maps_spelling_variants_and_trims():
    df = pd.DataFrame({
        "visit_id": [" v1 "], "patient_id": ["p1"], "doctor_id": ["d1"],
        "visit_ts": ["2026-09-01 10:00:00"], "visit_type": ["follow up"],
        "diagnosis_code": ["j06.9"], "status": ["canceled"],
        "consultation_fee": ["500"], "discount": [""],
    })
    out = T.standardize("visits", df)
    assert out.loc[0, "visit_id"] == "V1"
    assert out.loc[0, "visit_type"] == "Follow-up"
    assert out.loc[0, "status"] == "Cancelled"
    assert out.loc[0, "diagnosis_code"] == "J06.9"
    assert pd.isna(out.loc[0, "discount"])          # blank -> missing


def test_standardize_patients_gender_and_casing():
    df = pd.DataFrame({
        "patient_id": ["p1", "p2"], "full_name": ["rahim ahmed", "AYESHA KHAN"],
        "gender": ["male", "F"], "date_of_birth": ["1990-01-01"] * 2,
        "city": ["dhaka", "CHATTOGRAM"], "insurance_type": ["premium", "NONE"],
        "registered_date": ["2026-01-01"] * 2,
    })
    out = T.standardize("patients", df)
    assert list(out["gender"]) == ["M", "F"]
    assert list(out["full_name"]) == ["Rahim Ahmed", "Ayesha Khan"]
    assert list(out["city"]) == ["Dhaka", "Chattogram"]
    assert list(out["insurance_type"]) == ["Premium", "None"]


def test_parse_ts_is_strict_iso():
    parsed = T.parse_ts(pd.Series(["2026-09-01", "2026-09-01 08:30:00", "31/02/2026 10:00", None]))
    assert parsed.notna().tolist() == [True, True, False, False]


def test_to_typed_visits_computes_net_amount_and_defaults_discount():
    df = pd.DataFrame({
        "visit_ts": ["2026-09-01 10:00:00", "2026-09-01 11:00:00"],
        "consultation_fee": ["1000", "800"], "discount": ["100", None],
    })
    out = T.to_typed("visits", df)
    assert out["net_amount"].tolist() == [900.0, 800.0]
    assert out["discount"].tolist() == [100.0, 0.0]
