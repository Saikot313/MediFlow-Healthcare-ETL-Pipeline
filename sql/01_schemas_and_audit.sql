CREATE SCHEMA IF NOT EXISTS staging;   
CREATE SCHEMA IF NOT EXISTS dwh;      
CREATE SCHEMA IF NOT EXISTS audit;     
CREATE SCHEMA IF NOT EXISTS mart;     

CREATE TABLE IF NOT EXISTS audit.etl_run_log (
    run_id        BIGSERIAL PRIMARY KEY,
    batch_date    DATE         NOT NULL,
    step          VARCHAR(60)  NOT NULL,
    status        VARCHAR(12)  NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    rows_in       INTEGER,
    rows_out      INTEGER,
    rows_rejected INTEGER,
    message       TEXT,
    started_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_run_log_batch ON audit.etl_run_log (batch_date, step);

CREATE TABLE IF NOT EXISTS audit.dq_results (
    dq_id        BIGSERIAL PRIMARY KEY,
    batch_date   DATE         NOT NULL,
    table_name   VARCHAR(60)  NOT NULL,
    check_name   VARCHAR(80)  NOT NULL,
    severity     VARCHAR(10)  NOT NULL CHECK (severity IN ('reject', 'warn', 'fail')),
    failed_rows  INTEGER      NOT NULL,
    total_rows   INTEGER      NOT NULL,
    passed       BOOLEAN      NOT NULL,
    checked_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dq_results_batch ON audit.dq_results (batch_date, table_name);

CREATE TABLE IF NOT EXISTS audit.rejected_rows (
    reject_id    BIGSERIAL PRIMARY KEY,
    batch_date   DATE         NOT NULL,
    table_name   VARCHAR(60)  NOT NULL,
    reasons      TEXT         NOT NULL,
    row_data     JSONB        NOT NULL,
    rejected_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rejected_batch ON audit.rejected_rows (batch_date, table_name);
