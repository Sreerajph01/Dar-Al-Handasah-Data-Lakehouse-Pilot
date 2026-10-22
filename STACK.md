# STACK.md — Component Manifest
# Dar Al Handasah Data Lakehouse Pilot
# Generated from M0 plan; updated at each milestone.
# ─────────────────────────────────────────────────────────────────────────────
# Version corrections vs M0 plan applied in M1:
#   • SeaweedFS: 3.73 → 3.75 (latest stable)
#   • Lakekeeper: 0.9.0 → 0.13.6 (latest stable)
#   • OpenMetadata: 1.5.9 → 2.0.3 (major version; requires OpenSearch 3.x)
#   • OpenSearch: 2.17.1 → 3.3.2 (required by OpenMetadata 2.0.3)
#   • Redis: REMOVED (RSALv2/SSPL — not OSI-approved)
#   • OpenSearch transport port: corrected 9600 → 9300
#   • Samba host port: corrected 445 → 1445 (Windows SMB conflict)
#   • Keycloak: 25.0.6 → 26.0.7 (latest stable)

## Supported commands

Run `.\dar.ps1 up`, `.\dar.ps1 down`, `.\dar.ps1 seed`, and `.\dar.ps1 health` from Windows PowerShell 5.1 or later. `dar.ps1` is the single implementation for lifecycle and verification commands; the optional Makefile forwards to it for Linux/WSL users.

`.\dar.ps1 down` preserves named volumes. `.\dar.ps1 reset -Force` prints the project volumes and then deletes them. Health checks probe application endpoints and Postgres, not just container state.

The historical `s3-proxy` container was a raw TCP forwarder to `dar-seaweedfs-s3:8333`. It had no repository references and is not part of this stack. S3 checks connect directly to the SeaweedFS gateway on port 8333.

## Core Profile (OSS, always started by `.\dar.ps1 up`)

