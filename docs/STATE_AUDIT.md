# State Audit (P0)

**Audit date:** 2026-10-09  
**Repo:** `C:\dar-lakehouse-pilot`  
**Git HEAD:** `363ea88` (tag `baseline` only; no phase tags yet)  
**Stack runtime:** All `dar-*` containers **stopped** (~30 hours since last run). Unrelated stacks still running: `airflow-intro_*` (host **8080**), `local-control-plane` (kind).

Evidence for this audit lives under `evidence/2026-10-09/p0-*.log` (captured via `log_evidence.ps1` and one inline GPU pull).

---

## Workspace inventory (verified)

| Area | Present | Notes |
|------|---------|--------|
| Entry point | `dar.ps1` | Targets: up, up-lite, down, reset, seed, health, verify, simulate-day, backup (stub), restore (stub), licenses, lint-*, s3-conformance, smoke-m1/m2/m3, benchmark, demo (throws) |
| Evidence helper | `log_evidence.ps1` | Tees command output to `evidence/<date>/<step>.log` |
| Compose | `docker-compose.yml` + uc1, uc2, governance, observability, cicd, benchmark | **37 services** in full profile (`p0-compose-services.log`) |
| UC2 | `uc2-warehouse-migration/` | dags, dlt ingestion, dbt models, mocks, api, nl2sql stubs |
| UC1 | `uc1-search/` | api, ui skeleton, ingestion paths |
| IaC | `tofu/envs/dev` | OpenTofu modules (buckets, kong, keycloak) |
| Tests | `tests/smoke`, `tests/s3_conformance`, `tests/uc2/test_m2_gate.py`, `test_m3_gate.py` | **No** `test_p2_gate.py` / `test_p3_gate.py` yet (phase naming debt) |
| RFP source | `docs/source/RFP_tooling.xlsx` | Present |
| RFP parse | `docs/rfp/requirements.yaml` | **97 rows** re-parsed 2026-10-09 (`p0-rfp-parse.log`; Nb 1 and 97 spot-checked in output) |
| Docs | `STACK.md`, `README.md`, `KNOWN_GAPS.md`, partial `S3_CONFORMANCE.md` | `docs/PROGRESS.md` created this session |
| Secrets | `.env` (gitignored), `.env.example` | Generated configs under `infra/` (some gitignored) |
| Junk paths | `C?...?uc2-warehouse-migration?dbt?models?*` | Duplicate/mojibake directories alongside real `uc2-warehouse-migration/dbt/` — **remove later** (P12) |
| Host Python | Not on PATH | Use containerized Python (as `dar.ps1` does) |

---

## Docker inventory (verified 2026-10-09)

### Project volumes (`dar-lakehouse_*`)

16 named volumes exist (postgres x3, seaweedfs x3, opensearch, ollama, superset, grafana, prometheus, gitea x2, samba x2, airflow-logs). See `p0-docker-inventory.log`.

### `dar-*` container last known status (`p0-dar-containers.log`)

| Container | Last status | Decision |
|-----------|-------------|----------|
| seaweedfs-* (master, volume, filer, s3) | Exited 0/137 | **Keep** — retest S3 on 8333 when up |
| lakekeeper, lakekeeper-init | Exited 0 | **Keep** |
| trino | Exited 143 | **Keep** — fix health/startup in P1 |
| postgres-* | Exited 0 | **Keep** |
| opa, kong, mailpit, samba, tika | Exited 0/143 | **Keep** — healthchecks need P1 pass |
| opensearch, dashboards | Exited 143 | **Fix** healthchecks / heap / vm.max_map_count |
| keycloak | Exited 143 | **Fix** health endpoint vs compose healthcheck |
| airflow-* | Exited 143 (init 0) | **Keep** — verify dbt in scheduler image at P1 |
| ollama, ollama-pull | Exited 0 / **Exited 1** | **Fix** model pull + GPU reservation |
| openmetadata | Exited 1 | **Fix** (known verifySSL / deps) |
| openmetadata-ingestion | Exited 2 | **Fix** `PIPELINE_SERVICE_CLIENT_VERIFY_SSL=no-ssl` |
| d365-mock, sharepoint-mock | Exited 0 | **Keep** |
| data-api, search-api, nl2sql | Exited 0/137 | **Rebuild** — likely placeholders (P5–P6) |
| superset | Exited 137 | **Fix** startup / deps |
| gitea, gitea-runner | Exited 0/143 | **Keep** — runner registration at P1 |
| prometheus, grafana, fluent-bit, cadvisor | Exited 0/137 | **Keep** |
| tofu-seed | Exited 0 | **Keep** |

### s3-proxy removal

- **No container named `s3-proxy`** in `docker ps -a` (`p0-s3-proxy-check.log`).
- S3 path is **`dar-seaweedfs-s3`** (SeaweedFS 3.75), port **8333** per stack design.
- Legacy **`lakehouse_seaweedfs_ui_proxy`** (old repo) still exists **stopped** — not used by this compose; optional cleanup in P12.

---

## Environment / hardware (verified)

