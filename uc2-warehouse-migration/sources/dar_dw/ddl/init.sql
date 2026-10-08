-- =============================================================================
-- init.sql  —  DAR_DW star schema (M2)
-- PostgreSQL 16.4 emulating SQL Server DW pattern.
-- Tables include: modified_at (watermark), row_version (optimistic concurrency),
-- is_deleted (soft delete for incremental pipelines without CDC).
-- =============================================================================

SET search_path = warehouse;

-- ---------------------------------------------------------------------------
-- DIM_CALENDAR — date spine (no modified_at; static dimension)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.dim_calendar (
    date_id          DATE         PRIMARY KEY,
    year             SMALLINT     NOT NULL,
    quarter          SMALLINT     NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month            SMALLINT     NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name       VARCHAR(9)   NOT NULL,
    day              SMALLINT     NOT NULL,
    day_of_week      SMALLINT     NOT NULL,           -- 0=Monday
    day_name         VARCHAR(9)   NOT NULL,
    week_of_year     SMALLINT     NOT NULL,
    is_weekend       BOOLEAN      NOT NULL DEFAULT FALSE,
    is_holiday       BOOLEAN      NOT NULL DEFAULT FALSE,
    fiscal_year      SMALLINT,                        -- Dar FY: April–March
    fiscal_quarter   SMALLINT
);

