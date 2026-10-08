-- =============================================================================
-- infra/postgres/init-meta-dbs.sql
-- Creates Lakekeeper and OpenMetadata databases and roles inside postgres-meta.
-- Executed once by Docker entrypoint (idempotent via DO $$ blocks).
-- =============================================================================

-- Lakekeeper DB
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = current_setting('env.lakekeeper_db_user', true)) THEN
    -- We read from env vars set by Docker; fall back to environment variables
    NULL;
  END IF;
END $$;

-- Create lakekeeper role + DB (using shell env vars passed via POSTGRES_* mechanism)
DO $$
DECLARE
  v_user  text := current_setting('lakekeeper.db_user',  true);
  v_pass  text := current_setting('lakekeeper.db_pass',  true);
  v_db    text := current_setting('lakekeeper.db_name',  true);
BEGIN
  -- Fallback: these are set by the entrypoint env vars
  v_user  := COALESCE(v_user,  'lakekeeper');
  v_pass  := COALESCE(v_pass,  'lakekeeper_pw');
  v_db    := COALESCE(v_db,    'lakekeeper');
END $$;

-- Simpler approach: use shell substitution baked in by docker entrypoint
-- The actual dynamic creation happens via the shell script below.
-- This file intentionally uses \gset or psql variables not available here;
-- we use a companion shell script instead.
SELECT 1; -- placeholder; real init via init-meta-dbs.sh
