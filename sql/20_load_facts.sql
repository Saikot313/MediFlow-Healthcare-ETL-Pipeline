
INSERT INTO dwh.fact_visits (visit_id, date_key, patient_key, doctor_key, diagnosis_key,
                             visit_ts, visit_type, status, consultation_fee, discount,
                             net_amount, batch_date)
SELECT v.visit_id,
       to_char(v.visit_ts, 'YYYYMMDD')::int,
       p.patient_key,                         -- version of the patient valid ON the visit date
       d.doctor_key,
       coalesce(dg.diagnosis_key, -1),
       v.visit_ts, v.visit_type, v.status,
       v.consultation_fee, v.discount, v.net_amount,
       v._batch_date
FROM staging.visits v
JOIN dwh.dim_patient p
  ON p.patient_id = v.patient_id
 AND CAST(v.visit_ts AS date) >= p.valid_from
 AND CAST(v.visit_ts AS date) <  p.valid_to
JOIN dwh.dim_doctor d ON d.doctor_id = v.doctor_id
LEFT JOIN dwh.dim_diagnosis dg ON dg.diagnosis_code = v.diagnosis_code
WHERE v._batch_date = :batch_date
ON CONFLICT (visit_id) DO UPDATE
SET patient_key      = EXCLUDED.patient_key,
    doctor_key       = EXCLUDED.doctor_key,
    diagnosis_key    = EXCLUDED.diagnosis_key,
    status           = EXCLUDED.status,
    visit_type       = EXCLUDED.visit_type,
    consultation_fee = EXCLUDED.consultation_fee,
    discount         = EXCLUDED.discount,
    net_amount       = EXCLUDED.net_amount,
    batch_date       = EXCLUDED.batch_date,
    loaded_at        = now()
WHERE dwh.fact_visits.batch_date <= EXCLUDED.batch_date;   -- never overwrite newer data


INSERT INTO dwh.fact_lab_tests (lab_order_id, visit_key, date_key, patient_key, doctor_key,
                                test_key, ordered_at, resulted_at, turnaround_minutes,
                                result_value, result_flag, test_price, batch_date)
SELECT l.lab_order_id,
       fv.visit_key,
       fv.date_key,
       fv.patient_key,
       fv.doctor_key,
       t.test_key,
       l.ordered_at,
       l.resulted_at,
       CASE WHEN l.resulted_at IS NULL THEN NULL
            ELSE (extract(epoch FROM (l.resulted_at - l.ordered_at)) / 60)::int END,
       l.result_value,
       CASE WHEN l.result_value IS NULL                                THEN 'Pending'
            WHEN t.ref_low  IS NOT NULL AND l.result_value < t.ref_low  THEN 'Low'
            WHEN t.ref_high IS NOT NULL AND l.result_value > t.ref_high THEN 'High'
            ELSE 'Normal' END,
       l.test_price,
       l._batch_date
FROM staging.lab_tests l
JOIN dwh.fact_visits fv ON fv.visit_id  = l.visit_id
JOIN dwh.dim_test    t  ON t.test_code  = l.test_code
WHERE l._batch_date = :batch_date
ON CONFLICT (lab_order_id) DO UPDATE
SET resulted_at        = EXCLUDED.resulted_at,
    turnaround_minutes = EXCLUDED.turnaround_minutes,
    result_value       = EXCLUDED.result_value,
    result_flag        = EXCLUDED.result_flag,
    test_price         = EXCLUDED.test_price,
    batch_date         = EXCLUDED.batch_date,
    loaded_at          = now()
WHERE dwh.fact_lab_tests.batch_date <= EXCLUDED.batch_date;  -- never overwrite newer data
