# =============================================================================
# Makefile — dar-lakehouse-pilot
# MUST be run from inside WSL2 (not Windows CMD/PowerShell).
# See README.md §WSL2 Setup.
# =============================================================================

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

include .env
export

# ─── Compose files ────────────────────────────────────────────────────────────
COMPOSE_CORE        := docker-compose.yml
COMPOSE_UC1         := docker-compose.uc1.yml
COMPOSE_UC2         := docker-compose.uc2.yml
COMPOSE_GOV         := docker-compose.governance.yml
COMPOSE_OBS         := docker-compose.observability.yml
COMPOSE_CICD        := docker-compose.cicd.yml
COMPOSE_BENCH       := docker-compose.benchmark.yml
COMPOSE_OPT_SQL     := docker-compose.opt-sqlserver.yml
COMPOSE_OPT_STREAM  := docker-compose.opt-streaming.yml

# Full demo stack (all core profiles)
COMPOSE_FULL := -f $(COMPOSE_CORE) -f $(COMPOSE_UC1) -f $(COMPOSE_UC2) \
                -f $(COMPOSE_GOV) -f $(COMPOSE_OBS) -f $(COMPOSE_CICD)

# Lite stack (16 GB machine)
COMPOSE_LITE := -f $(COMPOSE_CORE) -f $(COMPOSE_UC1) -f $(COMPOSE_UC2)

# Python venv for test tooling
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv up up-lite down seed reset verify \
        lint-branding lint-code lint \
        s3-conformance smoke-m1 \
        backup restore \
        simulate-day \
        benchmark \
        licenses \
        generate-secrets \
        tofu-init tofu-plan tofu-apply \
        verify-opa \
        demo clean

help: ## Show this help message
	@echo ""
	@echo "  dar-lakehouse-pilot — Makefile targets"
	@echo "  ════════════════════════════════════════"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-25s %s\n", $$1, $$2}'
	@echo ""

# ─── Environment setup ────────────────────────────────────────────────────────
generate-secrets: ## Generate .env from .env.example with random secrets
	@bash scripts/generate-secrets.sh

venv: ## Create Python virtualenv for test tooling
	@python3 -m venv $(VENV)
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install --quiet \
	  boto3==1.35.44 \
	  trino==0.329.0 \
	  pytest==8.3.3 \
	  pyyaml==6.0.2 \
	  pip-licenses==5.0.0
	@echo "✓ venv ready"

# ─── Service lifecycle ────────────────────────────────────────────────────────
up: generate-secrets ## Start full demo stack (all core profiles)
	@echo "Starting full demo stack..."
	@bash scripts/generate-configs.sh
	@docker compose $(COMPOSE_FULL) up -d --build
	@echo "Waiting for services to be healthy..."
	@bash scripts/wait-for-services.sh \
	  localhost:$(SEAWEEDFS_S3_PORT) \
	  localhost:$(LAKEKEEPER_PORT) \
	  localhost:$(TRINO_PORT) \
	  localhost:$(KEYCLOAK_HTTP_PORT) \
	  localhost:$(AIRFLOW_PORT) \
	  localhost:$(OPENSEARCH_PORT)
	@echo "✓ Stack is up"

up-lite: generate-secrets ## Start lite stack (core + UC1 + UC2 only, ~13 GB RAM, 16 GB machines)
	@echo "Starting lite stack (no governance/observability/cicd)..."
	@bash scripts/generate-configs.sh
	@docker compose $(COMPOSE_LITE) up -d
	@bash scripts/wait-for-services.sh \
	  localhost:$(SEAWEEDFS_S3_PORT) \
	  localhost:$(LAKEKEEPER_PORT) \
	  localhost:$(TRINO_PORT) \
	  localhost:$(AIRFLOW_PORT)
	@echo "✓ Lite stack is up"

down: ## Stop all services (preserves volumes)
	@docker compose $(COMPOSE_FULL) down

reset: ## Destroy all volumes and restart from scratch
	@echo "⚠  This will DELETE all data volumes. Proceeding in 5s..."
	@sleep 5
	@docker compose $(COMPOSE_FULL) down -v --remove-orphans

# ─── Seeding and bootstrap ────────────────────────────────────────────────────
seed: venv ## Seed all data: bootstrap, create buckets, init Iceberg catalog, load demo data
	@echo "=== Seeding ==="
	@source .env && bash scripts/bootstrap.sh
	@echo "✓ Seed complete"

# ─── OpenTofu ─────────────────────────────────────────────────────────────────
tofu-init: ## Initialise OpenTofu providers
	@docker run --rm \
	  --network dar-lakehouse_default \
	  -v "$(PWD)/tofu/envs/$(ENVIRONMENT)":/workspace \
	  -w /workspace \
	  ghcr.io/opentofu/opentofu:$(TOFU_VERSION) init

tofu-plan: ## Show OpenTofu plan (no changes applied)
	@docker run --rm \
	  --network dar-lakehouse_default \
	  -e AWS_ACCESS_KEY_ID="$(S3_ACCESS_KEY)" \
	  -e AWS_SECRET_ACCESS_KEY="$(S3_SECRET_KEY)" \
	  -v "$(PWD)/tofu/envs/$(ENVIRONMENT)":/workspace \
	  -w /workspace \
	  ghcr.io/opentofu/opentofu:$(TOFU_VERSION) plan

