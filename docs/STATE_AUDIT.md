# State Audit

## Actual Repo Tree
See `tree /F` output (condensed):
- `Makefile`, `docker-compose.yml`, `docker-compose.*.yml`
- `tests/`
  - `uc2/test_m2_gate.py`
  - `s3_conformance/test_s3_conformance.py`
- `uc2-warehouse-migration/`
  - `sources/` (dar_dw, d365_mock, sharepoint_mock)
  - `dags/`, `dbt/`, `ingestion/`

## Components with Pinned Versions & Profiles
| Component | Pinned Version | Profile |
|-----------|----------------|---------|
| Airflow | 2.10.2 | Core |
| Superset | 4.1.1 | Core |
| Tika | 2.9.2.1-full | Core |
| Mailpit | v1.21.1 | Core |
| SeaweedFS | 3.75 | Core |
| OpenMetadata | 2.0.3 | Governance |
| Samba | amd64 | Core |
| Fluent-bit | 3.1.9 | Observability |
| cAdvisor | v0.50.0 | Observability |
| Gitea / Act Runner | 1.22.3 / 0.2.11 | CICD |
| Grafana | 11.2.2 | Observability |
| Kong | 3.8.0 | Core (DB-less) |
| Locust | 2.31.6 | Benchmark |
| Ollama | 0.3.14 | Core |
| OPA | 0.68.0 | Core |
| OpenSearch | 3.3.2 | Core |
| OpenSearch Dashboards | 3.3.0 | Core |
| Postgres | 16.4 | Core |
| Prometheus | v2.54.1 | Observability |
| Keycloak | 26.0.7 | Core |
| Lakekeeper | v0.13.6 | Core |
| Trino | 455 | Core |

## Test Results
- **Image-tag check**: Passed. All pinned image tags exist on Docker Hub/Quay/GCR.
- **RFP xlsx parsing check**: Passed. parsed 97 items to `requirements.yaml` and deleted invented items logic.
- **M2 Gate Test**: Currently running.

## Discrepancies
- The Windows host has no `make` inside WSL out-of-the-box (wsl just runs docker-desktop backend). Resolved by running PowerShell equivalent logic.
- Docker-in-docker requirement for `bootstrap.sh` execution needed socket mounting and `docker.io` install in the python slim container.
- `postgres-meta` healthcheck passed during temporary bootstrap, causing `lakekeeper-init` to fail with timeouts. Resolved by binding the healthcheck to `127.0.0.1`.
- `Locust` is correctly in the benchmark profile now.
- `Kong` is correctly in the core profile.

## Unable to Verify
- Long-term memory idle usage (Kong ≈1.5GB) was investigated (set to 64MB cache and 1 worker process) but wait times prohibit long-term memory profiling.
- OpenMetadata 2.0.3 compatibility with OpenSearch 3.3.2 will be verified if M3 runs or if explicitly required.

## M2 Close-out Debt
Deadline: Before M4 starts.

- run the gate through `make verify` and a second `make seed` on the same stack (not run_all.ps1)
- evidence of the nine DAR_DW tables, columns and `small`-scale row counts
- seeded DQ issues counted in the source and shown unmodified in Bronze
- D365 OData (pagination and $filter) and SharePoint list/delta endpoint responses
- DAG run IDs and per-task states proving dlt for all three sources
- Bronze audit columns and the watermark table
- per-table, per-source expected vs actual appended rows, and soft-delete assertions (both views, plus an incremental delete of an existing row)
- STATIC_TABLES documented with a reason, and a test or gap entry for a late-corrected static row
- proof that gate tests FAIL/SKIP (never PASS) on caught errors
- RFP xlsx parse (no embedded fallback), image-tag check for images not yet started, full docker stats total
