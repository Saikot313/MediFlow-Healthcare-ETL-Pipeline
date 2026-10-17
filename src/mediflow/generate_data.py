from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

CITIES = ["Dhaka", "Chattogram", "Rajshahi", "Khulna", "Sylhet", "Barishal", "Rangpur",
          "Mymensingh", "Gazipur", "Narayanganj"]
CITY_P = [0.40, 0.14, 0.09, 0.08, 0.07, 0.04, 0.05, 0.05, 0.05, 0.03]

MALE = ["Rahim", "Karim", "Hasan", "Hossain", "Imran", "Nabil", "Tanvir", "Sakib", "Rafiq",
        "Jahid", "Mahmud", "Arif", "Faisal", "Shahin", "Rubel", "Mizan", "Salman", "Anwar",
        "Habib", "Zakir"]
FEMALE = ["Ayesha", "Fatima", "Nusrat", "Sumaiya", "Tasnim", "Farzana", "Rima", "Shirin",
          "Mim", "Nadia", "Sabina", "Jannat", "Rokeya", "Lubna", "Sharmin", "Tania", "Mousumi",
          "Rabeya", "Taslima", "Nipa"]
LAST = ["Ahmed", "Rahman", "Islam", "Hossain", "Khan", "Chowdhury", "Uddin", "Akter",
        "Begum", "Sarkar", "Mia", "Talukder", "Sheikh", "Mondal", "Biswas", "Haque", "Siddique",
        "Alam", "Karim", "Roy"]

INSURANCE = ["None", "Basic", "Premium", "Corporate"]
INSURANCE_P = [0.45, 0.30, 0.15, 0.10]
INSURANCE_DISCOUNT = {"None": 0.0, "Basic": 0.05, "Premium": 0.10, "Corporate": 0.20}

DEPARTMENTS = {
    "General Medicine": (28, 500, ["J06.9", "A09", "R50.9", "E11.9", "K29.7", "B34.9", "Z00.0", "D64.9", "A90"]),
    "Pediatrics":       (14, 600, ["J06.9", "A09", "J18.9", "R50.9", "H66.9", "J45.9"]),
    "Cardiology":       (10, 1000, ["I10", "I25.9", "E78.5", "E11.9"]),
    "Orthopedics":      (10, 800, ["M54.5", "M17.9", "S93.4"]),
    "Gynecology":       (10, 800, ["N39.0", "D64.9", "Z00.0"]),
    "ENT":              (8, 700, ["H66.9", "J06.9", "J45.9"]),
    "Dermatology":      (8, 700, ["L20.9", "B34.9"]),
    "Neurology":        (6, 1200, ["G43.9", "R51"]),
    "Emergency":        (6, 900, ["J18.9", "S93.4", "A90", "R50.9", "I10"]),
}
VISIT_TYPE_MULT = {"OPD": 1.0, "Emergency": 1.5, "Follow-up": 0.5, "Telemedicine": 0.7}

DIAGNOSES = [
    ("I10", "Essential (primary) hypertension", "Circulatory"),
    ("I25.9", "Chronic ischaemic heart disease, unspecified", "Circulatory"),
    ("E11.9", "Type 2 diabetes mellitus without complications", "Endocrine"),
    ("E78.5", "Hyperlipidaemia, unspecified", "Endocrine"),
    ("J06.9", "Acute upper respiratory infection, unspecified", "Respiratory"),
    ("J18.9", "Pneumonia, unspecified organism", "Respiratory"),
    ("J45.9", "Asthma, unspecified", "Respiratory"),
    ("A09", "Infectious gastroenteritis and colitis, unspecified", "Infectious"),
    ("A90", "Dengue fever (classical dengue)", "Infectious"),
    ("B34.9", "Viral infection, unspecified", "Infectious"),
    ("R50.9", "Fever, unspecified", "Symptoms and signs"),
    ("R51", "Headache", "Symptoms and signs"),
    ("K29.7", "Gastritis, unspecified", "Digestive"),
    ("M54.5", "Low back pain", "Musculoskeletal"),
    ("M17.9", "Osteoarthritis of knee, unspecified", "Musculoskeletal"),
    ("S93.4", "Sprain and strain of ankle", "Injury"),
    ("N39.0", "Urinary tract infection, site not specified", "Genitourinary"),
    ("H66.9", "Otitis media, unspecified", "Ear"),
    ("L20.9", "Atopic dermatitis, unspecified", "Skin"),
    ("G43.9", "Migraine, unspecified", "Nervous system"),
    ("D64.9", "Anaemia, unspecified", "Blood"),
    ("Z00.0", "General medical examination", "Health services"),
]

