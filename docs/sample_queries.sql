WITH daily AS (
    SELECT d.full_date, d.day_name, count(*) AS visits
    FROM dwh.fact_visits f
    JOIN dwh.dim_date d ON d.date_key = f.date_key
    GROUP BY d.full_date, d.day_name
)
SELECT full_date, day_name, visits,
       round(avg(visits) OVER (ORDER BY full_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
           AS moving_avg_3d,
       visits - lag(visits, 7) OVER (ORDER BY full_date) AS vs_same_day_last_week
FROM daily
ORDER BY full_date;

WITH per_doctor AS (
    SELECT dr.department, dr.full_name, count(*) AS completed_visits,
           sum(f.net_amount) AS net_revenue
    FROM dwh.fact_visits f
    JOIN dwh.dim_doctor dr ON dr.doctor_key = f.doctor_key
    WHERE f.status = 'Completed'
    GROUP BY dr.department, dr.full_name
), ranked AS (
    SELECT *, dense_rank() OVER (PARTITION BY department ORDER BY completed_visits DESC) AS rnk
    FROM per_doctor
)
SELECT department, rnk, full_name, completed_visits, net_revenue
FROM ranked
WHERE rnk <= 3
ORDER BY department, rnk, full_name;

WITH visits AS (
    SELECT p.patient_id, dr.department, f.visit_ts,
           lag(f.visit_ts) OVER (PARTITION BY p.patient_id ORDER BY f.visit_ts) AS prev_visit_ts
    FROM dwh.fact_visits f
    JOIN dwh.dim_patient p  ON p.patient_key = f.patient_key
    JOIN dwh.dim_doctor  dr ON dr.doctor_key = f.doctor_key
    WHERE f.status = 'Completed'
)
SELECT department,
       count(*)                                                        AS visits,
       count(*) FILTER (WHERE visit_ts - prev_visit_ts <= interval '30 days') AS return_within_30d,
       round(100.0 * count(*) FILTER (WHERE visit_ts - prev_visit_ts <= interval '30 days')
             / count(*), 1)                                            AS return_rate_pct
FROM visits
GROUP BY department
ORDER BY return_rate_pct DESC;

WITH tat AS (
    SELECT l.lab_order_id, t.test_name, l.turnaround_minutes,
           avg(l.turnaround_minutes) OVER (PARTITION BY l.test_key) AS avg_tat
    FROM dwh.fact_lab_tests l
    JOIN dwh.dim_test t ON t.test_key = l.test_key
    WHERE l.turnaround_minutes IS NOT NULL
)
SELECT test_name, count(*) AS breaches
FROM tat
WHERE turnaround_minutes > 1.4 * avg_tat
GROUP BY test_name
ORDER BY breaches DESC;

SELECT p.city AS city_at_visit_time,
       cur.city AS city_today,
       count(*) AS visits
FROM dwh.fact_visits f
JOIN dwh.dim_patient p   ON p.patient_key = f.patient_key
JOIN dwh.dim_patient cur ON cur.patient_id = p.patient_id AND cur.is_current
WHERE p.city <> cur.city
GROUP BY p.city, cur.city
ORDER BY visits DESC;

SELECT batch_date, step, status,
       rows_in, rows_out, rows_rejected,
       round(extract(epoch FROM (finished_at - started_at))::numeric, 2) AS seconds
FROM audit.etl_run_log
ORDER BY run_id DESC
LIMIT 20;
