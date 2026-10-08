#!/usr/bin/env bash
# =============================================================================
# scripts/generate-configs.sh
# Generates service config files from *.template sources, substituting
# environment variables. Must run BEFORE `docker compose up`.
# Called automatically by `make up` and `make up-lite`.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load .env if present
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  source "${ROOT}/.env"
  set +a
fi

# Require envsubst (shipped with gettext-base on Debian/Ubuntu)
if ! command -v envsubst &>/dev/null; then
  echo "Installing envsubst (gettext-base)..."
  sudo apt-get install -y -qq gettext-base 2>/dev/null || \
    brew install gettext 2>/dev/null || \
    { echo "ERROR: envsubst not found and could not be installed"; exit 1; }
fi

generate() {
  local template="$1"
  local output="$2"
  mkdir -p "$(dirname "${output}")"
  envsubst < "${template}" > "${output}"
  echo "  ✓ ${output}"
}

echo "=== Generating service configs from templates ==="

# SeaweedFS S3 identity config
generate \
  "${ROOT}/infra/seaweedfs/s3.json.template" \
  "${ROOT}/infra/seaweedfs/s3.json"

# Trino Iceberg catalog (has S3 credentials)
generate \
  "${ROOT}/infra/trino/catalog/iceberg.properties.template" \
  "${ROOT}/infra/trino/catalog/iceberg.properties"

# OpenSearch Dashboards (has admin password)
generate \
  "${ROOT}/infra/opensearch/opensearch_dashboards.yml.template" \
  "${ROOT}/infra/opensearch/opensearch_dashboards.yml"

# Trino PostgreSQL catalog (DAR_DW source — password from .env)
generate \
  "${ROOT}/infra/trino/catalog/postgres.properties.template" \
  "${ROOT}/infra/trino/catalog/postgres.properties"

echo "=== Config generation complete ==="