| # | Capability | Component | Image/Package | Version | Licence | OSI | Port(s) | RAM Est. |
|---|---|---|---|---|---|---|---|---|
| 1 | Object storage master | **SeaweedFS** master | `chrislusf/seaweedfs` | `3.75` | Apache-2.0 | ✅ | 9333 | 256 MB |
| 2 | Object storage volume | **SeaweedFS** volume | `chrislusf/seaweedfs` | `3.75` | Apache-2.0 | ✅ | 8080 | 512 MB |
| 3 | Object storage filer | **SeaweedFS** filer | `chrislusf/seaweedfs` | `3.75` | Apache-2.0 | ✅ | 8888 | 256 MB |
| 4 | Object storage S3 GW | **SeaweedFS** S3 | `chrislusf/seaweedfs` | `3.75` | Apache-2.0 | ✅ | 8333 | 128 MB |
| 5 | Iceberg REST catalog | **Lakekeeper** | `quay.io/lakekeeper/catalog` | `v0.13.6` | Apache-2.0 | ✅ | 8181 | 512 MB |
| 6 | Distributed SQL | **Trino** | `trinodb/trino` | `455` | Apache-2.0 | ✅ | 18080 | 4 GB |
| 7 | Metadata DB | **PostgreSQL** (meta) | `postgres` | `16.4` | PostgreSQL | ✅ | 5432 | 256 MB |
| 8 | Airflow DB | **PostgreSQL** (airflow) | `postgres` | `16.4` | PostgreSQL | ✅ | 5433 | 128 MB |
| 9 | Source DW | **PostgreSQL** (DAR_DW) | `postgres` | `16.4` | PostgreSQL | ✅ | 5434 | 512 MB |
| 10 | Identity / SSO | **Keycloak** | `quay.io/keycloak/keycloak` | `26.0.7` | Apache-2.0 | ✅ | 8444 | 768 MB |
| 11 | Access control | **OPA** | `openpolicyagent/opa` | `0.68.0` | Apache-2.0 | ✅ | 8282 | 64 MB |
| 12 | Orchestration | **Apache Airflow** | `apache/airflow` | `2.10.2` | Apache-2.0 | ✅ | 8079 | 1.5 GB |
| 13 | Connector layer (default) | **Bronze Loader / dlt** | `dlt` / custom bronze loader | `0.5.4` | Apache-2.0 | ✅ | — | — |
| 14 | Search / vector | **OpenSearch** | `opensearchproject/opensearch` | `3.3.2` | Apache-2.0 | ✅ | 9200, 9300 | 1.5 GB |
| 15 | Search dashboards | **OpenSearch Dashboards** | `opensearchproject/opensearch-dashboards` | `3.3.0` | Apache-2.0 | ✅ | 5601 | 512 MB |
| 16 | LLM + embeddings | **Ollama** | `ollama/ollama` | `0.3.14` | MIT | ✅ | 11434 | 4 GB* |
| 17 | LLM model | **Qwen2.5-7B-Instruct** | via Ollama | `q4_K_M` | Apache-2.0 | ✅ | — | ~4 GB |
| 18 | Embed model | **nomic-embed-text** | via Ollama | `1.5` | Apache-2.0 | ✅ | — | ~300 MB |
| 19 | BI | **Apache Superset** | `apache/superset` | `4.1.1` | Apache-2.0 | ✅ | 8088 | 768 MB |
| 20 | API gateway | **Kong OSS** (DB-less) | `kong` | `3.8.0` | Apache-2.0 | ✅ | 8000, 8001 | 256 MB |
| 21 | Email (test) | **Mailpit** | `axllent/mailpit` | `v1.21.1` | MIT | ✅ | 1025, 8025 | 32 MB |
| 22 | IaC | **OpenTofu** | `ghcr.io/opentofu/opentofu` | `1.8.3` | MPL-2.0 | ✅ | — | — |
| 23 | RAG framework | **LlamaIndex** | pip `llama-index` | `0.11.20` | MIT | ✅ | — | — |
| 24 | NL→SQL validation | **SQLGlot** | pip `sqlglot` | `25.19.0` | MIT | ✅ | — | — |
| 25 | Transformation | **dbt-trino** | pip `dbt-trino` | `1.8.3` | Apache-2.0 | ✅ | — | — |
| 26 | Doc extraction | **Apache Tika** | `apache/tika` | `2.9.2.1-full` | Apache-2.0 | ✅ | 9998 | 512 MB |
| 27 | NER / NLP | **spaCy** | pip `spacy` | `3.7.6` | MIT | ✅ | — | — |
| 28 | IFC extraction | **IfcOpenShell** | pip `ifcopenshell` | `0.7.0` | LGPL-3.0 | ✅ | — | — |
| 29 | DXF extraction | **ezdxf** | pip `ezdxf` | `1.3.4` | MIT | ✅ | — | — |
| 30 | MSG extraction | **extract_msg** | pip `extract-msg` | `0.48.6` | GPL-3.0 | ✅ | — | — |
| 31 | PII detection | **Presidio** | pip `presidio-analyzer` | `2.2.355` | MIT | ✅ | — | — |
| 32 | Data quality | **Great Expectations** | pip `great-expectations` | `0.18.21` | Apache-2.0 | ✅ | — | — |
| 33 | File share | **Samba** | `dperson/samba` | `20231204` | GPL-3.0 | ✅ | **1445** (host) | 128 MB |
| 34 | Git | **Gitea** | `gitea/gitea` | `1.22.3` | MIT | ✅ | 3001, 222 | 256 MB |
| 35 | CI runner | **Gitea act_runner** | `gitea/act_runner` | `0.2.11` | MIT | ✅ | — | 256 MB |
| 36 | Monitoring | **Prometheus** | `prom/prometheus` | `v2.54.1` | Apache-2.0 | ✅ | 9090 | 256 MB |
| 37 | Dashboards | **Grafana** | `grafana/grafana` | `11.2.2` | AGPL-3.0 | ✅ | 3002 | 256 MB |
| 38 | Log shipping | **Fluent Bit** | `fluent/fluent-bit` | `3.1.9` | Apache-2.0 | ✅ | 2020 | 64 MB |
| 39 | Container advisor | **cAdvisor** | `gcr.io/cadvisor/cadvisor` | `v0.50.0` | Apache-2.0 | ✅ | 8094 | 128 MB |
| 40 | Security scan | **Trivy** | `aquasec/trivy` | `0.55.2` | Apache-2.0 | ✅ | — | — |
| 41 | OWASP scan | **OWASP ZAP** | `ghcr.io/zaproxy/zaproxy` | `2.15.0` | Apache-2.0 | ✅ | — | 512 MB |
| 42 | HTTP benchmark | **Locust** | pip `locust` | `2.31.6` | MIT | ✅ | 8089 | 128 MB |
| 43 | Data catalog | **OpenMetadata** | `openmetadata/server` | `2.0.3` | Apache-2.0 | ✅ | 8585 | 1.5 GB |
| 44 | Lineage | **OpenLineage** (Airflow) | pip `openlineage-airflow` | `1.22.0` | Apache-2.0 | ✅ | — | — |

