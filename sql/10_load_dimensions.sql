
INSERT INTO dwh.dim_test (test_code, test_name, category, unit, ref_low, ref_high, list_price)
SELECT test_code, test_name, category, unit, ref_low, ref_high, list_price
FROM staging.ref_lab_catalog
ON CONFLICT (test_code) DO UPDATE
SET test_name  = EXCLUDED.test_name,
    category   = EXCLUDED.category,
    unit       = EXCLUDED.unit,
    ref_low    = EXCLUDED.ref_low,
    ref_high   = EXCLUDED.ref_high,
    list_price = EXCLUDED.list_price
WHERE (dwh.dim_test.test_name, dwh.dim_test.category, dwh.dim_test.unit,
       dwh.dim_test.ref_low, dwh.dim_test.ref_high, dwh.dim_test.list_price)
      IS DISTINCT FROM
      (EXCLUDED.test_name, EXCLUDED.category, EXCLUDED.unit,
       EXCLUDED.ref_low, EXCLUDED.ref_high, EXCLUDED.list_price);

INSERT INTO dwh.dim_diagnosis (diagnosis_code, description, category)
SELECT diagnosis_code, description, category
FROM staging.ref_diagnoses
ON CONFLICT (diagnosis_code) DO UPDATE
SET description = EXCLUDED.description,
    category    = EXCLUDED.category
WHERE (dwh.dim_diagnosis.description, dwh.dim_diagnosis.category)
      IS DISTINCT FROM (EXCLUDED.description, EXCLUDED.category);


INSERT INTO dwh.dim_doctor (doctor_id, full_name, department, specialty, hire_date, is_active,
                            batch_date)
SELECT doctor_id, full_name, department, specialty, hire_date, is_active, _batch_date
FROM staging.doctors
WHERE _batch_date = :batch_date
ON CONFLICT (doctor_id) DO UPDATE
SET full_name  = EXCLUDED.full_name,
    department = EXCLUDED.department,
    specialty  = EXCLUDED.specialty,
    hire_date  = EXCLUDED.hire_date,
    is_active  = EXCLUDED.is_active,
    batch_date = EXCLUDED.batch_date,
    updated_at = now()
WHERE dwh.dim_doctor.batch_date <= EXCLUDED.batch_date
  AND (dwh.dim_doctor.full_name, dwh.dim_doctor.department, dwh.dim_doctor.specialty,
       dwh.dim_doctor.hire_date, dwh.dim_doctor.is_active)
      IS DISTINCT FROM
      (EXCLUDED.full_name, EXCLUDED.department, EXCLUDED.specialty,
       EXCLUDED.hire_date, EXCLUDED.is_active);


UPDATE dwh.dim_patient d
SET    valid_to   = :batch_date,
       is_current = FALSE
FROM (
    SELECT DISTINCT ON (patient_id)
           patient_id,
           md5(concat_ws('|', full_name, gender, date_of_birth::text,
                         coalesce(city, ''), insurance_type)) AS row_hash
    FROM staging.patients
    WHERE _batch_date = :batch_date
    ORDER BY patient_id, _loaded_at DESC
) s
WHERE d.patient_id = s.patient_id
  AND d.is_current
  AND d.valid_from < :batch_date
  AND d.row_hash <> s.row_hash;


INSERT INTO dwh.dim_patient (patient_id, full_name, gender, date_of_birth, city,
                             insurance_type, registered_date, row_hash,
                             valid_from, valid_to, is_current)
SELECT s.patient_id, s.full_name, s.gender, s.date_of_birth, s.city,
       s.insurance_type, s.registered_date,
       md5(concat_ws('|', s.full_name, s.gender, s.date_of_birth::text,
                     coalesce(s.city, ''), s.insurance_type)),
       CASE WHEN EXISTS (SELECT 1 FROM dwh.dim_patient x WHERE x.patient_id = s.patient_id)
            THEN CAST(:batch_date AS date)
            ELSE DATE '1900-01-01' END,
       DATE '9999-12-31',
       TRUE
FROM (
    SELECT DISTINCT ON (patient_id) *
    FROM staging.patients
    WHERE _batch_date = :batch_date
    ORDER BY patient_id, _loaded_at DESC
) s
WHERE NOT EXISTS (
    SELECT 1 FROM dwh.dim_patient c
    WHERE c.patient_id = s.patient_id AND c.is_current
);
