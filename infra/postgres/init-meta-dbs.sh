#!/usr/bin/env bash
# =============================================================================
# infra/postgres/init-meta-dbs.sh
# Docker entrypoint init script — creates Lakekeeper and OpenMetadata DBs.
# Runs as the postgres superuser inside the container on first start.
# =============================================================================
set -euo pipefail

# Variables injected by docker-compose environment
LAKEKEEPER_DB="${LAKEKEEPER_DB:-lakekeeper}"
LAKEKEEPER_DB_USER="${LAKEKEEPER_DB_USER:-lakekeeper}"
LAKEKEEPER_DB_PASSWORD="${LAKEKEEPER_DB_PASSWORD:-lakekeeper_pw}"

OM_DB="${OM_DB:-openmetadata_db}"
OM_DB_USER="${OM_DB_USER:-openmetadata}"
OM_DB_PASSWORD="${OM_DB_PASSWORD:-openmetadata_pw}"

create_db_and_user() {
  local db="$1"
  local user="$2"
  local pass="$3"

  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" -d "${POSTGRES_DB}" <<-EOSQL
    DO \$\$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${user}') THEN
        CREATE ROLE "${user}" LOGIN PASSWORD '${pass}';
      ELSE
        ALTER ROLE "${user}" WITH PASSWORD '${pass}';
      END IF;
    END
    \$\$;

    SELECT 'CREATE DATABASE "${db}" OWNER "${user}"'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db}')
    \gexec

    GRANT ALL PRIVILEGES ON DATABASE "${db}" TO "${user}";
EOSQL
  echo "  ✓ Database '${db}' and role '${user}' ready"
}

echo "=== Initialising auxiliary databases ==="
create_db_and_user "${LAKEKEEPER_DB}" "${LAKEKEEPER_DB_USER}" "${LAKEKEEPER_DB_PASSWORD}"
create_db_and_user "${OM_DB}" "${OM_DB_USER}" "${OM_DB_PASSWORD}"
echo "=== Auxiliary database init complete ==="
