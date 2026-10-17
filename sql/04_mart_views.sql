
CREATE OR REPLACE VIEW mart.v_daily_visits AS
SELECT d.full_date                                              AS visit_date,
       d.day_name,
       count(*)                                                 AS total_visits,
       count(*) FILTER (WHERE f.status = 'Completed')           AS completed,
       count(*) FILTER (WHERE f.status = 'Cancelled')           AS cancelled,
       count(*) FILTER (WHERE f.status = 'No-Show')             AS no_show,
       round(100.0 * count(*) FILTER (WHERE f.status = 'No-Show')
             / count(*), 1)                                     AS no_show_pct,
       coalesce(sum(f.net_amount), 0)                           AS net_revenue
FROM dwh.fact_visits f
JOIN dwh.dim_date    d ON d.date_key = f.date_key
GROUP BY d.full_date, d.day_name;

CREATE OR REPLACE VIEW mart.v_department_workload AS
SELECT make_date(d.year_num, d.month_num, 1)                    AS month_start,
       dr.department,
       count(*)                                                 AS visits,
       count(DISTINCT f.doctor_key)                             AS active_doctors,
       round(count(*)::numeric / nullif(count(DISTINCT f.doctor_key), 0), 1)
                                                                AS visits_per_doctor,
       coalesce(sum(f.net_amount), 0)                           AS net_revenue
FROM dwh.fact_visits f
JOIN dwh.dim_date   d  ON d.date_key   = f.date_key
JOIN dwh.dim_doctor dr ON dr.doctor_key = f.doctor_key
WHERE f.status = 'Completed'
GROUP BY make_date(d.year_num, d.month_num, 1), dr.department;

CREATE OR REPLACE VIEW mart.v_lab_turnaround AS
SELECT t.category,
       t.test_name,
       count(*)                                                 AS orders,
       count(*) FILTER (WHERE l.result_flag = 'Pending')        AS pending,
       round(avg(l.turnaround_minutes))                         AS avg_tat_minutes,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY l.turnaround_minutes)
                                                                AS p90_tat_minutes,
       round(100.0 * count(*) FILTER (WHERE l.result_flag IN ('High', 'Low'))
             / nullif(count(*) FILTER (WHERE l.result_flag <> 'Pending'), 0), 1)
                                                                AS abnormal_pct
FROM dwh.fact_lab_tests l
JOIN dwh.dim_test       t ON t.test_key = l.test_key
GROUP BY t.category, t.test_name;

CREATE OR REPLACE VIEW mart.v_visits_by_patient_city AS
SELECT p.city,
       p.insurance_type,
       count(*)                  AS visits,
       sum(f.net_amount)         AS net_revenue
FROM dwh.fact_visits f
JOIN dwh.dim_patient p ON p.patient_key = f.patient_key
WHERE f.status = 'Completed'
GROUP BY p.city, p.insurance_type;

CREATE OR REPLACE VIEW mart.dim_patient AS
SELECT p.patient_key,
       left(md5(p.patient_id), 12)                              AS patient_token,
       p.gender,
       CASE
           WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 5  THEN '0-4'
           WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 18 THEN '5-17'
           WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 40 THEN '18-39'
           WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 60 THEN '40-59'
           ELSE '60+'
       END                                                      AS age_band,
       p.city,
       p.insurance_type,
       p.registered_date,
       p.valid_from,
       p.valid_to,
       p.is_current
FROM dwh.dim_patient p;

CREATE OR REPLACE VIEW mart.dim_doctor AS      -- staff, not patients: names are fine
SELECT doctor_key, doctor_id, full_name, department, specialty, is_active FROM dwh.dim_doctor;
CREATE OR REPLACE VIEW mart.dim_date       AS SELECT * FROM dwh.dim_date;
CREATE OR REPLACE VIEW mart.dim_test       AS SELECT * FROM dwh.dim_test;
CREATE OR REPLACE VIEW mart.dim_diagnosis  AS SELECT * FROM dwh.dim_diagnosis;
CREATE OR REPLACE VIEW mart.fact_visits    AS SELECT * FROM dwh.fact_visits;
CREATE OR REPLACE VIEW mart.fact_lab_tests AS SELECT * FROM dwh.fact_lab_tests;

-- ---------------------------------------------------------------------
-- Read-only access for BI tools (Metabase): the mart schema ONLY.
-- Docker creates the login role bi_reader; without Docker it is created here as NOLOGIN
-- (or skipped when the current user is not allowed to create roles).
-- Views run with their owner's rights, so bi_reader needs no access to dwh/staging/audit.
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_reader') THEN
        BEGIN
            CREATE ROLE bi_reader NOLOGIN;
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'bi_reader does not exist and cannot be created: BI grants skipped';
        END;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_reader') THEN
        REVOKE ALL ON SCHEMA staging, dwh, audit FROM bi_reader;
        REVOKE ALL ON ALL TABLES IN SCHEMA dwh FROM bi_reader;
        GRANT USAGE ON SCHEMA mart TO bi_reader;
        GRANT SELECT ON ALL TABLES IN SCHEMA mart TO bi_reader;
        ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO bi_reader;
    END IF;
END
$$;
