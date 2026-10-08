#!/usr/bin/env bash
set -e

echo "=== Branding Lint ==="
bash tests/branding_lint/check_branding.sh

echo "=== S3 Conformance ==="
python tests/s3_conformance/test_s3_conformance.py

echo "=== M1 Iceberg Smoke Test ==="
python tests/smoke/test_m1_iceberg.py

echo "=== OpenSearch 3.x k-NN Test ==="
python tests/smoke/test_opensearch_knn.py

echo "=== OPA Policies Test (Bootstrap / Allow-All) ==="
# Note: Windows path for docker volume mount in git bash
docker run --rm -v "/c/Users/sharidass/.gemini/antigravity-ide/scratch/dar-lakehouse-pilot/infra/opa:/policies" openpolicyagent/opa:0.68.0 test /policies -v

echo "=== Traceability Check ==="
python tests/traceability/check_traceability.py

echo "=== Docker Stats ==="
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}"
