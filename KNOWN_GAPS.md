# KNOWN_GAPS.md — Dar Al Handasah Data Lakehouse Pilot
# Updated at each milestone. Gaps are honest; none are hidden.
# ─────────────────────────────────────────────────────────────────────────────

## Format

Each gap: **ID · Area · Description · TRACEABILITY class · Mitigation/Production path**

---

## G1 — SeaweedFS: Object lock / WORM retention

- **Area**: Object storage (RFP Nb 25)
- **Detail**: SeaweedFS 3.75 has partial object lock support (governance mode only). Compliance-mode WORM and per-object retention period enforcement are not fully verified on a single node.
- **TRACEABILITY class**: Documented
- **Mitigation**: Conformance test `test_object_lock` classifies this. Production approach: Dell ObjectScale provides hardware-enforced WORM; alternatively Ceph RGW with object lock plugin. Documented in `docs/HA_AND_SCALE.md`.

## G2 — SeaweedFS: Storage tiering / cold tier

- **Area**: Object storage lifecycle (RFP Nb 24)
- **Detail**: Tiering to a secondary storage class (cold/archive) requires multi-node SeaweedFS or a cloud backend. Not demonstrable on a single laptop.
- **TRACEABILITY class**: Not locally demonstrable
- **Mitigation**: SeaweedFS supports remote storage targets (S3-compatible) for tiering in production. Dell ObjectScale provides hardware tiering. Documented in `docs/HA_AND_SCALE.md`.

## G3 — SeaweedFS: Cross-cluster replication

- **Area**: Data replication (RFP Nb 26)
- **Detail**: Cross-cluster replication requires two separate SeaweedFS clusters. Cannot be simulated on one laptop without prohibitive RAM cost.
- **TRACEABILITY class**: Not locally demonstrable
- **Mitigation**: SeaweedFS cross-DC replication is documented. Production: Dell ObjectScale handles cross-site replication natively.

## G4 — SeaweedFS: SSE encryption at rest (full)

- **Area**: Encryption at rest (RFP Nb 52)
- **Detail**: SeaweedFS supports SSE-S3 header pass-through but does not perform client-transparent data encryption at rest in the OSS version without additional key management setup.
- **TRACEABILITY class**: Documented
- **Mitigation**: Volume-level encryption (LUKS) on the host covers data at rest. TLS covers data in transit. Production: Dell ObjectScale provides hardware-backed encryption.

## G5 — Real AD/Entra ID federation

- **Area**: Identity (RFP Nb 23, 57)
- **Detail**: Keycloak is used as a stand-in for Azure Active Directory / Entra ID. Real LDAP/SAML federation to a customer AD is not configured (no AD server in pilot).
- **TRACEABILITY class**: Demonstrated (Keycloak); AD/Entra Documented
- **Mitigation**: Keycloak natively supports SAML2/OIDC federation to Entra ID. A one-page integration guide is provided in `docs/deliverables/`.

## G6 — Real D365 F&O connector

- **Area**: Ingestion (RFP Nb 37)
- **Detail**: The D365 source is a FastAPI mock with OData-style endpoints. The real dlt D365 connector or Airbyte connector requires a licensed D365 tenant.
- **TRACEABILITY class**: Demonstrated (simulated); real connector Documented
- **Mitigation**: The mock exposes identical endpoints. The dlt connector config (endpoint URL, auth) is parameterised; swap the mock URL for production.

## G7 — Real SharePoint / Microsoft Graph connector

- **Area**: Ingestion (RFP Nb 39, 40)
- **Detail**: SharePoint mock exposes a Graph-style REST API. Real connector requires an M365 tenant and app registration.
- **TRACEABILITY class**: Demonstrated (simulated); real Documented

## G8 — Salesforce connector

- **Area**: Ingestion (RFP Nb 38)
- **Detail**: No Salesforce org available for the pilot. Cannot be demonstrated.
- **TRACEABILITY class**: Not locally demonstrable
- **Mitigation**: dlt has a Salesforce connector; plugs into the same Airflow DAG pattern. Documented.

## G9 — Azure API Management (RFP Nb 47)

- **Area**: API gateway
- **Detail**: Kong OSS is used as the local stand-in. Azure API Management is a cloud service.
- **TRACEABILITY class**: Demonstrated (Kong OSS); Azure APIM integration Documented