tofu-apply: ## Apply OpenTofu (create buckets, Keycloak realm, Kong routes)
	@docker run --rm \
	  --network dar-lakehouse_default \
	  -e AWS_ACCESS_KEY_ID="$(S3_ACCESS_KEY)" \
	  -e AWS_SECRET_ACCESS_KEY="$(S3_SECRET_KEY)" \
	  -v "$(PWD)/tofu/envs/$(ENVIRONMENT)":/workspace \
	  -w /workspace \
	  ghcr.io/opentofu/opentofu:$(TOFU_VERSION) apply -auto-approve

# ─── Tests and verification ───────────────────────────────────────────────────
s3-conformance: venv ## Run S3 conformance matrix → docs/S3_CONFORMANCE.md
	@echo "=== S3 Conformance Test ==="
	@$(PYTHON) tests/s3_conformance/test_s3_conformance.py

smoke-m1: venv ## M1 gate: Iceberg create/read/write/delete via Trino on SeaweedFS
	@echo "=== M1 Iceberg Smoke Test ==="
	@$(PYTHON) tests/smoke/test_m1_iceberg.py

verify-opensearch: venv ## M1 gate: OpenSearch k-NN + Hybrid Search
	@echo "=== OpenSearch 3.x k-NN Test ==="
	@$(PYTHON) tests/smoke/test_opensearch_knn.py

lint-branding: ## Scan repo for forbidden branding / proprietary terms
	@bash tests/branding_lint/check_branding.sh

lint-code: ## Run sqlfluff, ruff, yamllint
	@echo "--- ruff ---"
	@docker run --rm -v "$(PWD)":/repo -w /repo \
	  ghcr.io/astral-sh/ruff:0.7.0 check --select=E,W,F --ignore=E501 .
	@echo "--- yamllint ---"
	@docker run --rm -v "$(PWD)":/repo -w /repo \
	  cytopia/yamllint:1.35.1 -d relaxed \
	  docker-compose.yml docker-compose.*.yml infra/

lint: lint-branding lint-code ## Run all linters

verify-opa: ## Run opa test on policy bundle (bootstrap, allow-all)
	@docker run --rm \
	  -v "$(PWD)/infra/opa":/policies \
	  openpolicyagent/opa:$(OPA_VERSION) test /policies -v

smoke-m2: venv ## M2 gate: full and incremental load
	@echo "=== M2 Gate Test ==="
	@docker run --rm --network dar-lakehouse_default --env-file .env \
	  -e "PG_DW_HOST=postgres-dw" -e "PG_DW_PORT=5432" -e "PG_DW_HOST_ACCESS=dar-postgres-dw" \
	  -e "TRINO_HOST_ACCESS=dar-trino" -e "TRINO_PORT=8080" \
	  -v "$(PWD)":/repo -w /repo python:3.11-slim bash -c "pip install --quiet pytest trino requests psycopg2-binary && pytest -q tests/uc2/test_lakekeeper_contract.py && python tests/uc2/test_m2_gate.py"

smoke-m3: venv ## M3 gate: Silver/Gold correctness, Airflow DAG, Demos
	@echo "=== M3 Gate Test ==="
	@docker run --rm --network dar-lakehouse_default --env-file .env \
	  -e "PG_DW_HOST=postgres-dw" -e "PG_DW_PORT=5432" -e "PG_DW_HOST_ACCESS=dar-postgres-dw" \
	  -e "TRINO_HOST_ACCESS=dar-trino" -e "TRINO_PORT=8080" \
	  -v "$(PWD)":/repo -w /repo python:3.11-slim bash -c "pip install --quiet pytest trino requests psycopg2-binary && python tests/uc2/test_m3_gate.py"

verify: venv lint-branding s3-conformance smoke-m1 verify-opensearch verify-opa traceability smoke-m2 smoke-m3 ## Full verification suite (M1, M2 and M3 gates)
	@echo ""
	@echo "✅ make verify PASSED"

# ─── Data simulation ──────────────────────────────────────────────────────────
traceability: venv ## Parse RFP requirements → docs/rfp/TRACEABILITY.md + coverage.csv
	@echo "=== Traceability Check ==="
	@$(PYTHON) tests/traceability/check_traceability.py

simulate-day: ## Advance the day simulator (inserts/updates/deletes in all sources)
	@$(PYTHON) data-gen/uc2/simulate_day.py

# ─── Benchmark ───────────────────────────────────────────────────────────────
benchmark: ## Run benchmark suite → docs/BENCHMARK_REPORT.md
	@docker compose -f $(COMPOSE_CORE) -f $(COMPOSE_BENCH) up -d
	@$(PYTHON) benchmark/report_generator.py

# ─── Licence audit ───────────────────────────────────────────────────────────
licenses: venv ## Generate LICENSES.md via pip-licenses + Trivy
	@echo "=== Licence Audit ==="
	@$(PYTHON) tests/licence_gate/check_licences.py
	@echo "✓ LICENSES.md generated"

# ─── Backup and restore ───────────────────────────────────────────────────────
backup: ## Backup SeaweedFS volumes + Postgres + Keycloak realm
	@bash scripts/backup.sh

restore: ## Restore from latest backup
	@bash scripts/restore.sh

# ─── Demo ────────────────────────────────────────────────────────────────────
demo: ## Step through DEMO_SCRIPT.md interactively
	@bash scripts/run-demo.sh

clean: ## Remove Python venv and generated files
	@rm -rf $(VENV) .pytest_cache __pycache__
	@echo "✓ Cleaned"