> *Ollama RAM is model-dependent. Qwen2.5-7B-Q4_K_M ≈ 4 GB RAM (CPU), ~4 GB VRAM (GPU).
> On the target hardware (RTX 4070 8 GB VRAM), model runs on GPU; concurrent embedding is CPU.

## Port Map (complete)

| Port | Service | Protocol |
|---|---|---|
| 222 | Gitea SSH | SSH |
| 1025 | Mailpit SMTP | SMTP |
| 1445 | Samba SMB (host) | SMB |
| 2020 | Fluent Bit metrics | HTTP |
| 3001 | Gitea HTTP | HTTP |
| 3002 | Grafana | HTTP |
| 5432 | PostgreSQL meta | TCP |
| 5433 | PostgreSQL Airflow | TCP |
| 5434 | PostgreSQL DAR_DW | TCP |
| 5601 | OpenSearch Dashboards | HTTP |
| 8000 | Kong proxy | HTTP |
| 8001 | Kong admin | HTTP |
| 8025 | Mailpit UI | HTTP |
| 8079 | Airflow webserver | HTTP |
| 8080 | SeaweedFS volume | HTTP |
| 8081 | SeaweedFS volume-2 | HTTP |
| 8088 | Apache Superset | HTTP |
| 8089 | Locust UI | HTTP |
| 8090 | D365 mock | HTTP |
| 8091 | SharePoint mock | HTTP |
| 8092 | Data API (FastAPI) | HTTP |
| 8093 | Search API (FastAPI) | HTTP |
| 8094 | cAdvisor | HTTP |
| 8181 | Lakekeeper | HTTP |
| 8282 | OPA | HTTP |
| 8333 | SeaweedFS S3 gateway | HTTP |
| 8444 | Keycloak HTTP | HTTP |
| 8585 | OpenMetadata | HTTP |
| 8888 | SeaweedFS filer | HTTP |
| 9090 | Prometheus | HTTP |
| 9200 | OpenSearch HTTP | HTTP |
| 9300 | OpenSearch transport | TCP |
| 9333 | SeaweedFS master | HTTP |
| 9998 | Apache Tika | HTTP |
| 11434 | Ollama | HTTP |
| 18080 | Trino | HTTP |

## Optional Profiles (non-default)

| Profile | Tools | Licence class | Added RAM | Notes |
|---|---|---|---|---|
| `opt-licensed-sqlserver` | SQL Server 2022 Developer | **Non-OSI** (EULA) | +1.5 GB | Non-production use only |
| `opt-airbyte` | Airbyte self-managed | **Non-OSI** (ELv2) | +3 GB | Compose stack (`docker-compose.airbyte.yml`) on port 8006 |
| `opt-streaming` | Kafka (KRaft) + Debezium | OSS-heavy (Apache-2.0) | +3 GB | CDC streaming |
| `opt-ranger` | Apache Ranger | OSS-heavy (Apache-2.0) | +1 GB | GUI-driven RBAC |
| `opt-gitlab` | GitLab CE + Runner | OSS-heavy (MIT CE) | +3 GB | Alternative to Gitea |
| `opt-spark` | Apache Spark standalone | OSS-heavy (Apache-2.0) | +2 GB | Alternative to Trino+dbt |
| `opt-graph` | Apache AGE on Postgres | OSS (Apache-2.0) | +256 MB | Graph queries |
| `opt-mlflow` | MLflow | OSS (Apache-2.0) | +256 MB | ML experiment tracking |
| `opt-gpu` | Ollama CUDA runtime | OSS (MIT) | — | Requires NVIDIA GPU |

## Licence corrections vs M0 plan

| Component | M0 licence | Corrected | Action |
|---|---|---|---|
| Redis | BSD-3 (M0 incorrect) | RSALv2/SSPL | **REMOVED** — not OSI |
| Grafana | AGPL-3.0 | AGPL-3.0 | ✅ OSI-approved; unmodified use OK |
| extract_msg | GPL-3.0 | GPL-3.0 | ✅ OSI-approved; standalone service |
| Samba | GPL-3.0 | GPL-3.0 | ✅ OSI-approved; unmodified container |