## G10 — Kaspersky AV compatibility (RFP Nb 53)

- **Area**: Security compatibility
- **Detail**: No Kaspersky environment available. Cannot be tested.
- **TRACEABILITY class**: Not locally demonstrable
- **Mitigation**: Documented as vendor-side responsibility; no known conflicts with standard OSS containers.

## G11 — Production HA and scale-out

- **Area**: High availability (RFP Nb 11, 12, 84, 85)
- **Detail**: All components run as single-node instances. HA requires Kubernetes or multi-VM deployment.
- **TRACEABILITY class**: Not locally demonstrable
- **Mitigation**: Documented in `docs/HA_AND_SCALE.md` with per-component scale-out approach and mapping to Dell AIDP hardware.

## G12 — RVT/DWG content extraction (Tier B formats)

- **Area**: UC1 search (RFP Nb 27)
- **Detail**: Revit (.rvt) and AutoCAD DWG (.dwg) binary formats are proprietary. No OSS library can reliably extract design content. Files are indexed with metadata only (path, name, size, hash, project, discipline, revision).
- **TRACEABILITY class**: Demonstrated (metadata-only); content extraction Not locally demonstrable
- **Mitigation**: Documented in Section 5.1 of the spec. The demo shows metadata-only badge in the Search UI. LibreDWG (GPL) provides optional DWG→DXF conversion but is unreliable for complex files.

## G13 — RFP xlsx not provided at M1

- **Area**: Traceability
- **Detail**: `docs/source/RFP_tooling.xlsx` has been referenced but not yet placed in the repo at M1 time. `requirements.yaml` is generated from inline spec text.
- **Status**: OPEN — user to provide file. `make verify` will re-parse it automatically when placed at `docs/source/RFP_tooling.xlsx`.

## G14 — Live IMAP email ingestion

- **Area**: UC1 ingestion (RFP Nb 35)
- **Detail**: The demo ingests `.eml` and `.msg` files from the file share. Live IMAP polling requires an email server credential and is not in scope for the local demo.
- **TRACEABILITY class**: Demonstrated (file-based); live IMAP Optional

## G15 — OpenMetadata 2.0 + OpenSearch 3.3.2 version jump from M0 plan

- **Area**: Governance stack
- **Detail**: OpenMetadata 1.5.9 (M0 plan) required OpenSearch 2.x. OpenMetadata 2.0.3 requires OpenSearch 3.3.2. This is a breaking change between plan and implementation. The M0 stack manifest is superseded by STACK.md.
- **Status**: RESOLVED — STACK.md updated. Shared OpenSearch instance uses `om_*` / `uc1_*` index prefix separation.

## G16 — Redis removed (licence correction)

- **Area**: Infrastructure
- **Detail**: Redis 7.4 is licensed under RSALv2/SSPL (not OSI-approved). It was incorrectly listed as BSD-3 in the M0 plan. Redis is REMOVED. Airflow LocalExecutor does not require a broker. Valkey (BSD-3, Redis-compatible) is available if a broker is genuinely needed in the future.
- **Status**: RESOLVED — Redis removed from all Compose files and STACK.md.

## M2: Bronze Layer Incremental Static Tables
- **Limitation**: Static tables (e.g., dim_calendar) that do not possess a modified_at column or tracking timestamp are fully fetched from the source. To prevent duplicating the same unchanged rows on every incremental run (since Bronze is append-only), we explicitly skip fetching them during incremental loads if they have an existing watermark.
- **Impact**: Any late-arriving or retroactive changes to these static tables at the source will NOT be captured in the Bronze layer until a full refresh is triggered.

## G17 — M2 evidence gate is not executable as an acceptance test

- **Area**: UC2 Bronze ingestion
- **Detail**: The current M2 test stops after its full-load run because it assumes an `id` key for D365 entities without one. Its comparisons are printed instead of asserted, so a mismatch can produce a zero exit status.
- **TRACEABILITY class**: Documented
- **Mitigation**: Replace it with assertion-backed source-to-Bronze, CDC/delete, and second-run idempotence tests, then repeat a clean reset/up-lite/seed/seed sequence before changing the M2 verdict.
