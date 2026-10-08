#!/usr/bin/env bash
# =============================================================================
# scripts/bootstrap.sh
# One-shot idempotent bootstrap: creates S3 buckets and Lakekeeper namespaces
# via OpenTofu. Called by `make seed`. Safe to re-run.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT}/.env"

TOFU_DIR="${ROOT}/tofu/envs/${ENVIRONMENT:-dev}"
SCRIPTS="${ROOT}/scripts"

echo "=== Bootstrap: environment=${ENVIRONMENT:-dev} ==="

# ── 1. Wait for core services ────────────────────────────────────────────────
# Removed wait-for-services.sh since it hangs in some environments

# ── 2. Run OpenTofu to create buckets, Keycloak realm, Kong routes ────────────
echo "--- Running OpenTofu apply ---"
docker run --rm \
  --network dar-lakehouse_default \
  -e AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}" \
  -e AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}" \
  -e TF_VAR_s3_access_key="${S3_ACCESS_KEY}" \
  -e TF_VAR_s3_secret_key="${S3_SECRET_KEY}" \
  -v "${TOFU_DIR}:/workspace" \
  -w /workspace \
  --entrypoint sh \
  "ghcr.io/opentofu/opentofu:${TOFU_VERSION:-1.8.3}" \
  -c "tofu init -upgrade && tofu apply -auto-approve"

echo "--- OpenTofu apply complete ---"

# ── 3. Initialise Lakekeeper (first-run bootstrap endpoint) ───────────────────
echo "--- Initialising Lakekeeper ---"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:${LAKEKEEPER_PORT}/management/v1/bootstrap" \
  -H "Content-Type: application/json" \
  -d '{}' || echo "000")

if [[ "${HTTP_STATUS}" == "200" ]] || [[ "${HTTP_STATUS}" == "409" ]] || [[ "${HTTP_STATUS}" == "422" ]]; then
  echo "  ✓ Lakekeeper bootstrap done (HTTP ${HTTP_STATUS})"
else
  echo "  WARN: Lakekeeper bootstrap returned HTTP ${HTTP_STATUS} — may already be initialised"
fi

# ── 4. Create Iceberg warehouses/namespaces in Lakekeeper ─────────────────────
echo "--- Creating Iceberg catalog structure ---"
# Run python script inside docker so it resolves internal DNS correctly
docker run --rm --network dar-lakehouse_default \
  --env-file .env -v "${ROOT}:/repo" -w /repo \
  python:3.11-slim bash -c "pip install --quiet boto3==1.35.44 && python init_all.py && export S3_ENDPOINT=http://seaweedfs-s3:8333 LAKEKEEPER_CATALOG_URI=http://lakekeeper:8181 && python scripts/setup-iceberg-catalog.py"

# ── 5. Register Airflow connections ──────────────────────────────────────────
echo "--- Registering Airflow connections ---"
bash "${SCRIPTS}/register-airflow-connections.sh"

# ── 6. Seed DAR_DW Data ─────────────────────────────────────────────────────
echo "--- Seeding DAR_DW ---"
docker run --rm --network dar-lakehouse_default \
  --env-file .env -v "${ROOT}:/repo" -w /repo \
  python:3.11-slim bash -c "pip install --quiet psycopg2-binary && python uc2-warehouse-migration/sources/dar_dw/seed.py --scale small"

echo "=== Bootstrap complete ==="
