$ErrorActionPreference = "Stop"

Write-Host "1. Resetting volumes..."
docker compose -f docker-compose.yml -f docker-compose.uc1.yml -f docker-compose.uc2.yml -f docker-compose.governance.yml -f docker-compose.observability.yml -f docker-compose.cicd.yml down -v --remove-orphans

Write-Host "2. Generating configs"
docker run --rm -v ${PWD}:/repo -w /repo python:3.11-slim bash -c "apt-get update && apt-get install -y gettext-base && bash scripts/generate-secrets.sh && bash scripts/generate-configs.sh"

Write-Host "3. Starting up-lite..."
docker compose -f docker-compose.yml -f docker-compose.uc1.yml -f docker-compose.uc2.yml up -d

Write-Host "Waiting 60 seconds for services to become healthy..."
Start-Sleep -Seconds 60

Write-Host "4. Bootstrapping stack..."
.\scripts\bootstrap.ps1

Write-Host "5. Running Gate Test..."
docker run --rm -t --network dar-lakehouse_default --env-file .env -e "PG_DW_HOST=postgres-dw" -e "PG_DW_PORT=5432" -e "PG_DW_HOST_ACCESS=dar-postgres-dw" -e "TRINO_HOST_ACCESS=dar-trino" -e "TRINO_PORT=8080" -v ${PWD}:/repo -w /repo python:3.11-slim bash -c "pip install --quiet trino requests psycopg2-binary && python -u tests/uc2/test_m2_gate.py"

Write-Host "--- TEST COMPLETE ---"