LAB_CATALOG = [
    ("HGB", "Hemoglobin", "Hematology", "g/dL", 12.0, 17.5, 250, 60),
    ("WBC", "White Blood Cell Count", "Hematology", "10^3/uL", 4.0, 11.0, 250, 60),
    ("PLT", "Platelet Count", "Hematology", "10^3/uL", 150, 450, 300, 70),
    ("GLU-F", "Fasting Glucose", "Biochemistry", "mg/dL", 70, 100, 150, 120),
    ("HBA1C", "HbA1c", "Biochemistry", "%", 4.0, 5.6, 700, 180),
    ("CHOL", "Total Cholesterol", "Biochemistry", "mg/dL", 0, 200, 350, 150),
    ("TG", "Triglycerides", "Biochemistry", "mg/dL", 0, 150, 350, 150),
    ("CREA", "Serum Creatinine", "Biochemistry", "mg/dL", 0.6, 1.3, 300, 120),
    ("ALT", "ALT (SGPT)", "Biochemistry", "U/L", 7, 56, 400, 150),
    ("TSH", "Thyroid Stimulating Hormone", "Endocrinology", "mIU/L", 0.4, 4.0, 800, 240),
    ("VITD", "Vitamin D", "Endocrinology", "ng/mL", 30, 100, 2500, 360),
    ("CRP", "C-Reactive Protein", "Immunology", "mg/L", 0, 10, 600, 180),
    ("SOD", "Sodium", "Electrolytes", "mmol/L", 135, 145, 300, 90),
    ("POT", "Potassium", "Electrolytes", "mmol/L", 3.5, 5.1, 300, 90),
]

PATIENT_COLS = ["patient_id", "full_name", "gender", "date_of_birth", "city",
                "insurance_type", "registered_date"]
DOCTOR_COLS = ["doctor_id", "full_name", "department", "specialty", "hire_date", "is_active"]
VISIT_COLS = ["visit_id", "patient_id", "doctor_id", "visit_ts", "visit_type",
              "diagnosis_code", "status", "consultation_fee", "discount"]
LAB_COLS = ["lab_order_id", "visit_id", "test_code", "ordered_at", "resulted_at",
            "result_value", "test_price"]


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def write_reference(out_dir: Path) -> None:
    _write(out_dir / "lab_catalog.csv",
           ["test_code", "test_name", "category", "unit", "ref_low", "ref_high", "list_price"],
           [dict(test_code=c, test_name=n, category=cat, unit=u, ref_low=lo, ref_high=hi,
                 list_price=p) for c, n, cat, u, lo, hi, p, _ in LAB_CATALOG])
    _write(out_dir / "diagnoses.csv", ["diagnosis_code", "description", "category"],
           [dict(diagnosis_code=c, description=d, category=g) for c, d, g in DIAGNOSES])


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


