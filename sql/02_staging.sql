CREATE TABLE IF NOT EXISTS staging.patients (
    patient_id      VARCHAR(20)  NOT NULL,
    full_name       VARCHAR(120) NOT NULL,
    gender          CHAR(1)      NOT NULL,
    date_of_birth   DATE         NOT NULL,
    city            VARCHAR(60),
    insurance_type  VARCHAR(30)  NOT NULL,
    registered_date DATE         NOT NULL,
    _batch_date     DATE         NOT NULL,
    _loaded_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_stg_patients_batch ON staging.patients (_batch_date);

CREATE TABLE IF NOT EXISTS staging.doctors (
    doctor_id   VARCHAR(20)  NOT NULL,
    full_name   VARCHAR(120) NOT NULL,
    department  VARCHAR(60)  NOT NULL,
    specialty   VARCHAR(80),
    hire_date   DATE,
    is_active   BOOLEAN      NOT NULL,
    _batch_date DATE         NOT NULL,
    _loaded_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_stg_doctors_batch ON staging.doctors (_batch_date);

CREATE TABLE IF NOT EXISTS staging.visits (
    visit_id         VARCHAR(30)   NOT NULL,
    patient_id       VARCHAR(20)   NOT NULL,
    doctor_id        VARCHAR(20)   NOT NULL,
    visit_ts         TIMESTAMP     NOT NULL,
    visit_type       VARCHAR(20)   NOT NULL,
    diagnosis_code   VARCHAR(12),
    status           VARCHAR(15)   NOT NULL,
    consultation_fee NUMERIC(10,2) NOT NULL,
    discount         NUMERIC(10,2) NOT NULL,
    net_amount       NUMERIC(10,2) NOT NULL,
    _batch_date      DATE          NOT NULL,
    _loaded_at       TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_stg_visits_batch ON staging.visits (_batch_date);

CREATE TABLE IF NOT EXISTS staging.lab_tests (
    lab_order_id  VARCHAR(30)   NOT NULL,
    visit_id      VARCHAR(30)   NOT NULL,
    test_code     VARCHAR(20)   NOT NULL,
    ordered_at    TIMESTAMP     NOT NULL,
    resulted_at   TIMESTAMP,
    result_value  NUMERIC(12,3),
    test_price    NUMERIC(10,2) NOT NULL,
    _batch_date   DATE          NOT NULL,
    _loaded_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_stg_lab_batch ON staging.lab_tests (_batch_date);

CREATE TABLE IF NOT EXISTS staging.ref_lab_catalog (
    test_code  VARCHAR(20) NOT NULL,
    test_name  VARCHAR(80) NOT NULL,
    category   VARCHAR(40) NOT NULL,
    unit       VARCHAR(20),
    ref_low    NUMERIC(12,3),
    ref_high   NUMERIC(12,3),
    list_price NUMERIC(10,2)
);

CREATE TABLE IF NOT EXISTS staging.ref_diagnoses (
    diagnosis_code VARCHAR(12)  NOT NULL,
    description    VARCHAR(160) NOT NULL,
    category       VARCHAR(60)  NOT NULL
);
