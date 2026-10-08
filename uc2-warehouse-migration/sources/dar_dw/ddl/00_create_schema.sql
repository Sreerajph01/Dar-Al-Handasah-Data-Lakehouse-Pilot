-- =============================================================================
-- 00_create_schema.sql
-- Creates the warehouse schema and read-only user.
-- Runs automatically on first `postgres-dw` start via initdb.d.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS warehouse;

-- Read-only role for Airflow dlt pipelines (principle of least privilege)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dar_dw_reader') THEN
    CREATE ROLE dar_dw_reader LOGIN PASSWORD 'CHANGE_ME_DW';
  END IF;
END$$;

GRANT USAGE ON SCHEMA warehouse TO dar_dw_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse
  GRANT SELECT ON TABLES TO dar_dw_reader;