| Check | Result | Evidence |
|-------|--------|----------|
| Docker memory limit | **31.06 GiB** (not yet 48 GiB) | `p0-docker-info.log` |
| Docker CPUs | 22 reported | `p0-docker-info.log` |
| WSL config written | `memory=48GB`, `processors=14`, `swap=16GB`, `vm.max_map_count=262144` | `p0-wslconfig.log` |
| GPU passthrough | **PASS** — `nvidia-smi` inside `nvidia/cuda:12.4.1-base-ubuntu22.04` | `p0-gpu-nvidia-smi.log` |
| GPU model | **NVIDIA GeForce RTX 4070 Laptop GPU**, 8188 MiB VRAM (spec mentioned 4060; hardware is 4070) | same |
| Host port conflict | **`airflow-intro-airflow-apiserver-1` → 8080** | `p0-host-port-conflicts.log` — may affect SeaweedFS volume **status** port mapping; resolve before/full `dar.ps1 up` |

**USER ACTION REQUIRED:** Apply `.wslconfig` with `wsl --shutdown`, then restart Docker Desktop. Re-run `docker info` and confirm **Total Memory ≈ 48 GiB** before treating P0 memory gate as green.

---

## Component decisions (keep / fix / rebuild / remove-later)

| Component | Version (pinned in repo) | Profile | Decision |
|-----------|--------------------------|---------|----------|
| SeaweedFS | 3.75 | core | **Keep** — blocking S3/Iceberg tests on 8333 |
| Lakekeeper | v0.13.6 | core | **Keep** |
| Iceberg + Trino | Trino 455 | core | **Keep** |
| OPA | 0.68.0 | core | **Keep** |
| Keycloak | 26.0.7 | core | **Fix** health + realm bootstrap |
| PostgreSQL | 16.4 | core | **Keep** |
| Airflow | 2.10.2 + dbt-trino 1.8.3 in pip extras | core | **Fix** — prove `dbt --version` in scheduler (was reported missing historically) |
| OpenSearch + Dashboards | 3.3.2 / 3.3.0 | core | **Fix** healthchecks + heap |
| Ollama | 0.3.14 | core | **Fix** pull + GPU; pin models Qwen2.5-7B Q4 + nomic-embed-text |
| Tika | 2.9.2.1-full | uc1 | **Fix** healthcheck |
| Samba | dperson/samba amd64 | uc1 | **Keep** — host **1445** |
| Kong | 3.8.0 | core | **Keep** |
| Superset | 4.1.1 | core | **Fix** |
| OpenMetadata + ingestion | 2.0.3 | governance | **Fix** SSL env + OpenSearch 3.x |
| FastAPI mocks | d365, sharepoint | uc2 | **Keep** — extend for P2 |
| data-api / search-api / nl2sql | built images | serve | **Rebuild** (stubs) |
| Gitea + act_runner | 1.22.3 / 0.2.11 | cicd | **Fix** runner online at P1 |
| Prometheus/Grafana/Fluent Bit/cAdvisor | pinned | observability | **Keep** |
| Mailpit | v1.21.1 | core | **Keep** |
| Locust | in benchmark compose | benchmark | **Keep** |
| Makefile | thin wrapper | optional | **Keep** — PowerShell is canonical |
| `backup/` bind tree | seaweedfs volume files | — | **Remove-later** if not referenced by scripts (P12) |
| Root-level scratch scripts | `test_s3_*.py`, `run_all.ps1`, etc. | — | **Review** in P12 |

---

## Prior-session claims — status

| Claim | Status |
|-------|--------|
| M2/M3 gates passed | **UNVERIFIED** (no evidence from reset→up→seed→verify today) |
| Iceberg 11/11 smoke | **UNVERIFIED** until `.\dar.ps1 smoke-m1` on live stack |
| OpenSearch k-NN 8/8 | **UNVERIFIED** until `verify-opensearch` on live stack |
| OPA mask/RLS | **UNVERIFIED** until live Trino + `verify-opa` |
| S3 conformance matrix | **UNVERIFIED** — retest in P1 → `docs/S3_CONFORMANCE.md` |
| Backup/restore | **FAIL** — `dar.ps1 backup`/`restore` exit 2 (scripts absent) |
| OpenMetadata ingestion | **FAIL** last run (Exited 2) |
| ollama-pull | **FAIL** last run (Exited 1) |
| RFP 97 requirements | **VERIFIED** 2026-10-09 (`p0-rfp-parse.log`) |
| GPU passthrough | **VERIFIED** 2026-10-09 |
| s3-proxy not required | **VERIFIED** — no s3-proxy container |

---

## P0 gate checklist

| Gate item | Pass? | Evidence |
|-----------|-------|----------|
| STATE_AUDIT from real commands | Yes | This file + `evidence/2026-10-09/p0-*` |
| `dar.ps1` + evidence helper | Yes | `p0-dar-help.log`, repo files |
| `.wslconfig` created | Yes | `p0-wslconfig.log` |
| `docker info` ≥48 GiB RAM | **No** | `p0-docker-info.log` — pending WSL restart |
| GPU `nvidia-smi` in container | Yes | `p0-gpu-nvidia-smi.log` |
| s3-proxy removed / unused | Yes | `p0-s3-proxy-check.log` |
| RFP xlsx → 97 rows | Yes | `p0-rfp-parse.log` |

**P0 overall:** **RED** on Docker memory until you restart WSL/Docker Desktop. All other P0 items green.