-- ---------------------------------------------------------------------------
-- DIM_PROJECT
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.dim_project (
    project_id       VARCHAR(50)  PRIMARY KEY,
    project_name     VARCHAR(255),                    -- DQ: intentionally nullable
    client_name      VARCHAR(255) NOT NULL,
    project_type     VARCHAR(50)  NOT NULL,           -- Infrastructure/Building/Transport
    country          VARCHAR(50)  NOT NULL,
    currency         VARCHAR(3)   NOT NULL DEFAULT 'USD',
    status           VARCHAR(50)  NOT NULL,           -- Active/Completed/Planning/OnHold
    start_date       DATE,
    planned_end_date DATE,
    actual_end_date  DATE,
    pm_employee_id   INT,
    modified_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version      BIGINT       NOT NULL DEFAULT 1,
    is_deleted       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- DIM_WBS — hierarchical work breakdown structure
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.dim_wbs (
    wbs_id           VARCHAR(100) PRIMARY KEY,
    project_id       VARCHAR(50),                     -- may be NULL (orphan: DQ issue)
    parent_wbs_id    VARCHAR(100),                    -- NULL for root level
    wbs_code         VARCHAR(50)  NOT NULL,
    wbs_name         VARCHAR(255) NOT NULL,
    wbs_level        SMALLINT     NOT NULL DEFAULT 1,
    discipline       VARCHAR(100),
    is_summary       BOOLEAN      NOT NULL DEFAULT FALSE,
    sort_order       INT          NOT NULL DEFAULT 0,
    modified_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version      BIGINT       NOT NULL DEFAULT 1,
    is_deleted       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- DIM_EMPLOYEE
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.dim_employee (
    employee_id      INT          PRIMARY KEY,
    employee_name    VARCHAR(255) NOT NULL,
    email            VARCHAR(255),
    role             VARCHAR(100) NOT NULL,
    grade            VARCHAR(20),
    department       VARCHAR(100) NOT NULL,
    office_country   VARCHAR(50),
    hourly_rate_usd  NUMERIC(10,2),
    hire_date        DATE,
    modified_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version      BIGINT       NOT NULL DEFAULT 1,
    is_deleted       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- DIM_COST_CODE
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.dim_cost_code (
    cost_code        VARCHAR(50)  PRIMARY KEY,
    description      VARCHAR(255) NOT NULL,
    category         VARCHAR(50)  NOT NULL,           -- LABOR/MATERIAL/SUBCONTRACT/OVERHEAD
    is_billable      BOOLEAN      NOT NULL DEFAULT TRUE,
    modified_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version      BIGINT       NOT NULL DEFAULT 1,
    is_deleted       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- FACT_BUDGET
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.fact_budget (
    budget_id        SERIAL       PRIMARY KEY,
    wbs_id           VARCHAR(100) NOT NULL,
    cost_code        VARCHAR(50)  NOT NULL,
    budget_amount    NUMERIC(15,2) NOT NULL,
    currency         VARCHAR(3)   NOT NULL DEFAULT 'USD',  -- DQ: may be EUR
    budget_hours     NUMERIC(10,2),
    effective_date   DATE,
    modified_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version      BIGINT       NOT NULL DEFAULT 1,
    is_deleted       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- FACT_TIMESHEET
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.fact_timesheet (
    timesheet_id     SERIAL       PRIMARY KEY,
    employee_id      INT          NOT NULL,
    wbs_id           VARCHAR(100) NOT NULL,
    date_id          DATE         NOT NULL,
    hours            NUMERIC(5,2) NOT NULL CHECK (hours >= 0),
    activity_code    VARCHAR(50),
    is_approved      BOOLEAN      NOT NULL DEFAULT FALSE,
    approved_by      INT,
    submitted_at     TIMESTAMP,
    modified_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version      BIGINT       NOT NULL DEFAULT 1,
    is_deleted       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- FACT_COST_ACTUALS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.fact_cost_actuals (
    actual_id        SERIAL       PRIMARY KEY,
    wbs_id           VARCHAR(100) NOT NULL,
    cost_code        VARCHAR(50)  NOT NULL,
    date_id          DATE         NOT NULL,
    actual_cost      NUMERIC(15,2) NOT NULL,
    currency         VARCHAR(3)   NOT NULL DEFAULT 'USD',
    vendor_id        VARCHAR(50),
    invoice_ref      VARCHAR(100),
    modified_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version      BIGINT       NOT NULL DEFAULT 1,
    is_deleted       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- FACT_EVM_SNAPSHOT — Earned Value Management weekly snapshots
-- PV/EV/AC/BAC stored; SPI/CPI are derived but pre-computed here for DW compat
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouse.fact_evm_snapshot (
    snapshot_id           SERIAL       PRIMARY KEY,
    project_id            VARCHAR(50)  NOT NULL,
    date_id               DATE         NOT NULL,
    planned_value         NUMERIC(15,2) NOT NULL,     -- PV: BCWS
    earned_value          NUMERIC(15,2) NOT NULL,     -- EV: BCWP
    actual_cost           NUMERIC(15,2) NOT NULL,     -- AC: ACWP
    budget_at_completion  NUMERIC(15,2) NOT NULL,     -- BAC
    estimate_at_completion NUMERIC(15,2),             -- EAC (optional pre-compute)
    schedule_variance     NUMERIC(15,2),              -- SV = EV - PV
    cost_variance         NUMERIC(15,2),              -- CV = EV - AC
    spi                   NUMERIC(8,4),               -- SPI = EV / PV
    cpi                   NUMERIC(8,4),               -- CPI = EV / AC
    percent_complete      NUMERIC(5,2),
    modified_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version           BIGINT       NOT NULL DEFAULT 1,
    is_deleted            BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- Indexes for incremental load watermark queries
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dim_project_modified   ON warehouse.dim_project   (modified_at);
CREATE INDEX IF NOT EXISTS idx_dim_wbs_modified        ON warehouse.dim_wbs       (modified_at);
CREATE INDEX IF NOT EXISTS idx_dim_employee_modified   ON warehouse.dim_employee  (modified_at);
CREATE INDEX IF NOT EXISTS idx_dim_cost_code_modified  ON warehouse.dim_cost_code (modified_at);
CREATE INDEX IF NOT EXISTS idx_fact_budget_modified    ON warehouse.fact_budget   (modified_at);
CREATE INDEX IF NOT EXISTS idx_fact_timesheet_modified ON warehouse.fact_timesheet (modified_at);
CREATE INDEX IF NOT EXISTS idx_fact_actuals_modified   ON warehouse.fact_cost_actuals (modified_at);
CREATE INDEX IF NOT EXISTS idx_fact_evm_modified       ON warehouse.fact_evm_snapshot (modified_at);

-- Grant read to reader role
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO dar_dw_reader;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA warehouse TO dar_dw_reader;