class _Generator:
    def __init__(self, seed: int, n_patients: int, n_doctors: int, dirty_rate: float):
        self.rng = np.random.default_rng(seed)
        self.dirty_rate = dirty_rate
        self.n_patients = n_patients
        self.n_doctors = n_doctors
        self.patients: list[dict] = []
        self.doctors: list[dict] = []
        self._pat_seq = 0
        self._carry_over: list[dict] = []     # lab orders pending yesterday, resulted today

    def _pick(self, seq):
        return seq[int(self.rng.integers(0, len(seq)))]

    def _new_patient(self, registered: date) -> dict:
        self._pat_seq += 1
        gender = "M" if self.rng.random() < 0.48 else "F"
        first = self._pick(MALE if gender == "M" else FEMALE)
        age_days = int(self.rng.integers(1, 86)) * 365 + int(self.rng.integers(0, 365))
        return {
            "patient_id": f"P{self._pat_seq:06d}",
            "full_name": f"{first} {self._pick(LAST)}",
            "gender": gender,
            "date_of_birth": (registered - timedelta(days=age_days)).isoformat(),
            "city": str(self.rng.choice(CITIES, p=CITY_P)),
            "insurance_type": str(self.rng.choice(INSURANCE, p=INSURANCE_P)),
            "registered_date": registered.isoformat(),
        }

    def _init_doctors(self, d: date) -> None:
        depts = list(DEPARTMENTS)
        for i in range(1, self.n_doctors + 1):
            dept = depts[(i - 1) % len(depts)]
            first = self._pick(MALE + FEMALE)
            self.doctors.append({
                "doctor_id": f"D{i:03d}",
                "full_name": f"Dr. {first} {self._pick(LAST)}",
                "department": dept,
                "specialty": dept,
                "hire_date": (d - timedelta(days=int(self.rng.integers(200, 4000)))).isoformat(),
                "is_active": "true",
            })

    def day(self, d: date, first_day: bool) -> dict[str, list[dict]]:
        rng = self.rng
        patients_today: list[dict] = []
        doctors_today: list[dict] = []
        dirty_patients: list[dict] = []

        if first_day:
            for _ in range(self.n_patients):
                p = self._new_patient(d - timedelta(days=int(rng.integers(0, 700))))
                self.patients.append(p)
            patients_today = [dict(p) for p in self.patients]
            self._init_doctors(d)
            doctors_today = [dict(x) for x in self.doctors]
        else:
            for _ in range(int(rng.poisson(12))):                     # new registrations
                p = self._new_patient(d)
                self.patients.append(p)
                patients_today.append(dict(p))
            n_changes = max(1, int(len(self.patients) * 0.008))       # attribute changes (SCD2)
            for idx in rng.choice(len(self.patients), size=n_changes, replace=False):
                p = self.patients[int(idx)]
                if p["registered_date"] == d.isoformat():
                    continue
                if rng.random() < 0.6:
                    p["city"] = str(rng.choice([c for c in CITIES if c != p["city"]]))
                else:
                    p["insurance_type"] = str(
                        rng.choice([i for i in INSURANCE if i != p["insurance_type"]]))
                patients_today.append(dict(p))
            if rng.random() < 0.25:                                   # roster change (SCD1)
                doc = self.doctors[int(rng.integers(0, len(self.doctors)))]
                if rng.random() < 0.5:
                    doc["is_active"] = "false" if doc["is_active"] == "true" else "true"
                else:
                    doc["department"] = self._pick(list(DEPARTMENTS))
                doctors_today.append(dict(doc))
            if patients_today and self.dirty_rate > 0 and rng.random() < 0.7:
                changed = [r for r in patients_today if r["registered_date"] != d.isoformat()]
                if changed:
                    bad = dict(self._pick(changed))
                    kind = self._pick(["gender", "dob", "insurance"])
                    if kind == "gender":
                        bad["gender"] = "X"
                    elif kind == "dob":
                        bad["date_of_birth"] = (d + timedelta(days=400)).isoformat()
                    else:
                        bad["insurance_type"] = "Gold-Plus"
                    dirty_patients.append(bad)
        patients_today = patients_today + dirty_patients

        visits, labs, pending_results = self._visits_and_labs(d)
        labs = self._carry_over + labs
        self._carry_over = pending_results
        return {"patients": patients_today, "doctors": doctors_today,
                "visits": visits, "lab_tests": labs}

    def _visits_and_labs(self, d: date):
        rng = self.rng
        weekend = d.weekday() in (4, 5)                              # Fri, Sat
        n = int(rng.poisson(95 if weekend else 190))
        active = [x for x in self.doctors if x["is_active"] == "true"]
        by_dept: dict[str, list[dict]] = {}
        for doc in active:
            by_dept.setdefault(doc["department"], []).append(doc)
        depts = [k for k in DEPARTMENTS if k in by_dept]
        w = np.array([DEPARTMENTS[k][0] for k in depts], dtype=float)
        w /= w.sum()
        frequent = self.patients[: max(1, int(len(self.patients) * 0.15))]
        ins_by_patient = {p["patient_id"]: p["insurance_type"] for p in self.patients}

        visits: list[dict] = []
        labs: list[dict] = []
        follow_ups: list[dict] = []
        lab_seq = 0
        for i in range(1, n + 1):
            dept = str(rng.choice(depts, p=w))
            doc = self._pick(by_dept[dept])
            patient = self._pick(frequent) if rng.random() < 0.5 else self._pick(self.patients)
            if dept == "Emergency":
                vtype = "Emergency"
            else:
                vtype = str(rng.choice(["OPD", "Follow-up", "Telemedicine"], p=[0.70, 0.20, 0.10]))
            status = str(rng.choice(["Completed", "Cancelled", "No-Show"], p=[0.83, 0.09, 0.08]))
            if vtype == "Emergency":
                minute = int(rng.integers(0, 24 * 60))
            else:
                minute = int(rng.integers(8 * 60, 20 * 60))
            ts = datetime(d.year, d.month, d.day) + timedelta(minutes=minute)
            fee = discount = 0.0
            dx = ""
            if status == "Completed":
                fee = round(DEPARTMENTS[dept][1] * VISIT_TYPE_MULT[vtype] / 50) * 50.0
                discount = round(fee * INSURANCE_DISCOUNT[ins_by_patient[patient["patient_id"]]], 2)
                dx = self._pick(DEPARTMENTS[dept][2])
            visit_id = f"V{d:%Y%m%d}-{i:04d}"
            visits.append({
                "visit_id": visit_id, "patient_id": patient["patient_id"],
                "doctor_id": doc["doctor_id"], "visit_ts": _fmt_ts(ts), "visit_type": vtype,
                "diagnosis_code": dx, "status": status,
                "consultation_fee": f"{fee:.2f}", "discount": f"{discount:.2f}",
            })
            if status == "Completed" and rng.random() < 0.35:
                for idx in rng.choice(len(LAB_CATALOG), size=int(rng.integers(1, 4)), replace=False):
                    code, _n, _c, _u, lo, hi, price, tat = LAB_CATALOG[int(idx)]
                    lab_seq += 1
                    ordered = ts + timedelta(minutes=int(rng.integers(5, 40)))
                    pending = rng.random() < 0.03
                    resulted = ordered + timedelta(
                        minutes=max(15, int(rng.normal(tat, tat * 0.25))))
                    mid, span = (lo + hi) / 2, (hi - lo)
                    r = rng.random()
                    if r < 0.80:
                        value = rng.uniform(lo, hi)
                    elif r < 0.90 and lo > 0:
                        value = lo - rng.uniform(0.02, 0.25) * span
                    else:
                        value = hi + rng.uniform(0.02, 0.35) * span
                    row = {
                        "lab_order_id": f"L{d:%Y%m%d}-{lab_seq:05d}", "visit_id": visit_id,
                        "test_code": code, "ordered_at": _fmt_ts(ordered),
                        "resulted_at": "" if pending else _fmt_ts(resulted),
                        "result_value": "" if pending else f"{value:.2f}",
                        "test_price": f"{price:.2f}",
                    }
                    labs.append(row)
                    if pending:                       # result arrives the next morning
                        late = datetime(d.year, d.month, d.day) + timedelta(
                            days=1, hours=8 + lab_seq % 6, minutes=(lab_seq * 7) % 60)
                        follow_ups.append({**row, "resulted_at": _fmt_ts(late),
                                           "result_value": f"{value:.2f}"})
        self._corrupt(visits, labs, d)               # only today's own rows are corrupted
        return visits, labs, follow_ups

    def _corrupt(self, visits: list[dict], labs: list[dict], d: date) -> None:
        """Inject ~dirty_rate bad rows. Each kind maps to a validation rule."""
        rng = self.rng
        k = max(1, int(len(visits) * self.dirty_rate)) if visits and self.dirty_rate > 0 else 0
        for idx in rng.choice(len(visits), size=min(k, len(visits)), replace=False) if k else []:
            v = visits[int(idx)]
            kind = self._pick(["null_patient", "unknown_patient", "negative_fee", "discount_gt_fee",
                               "bad_status", "unknown_doctor", "bad_ts", "wrong_date",
                               "unknown_dx", "dup"])
            if kind == "null_patient":
                v["patient_id"] = ""
            elif kind == "unknown_patient":
                v["patient_id"] = "P999999"
            elif kind == "negative_fee":
                v["consultation_fee"] = "-500.00"
            elif kind == "discount_gt_fee":
                v["discount"] = f"{float(v['consultation_fee']) + 100:.2f}"
            elif kind == "bad_status":
                v["status"] = "Pending-Review"
            elif kind == "unknown_doctor":
                v["doctor_id"] = "D999"
            elif kind == "bad_ts":
                v["visit_ts"] = "31/02/2026 10:00"
            elif kind == "wrong_date":
                v["visit_ts"] = _fmt_ts(datetime(d.year, d.month, d.day) - timedelta(days=9, hours=-10))
            elif kind == "unknown_dx":                       # warn only: loads as 'Unknown'
                v["diagnosis_code"] = "ZZ99"
            elif kind == "dup":
                visits.append(dict(v))
        k = max(1, int(len(labs) * self.dirty_rate)) if labs and self.dirty_rate > 0 else 0
        for idx in rng.choice(len(labs), size=min(k, len(labs)), replace=False) if k else []:
            row = labs[int(idx)]
            kind = self._pick(["unknown_visit", "unknown_test", "result_before_order",
                               "negative_price", "text_value"])
            if kind == "unknown_visit":
                row["visit_id"] = "V99999999-9999"
            elif kind == "unknown_test":
                row["test_code"] = "XYZ-99"
            elif kind == "result_before_order" and row["resulted_at"]:
                ordered = datetime.strptime(row["ordered_at"], "%Y-%m-%d %H:%M:%S")
                row["resulted_at"] = _fmt_ts(ordered - timedelta(minutes=30))
            elif kind == "negative_price":
                row["test_price"] = "-250.00"
            elif kind == "text_value":
                row["result_value"] = "n/a"


def generate(start: date, days: int, out_dir: Path, reference_dir: Path | None = None,
             seed: int = 42, n_patients: int = 1500, n_doctors: int = 36,
             dirty_rate: float = 0.02) -> list[Path]:
    """Generate `days` consecutive daily batches starting at `start`."""
    out_dir = Path(out_dir)
    write_reference(Path(reference_dir) if reference_dir else out_dir.parent / "reference")
    gen = _Generator(seed, n_patients, n_doctors, dirty_rate)
    folders = []
    for i in range(days):
        d = start + timedelta(days=i)
        data = gen.day(d, first_day=(i == 0))
        folder = out_dir / d.isoformat()
        _write(folder / "patients.csv", PATIENT_COLS, data["patients"])
        _write(folder / "doctors.csv", DOCTOR_COLS, data["doctors"])
        _write(folder / "visits.csv", VISIT_COLS, data["visits"])
        _write(folder / "lab_tests.csv", LAB_COLS, data["lab_tests"])
        folders.append(folder)
    return folders
