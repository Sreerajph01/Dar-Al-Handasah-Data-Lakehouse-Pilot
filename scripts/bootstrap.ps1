$ErrorActionPreference = "Stop"

# Load .env
Get-Content .env | Foreach-Object {
    if ($_ -match '^(.*?)=(.*)$') {
        Set-Item -Path "Env:\$($Matches[1])" -Value $Matches[2]
    }
}

$env:ENVIRONMENT = "dev"
$env:TF_VAR_s3_access_key = $env:S3_ACCESS_KEY
$env:TF_VAR_s3_secret_key = $env:S3_SECRET_KEY

Write-Host "--- Running OpenTofu apply ---"
docker run --rm --network dar-lakehouse_default -e TF_VAR_s3_access_key=$env:S3_ACCESS_KEY -e TF_VAR_s3_secret_key=$env:S3_SECRET_KEY -e ENVIRONMENT=dev -v "$($PWD.Path)\tofu\envs\dev:/workspace" -w /workspace --entrypoint sh ghcr.io/opentofu/opentofu:1.8.3 -c "tofu init -upgrade && tofu apply -auto-approve"

Write-Host "--- Initialising Lakekeeper ---"
try {
    Invoke-RestMethod -Uri "http://localhost:8181/management/v1/bootstrap" -Method Post -Body '{"accept-terms-of-use": true}' -ContentType "application/json"
} catch {
    Write-Host "Lakekeeper already bootstrapped or error: $_"
}

Write-Host "--- Creating Iceberg catalog structure ---"
docker run --rm --network dar-lakehouse_default --env-file .env -v ${PWD}:/repo -w /repo python:3.11-slim bash -c "pip install --quiet boto3==1.35.44 requests && python init_all.py && export S3_ENDPOINT=http://seaweedfs-s3:8333 LAKEKEEPER_CATALOG_URI=http://lakekeeper:8181 && python scripts/setup-iceberg-catalog.py"
Write-Host "--- Restarting Trino to pick up updated Iceberg catalog config ---"
docker restart dar-trino

Write-Host "--- Registering Airflow connections ---"
docker run --rm --network dar-lakehouse_default --env-file .env -v ${PWD}:/repo -w /repo python:3.11-slim bash -c "apt-get update && apt-get install -y curl && export AIRFLOW_URL=http://dar-airflow-webserver:8080 && bash scripts/register-airflow-connections.sh"

Write-Host "--- Seeding DAR_DW ---"
docker run --rm --network dar-lakehouse_default --env-file .env -v ${PWD}:/repo -w /repo python:3.11-slim bash -c "pip install --quiet psycopg2-binary && python uc2-warehouse-migration/sources/dar_dw/seed.py --scale small"
