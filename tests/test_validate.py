from datetime import date

import pandas as pd
import pytest

from mediflow import validate as V

D = date(2026, 9, 1)


def known():
    return V.KnownIds(patient_ids={"P1"}, doctor_ids={"D1"}, visit_ids=set(),
                      test_codes={"HGB"}, diagnosis_codes={"J06.9"})


def raw(patients=None, doctors=None, visits=None, labs=None):
    base = {
        "patients": dict(patient_id="P2", full_name="a b", gender="M", date_of_birth="1990-01-01",
                         city="Dhaka", insurance_type="None", registered_date="2026-08-01"),
        "doctors": dict(doctor_id="D2", full_name="Dr X", department="ENT", specialty="ENT",
                        hire_date="2020-01-01", is_active="true"),
        "visits": dict(visit_id="V1", patient_id="P1", doctor_id="D1", visit_ts="2026-09-01 10:00:00",
                       visit_type="OPD", diagnosis_code="J06.9", status="Completed",
                       consultation_fee="500", discount="0"),
        "lab_tests": dict(lab_order_id="L1", visit_id="V1", test_code="HGB",
                          ordered_at="2026-09-01 10:10:00", resulted_at="2026-09-01 11:00:00",
                          result_value="13.5", test_price="250"),
    }
    given = {"patients": patients, "doctors": doctors, "visits": visits, "lab_tests": labs}
    out = {}
    for table, rows in given.items():
        rows = rows if rows is not None else [{}]
        out[table] = pd.DataFrame([{**base[table], **r} for r in rows])
    return out


def reasons(outcome, table):
    return sorted(outcome.rejected[table]["reject_reasons"].tolist())


def test_clean_batch_passes_untouched():
    out = V.validate_batch(raw(), D, known())
    assert all(len(df) == 1 for df in out.clean.values())
    assert all(len(df) == 0 for df in out.rejected.values())


@pytest.mark.parametrize("override,reason", [
    ({"patient_id": "P999"}, "patient_fk_unknown"),
    ({"patient_id": None}, "patient_id_not_null"),
    ({"doctor_id": "D999"}, "doctor_fk_unknown"),
    ({"consultation_fee": "-5"}, "fee_invalid"),
    ({"discount": "900"}, "discount_invalid"),
    ({"status": "Pending-Review"}, "status_invalid"),
    ({"visit_ts": "31/02/2026 10:00"}, "visit_ts_parseable"),
    ({"visit_ts": "2026-08-20 10:00:00"}, "visit_date_outside_batch"),
])
def test_visit_rules_reject(override, reason):
    out = V.validate_batch(raw(visits=[override]), D, known())
    assert len(out.clean["visits"]) == 0
    assert reason in reasons(out, "visits")[0]


def test_unknown_diagnosis_is_only_a_warning():
    out = V.validate_batch(raw(visits=[{"diagnosis_code": "ZZ99"}]), D, known())
    assert len(out.clean["visits"]) == 1
    warn = [r for r in out.results if r.check == "diagnosis_code_unknown"][0]
    assert warn.severity == "warn" and warn.failed == 1


def test_duplicate_keeps_the_valid_row_not_the_bad_one():
    patients = [
        {"patient_id": "P1", "city": "Sylhet"},
        {"patient_id": "P1", "city": "Sylhet", "gender": "X"},
    ]
    out = V.validate_batch(raw(patients=patients), D, known())
    assert len(out.clean["patients"]) == 1
    assert out.clean["patients"].loc[0, "gender"] == "M"
    assert "gender_valid" in reasons(out, "patients")[0]


def test_duplicate_visit_ids_keep_first():
    out = V.validate_batch(raw(visits=[{}, {}]), D, known())
    assert len(out.clean["visits"]) == 1
    assert reasons(out, "visits") == ["duplicate_visit_id"]


def test_new_patient_and_doctor_in_same_batch_are_valid_foreign_keys():
    out = V.validate_batch(
        raw(visits=[{"patient_id": "P2", "doctor_id": "D2"}]), D, known())
    assert len(out.clean["visits"]) == 1


def test_lab_for_rejected_visit_becomes_orphan():
    out = V.validate_batch(
        raw(visits=[{"status": "bogus"}]), D, known())
    assert reasons(out, "lab_tests") == ["visit_fk_unknown"]


@pytest.mark.parametrize("override,reason", [
    ({"test_code": "XYZ"}, "test_code_unknown"),
    ({"resulted_at": "2026-09-01 09:00:00"}, "resulted_before_ordered"),
    ({"result_value": "n/a"}, "result_value_not_numeric"),
    ({"test_price": "-1"}, "test_price_invalid"),
])
def test_lab_rules_reject(override, reason):
    out = V.validate_batch(raw(labs=[override]), D, known())
    assert reason in reasons(out, "lab_tests")[0]


def test_pending_lab_result_is_allowed():
    out = V.validate_batch(raw(labs=[{"resulted_at": None, "result_value": None}]), D, known())
    assert len(out.clean["lab_tests"]) == 1


def test_missing_column_is_a_hard_failure():
    r = raw()
    r["visits"] = r["visits"].drop(columns=["status"])
    with pytest.raises(V.DataQualityError, match="missing required column"):
        V.validate_batch(r, D, known())


def test_reject_threshold():
    visits = [{"visit_id": f"V{i}", "patient_id": "NOPE"} for i in range(5)] + \
             [{"visit_id": f"V9{i}"} for i in range(5)]
    out = V.validate_batch(raw(visits=visits, labs=[{"visit_id": "V90"}]), D, known())
    counts = {"patients": 1, "doctors": 1, "visits": 10, "lab_tests": 1}
    with pytest.raises(V.DataQualityError, match="visits: 50% rejected"):
        V.enforce_thresholds(out, counts, 0.20)
    V.enforce_thresholds(out, counts, 0.60)          # lenient limit: no error
