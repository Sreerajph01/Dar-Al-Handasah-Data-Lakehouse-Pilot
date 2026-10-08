#!/usr/bin/env bash
# =============================================================================
# scripts/register-airflow-connections.sh
# Registers all Airflow connections idempotently via Airflow REST API.
# =============================================================================
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"

AIRFLOW_URL="${AIRFLOW_URL:-http://localhost:${AIRFLOW_PORT}}"
AUTH="admin:${AIRFLOW_WEBSERVER_SECRET:-admin}"

airflow_conn() {
  local conn_id="$1"
  local payload="$2"

  # Try to delete if exists (idempotent), then create
  curl -s -X DELETE \
    "${AIRFLOW_URL}/api/v1/connections/${conn_id}" \
    -u "${AUTH}" \
    -H "Content-Type: application/json" > /dev/null 2>&1 || true

  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${AIRFLOW_URL}/api/v1/connections" \
    -u "${AUTH}" \
    -H "Content-Type: application/json" \
    -d "${payload}")

  if [[ "${HTTP}" == "200" ]] || [[ "${HTTP}" == "201" ]]; then
    echo "  ✓ Connection '${conn_id}' registered"
  else
    echo "  WARN: '${conn_id}' returned HTTP ${HTTP}"
  fi
}

# PostgreSQL — meta
airflow_conn "postgres_meta" '{
  "connection_id": "postgres_meta",
  "conn_type": "postgres",
  "host": "'"${PG_META_HOST}"'",
  "port": '"${PG_META_PORT}"',
  "schema": "'"${PG_META_DB}"'",
  "login": "'"${PG_META_USER}"'",
  "password": "'"${PG_META_PASSWORD}"'"
}'

# PostgreSQL — DAR_DW
airflow_conn "postgres_dar_dw" '{
  "connection_id": "postgres_dar_dw",
  "conn_type": "postgres",
  "host": "'"${PG_DW_HOST}"'",
  "port": '"${PG_DW_PORT}"',
  "schema": "'"${PG_DW_DB}"'",
  "login": "'"${PG_DW_USER}"'",
  "password": "'"${PG_DW_PASSWORD}"'"
}'

# S3 / SeaweedFS
airflow_conn "s3_seaweedfs" '{
  "connection_id": "s3_seaweedfs",
  "conn_type": "aws",
  "extra": "{\"aws_access_key_id\": \"'"${S3_ACCESS_KEY}"'\", \"aws_secret_access_key\": \"'"${S3_SECRET_KEY}"'\", \"endpoint_url\": \"'"${S3_ENDPOINT}"'\", \"region_name\": \"'"${S3_REGION}"'\"}"
}'

# Trino
airflow_conn "trino_default" '{
  "connection_id": "trino_default",
  "conn_type": "trino",
  "host": "trino",
  "port": '"${TRINO_PORT}"',
  "schema": "'"${TRINO_DEFAULT_SCHEMA}"'"
}'

echo "Airflow connections registered."
