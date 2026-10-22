# Dar Al-Handasah Data Lakehouse Pilot — 10-Minute Executive & Technical Demo Script

**Target Audience:** Senior Leadership, Data Architecture Evaluation Committee, Engineering Directorate  
**Duration:** 10 Minutes  
**Demonstration Command:** `.\dar.ps1 demo` (or interactive Web UIs)  
**Environment:** Single Developer Laptop / Workstation (Windows PowerShell 5.1+ / Docker Desktop WSL2)

---

## Architecture & Synthetic Data Transparency Notice

> [!NOTE]
> **Data Authenticity Disclosure:**
> - **Real Ingestion & Processing:** Apache Tika, ezdxf CAD parser, Presidio PII anonymizer, OpenSearch 3.3.2 hybrid search (BM25 + 768-dim k-NN vectors), local Ollama LLM (`qwen2.5:7b-instruct-q4_K_M`), SeaweedFS S3, Lakekeeper Iceberg REST Catalog, Trino 455, and dbt 1.8.3 are **100% real, active running services**.
> - **Synthetic / Mock Sources:** Enterprise ERP (Microsoft Dynamics 365 F&O) and SharePoint document repositories are **simulated mock microservices** (`dar-d365-mock`, `dar-sharepoint-mock`) generating realistic synthetic engineering operational payloads. The legacy PostgreSQL Data Warehouse contains synthetic project data (P001–P005) mirroring Dar Al-Handasah PM, WBS, and financial schemas.

---

## 10-Minute Demonstration Timeline

| Segment | Time | Component | Focus |
|---|---|---|---|
| **0. Pre-Flight & Health** | 0:00 – 1:00 | Platform Orchestration | Zero-failure readiness check (`.\dar.ps1 health`) |
| **1. UC1: Search & Discovery** | 1:00 – 3:00 | CAD/BIM/EML & Presidio | Multi-format extraction, PII scrubbing, 768-dim hybrid search |
| **2. UC1: Grounded RAG & ACL** | 3:00 – 5:00 | Local Ollama & OPA ACL | Citation-backed engineering Q&A, Hallucination Guard, Role Isolation |
| **3. UC2: Medallion Lakehouse** | 5:00 – 7:30 | Iceberg, Trino, dbt, EVM | Bronze $\to$ Silver $\to$ Gold transformation, EVM metrics, Financial Audit |
| **4. UC2: NL2SQL & Data API** | 7:30 – 9:00 | SQLGlot & FastAPI | Natural language self-service with AST guardrails, Row-Level Security |
| **5. Business Intelligence & Q&A**| 9:00 – 10:00| Apache Superset | Cost/Budget/EVM dashboards, wrap-up |

---

## Detailed Talk Track & Commands

### Segment 0: Pre-Flight Platform Health (1 min)

**Speaker Dialogue:**
> *"Good morning. Today we present the Dar Al-Handasah Data Lakehouse Pilot. Before showing analytics or AI, we verify platform integrity. Our automated orchestration layer manages 34 distributed services spanning object storage, distributed query engines, vector search, and local AI models without any cloud dependencies."*

**Command to Run:**
```powershell
.\dar.ps1 health
```

**Expected Output Highlights:**
- SeaweedFS S3, Lakekeeper Iceberg Catalog, Trino, OpenSearch, Ollama, Keycloak, Airflow, Superset all report **PASS** (100% green, 0 FAIL).
- Zero host port conflicts.

---

### Segment 1: Use Case 1 — Engineering Search & Extraction (2 mins)

**Speaker Dialogue:**
> *"Engineering teams manage heterogeneous, unstructured files—AutoCAD DXF/DWG drawings, IFC BIM models, and project change orders in email format. The pilot extracts layers, geometries, and metadata, redacts GDPR/PII data via Microsoft Presidio, and indexes 768-dimensional dense vectors into OpenSearch alongside BM25 lexical tokens."*

**Demo Actions:**
1. Navigate to: `http://localhost:8093/ui`
2. **Search Query:** `deep bored concrete piles foundation`
3. Point out:
   - **Score Normalization:** Hybrid reciprocal rank fusion combining BM25 keyword relevance and cosine vector distance.
   - **Metadata Badges:** CAD drawing layers (`S-COLS`, `S-BEAMS`), BIM structural attributes, and PII redaction tags.
   - **Tier Handling:** Tier A files (DXF, IFC, TXT, EML) index full text; Tier B proprietary files (`.dwg`, `.rvt`) are indexed safely as metadata-only records.

---

### Segment 2: Grounded Engineering RAG & Role-Based Isolation (2 mins)

**Speaker Dialogue:**
> *"Engineers cannot afford LLM hallucinations or unauthorized access to confidential project specs. Here we demonstrate strict role-based access control and strict grounding using a local quantized Qwen 2.5 7B model running completely on-premise via Ollama."*

**Demo Actions & Questions:**
1. **Role Switcher Live Demo:**
   - Select persona: **Project Manager (METRO-01 Only)** (`pm_metro-01`).
   - Query project: `HOSP-03` $\to$ Returns **0 documents (Access Blocked)**.
   - Select persona: **Executive Leadership** (`pm_executive`).
   - Query project: `HOSP-03` $\to$ Returns **4 documents (Access Granted)**.
2. **Grounded Technical Q&A with Citations:**
   - **Question:** *"What is the concrete strength and cement type specified for HOSP-03 piles?"*
   - **Expected AI Response:** Concrete compressive strength $f_{cu} = 50\text{ MPa}$ (C40/50), Sulfate Resisting Portland Cement (SRPC) Type V.
   - Point out: Exact clickable file citation `HOSP-03_Foundation_Piling_Spec.txt` with chunk excerpts.
3. **Hallucination Guard Test:**
   - Click question chip: *"What is the titanium alloy grade for the bridge suspension cables on HOSP-03?"*
   - **Expected AI Response:** *"Information not found in the retrieved documents."*
   - Point out: The LLM refuses to fabricate ungrounded answers.

---

### Segment 3: Use Case 2 — Medallion Lakehouse & EVM Analytics (2.5 mins)

**Speaker Dialogue:**
> *"For structured analytics, we migrated legacy relational data warehouses into an Apache Iceberg Medallion Lakehouse powered by SeaweedFS S3 and Trino. Our conformed silver models enforce ISO currency normalization, and gold models compute Earned Value Management (EVM) metrics."*

**Interactive Inspection or Demo Runner:**
```powershell
.\dar.ps1 demo
```

**Key Data Proofs to Highlight:**
1. **Medallion Conformance:**
   - Silver `dim_project` maintains exactly **4 active conformed projects** with deduplicated SCD2 tracking.
   - Quarantine table intercepts corrupt/null records (e.g. project with null name).
2. **Earned Value Management (EVM):**
   - Clean tabular output showing Planned Value (PV), Earned Value (EV), Actual Cost (AC), Cost Performance Index (CPI), and Schedule Performance Index (SPI) deduplicated by latest date snapshot.
   - Projects underperforming ($CPI < 1.0$) are accurately highlighted.
3. **Automated Reconciliation Audit:**
   - Source PostgreSQL DW total budget: `$40,036,263.38`
   - Target Lakehouse Gold + Quarantine sum: `$40,036,263.38`
   - Reconciled variance: **$0.0000** (Zero data loss).

---

### Segment 4: Natural Language to SQL (NL2SQL) & REST Data API (1.5 mins)

**Speaker Dialogue:**
> *"Non-technical project controllers can query the lakehouse in plain English. The NL2SQL service translates natural language into ANSI Trino SQL with SQLGlot AST guardrails that enforce read-only SELECT execution, schema context pruning, and sub-second caching."*

**Demo Actions:**
1. Navigate to: `http://localhost:8095/docs` (or view demo runner terminal).
2. **Query:** *"List all projects with Cost Performance Index below 1.0"*
3. **Show Generated SQL:**
   ```sql
   SELECT e.project_id, p.project_name, e.date_id, e.cpi 
   FROM iceberg.gold.evm_metrics AS e 
   JOIN iceberg.silver.dim_project AS p ON e.project_id = p.project_id 
   WHERE e.cpi < 1.0 AND p.is_current = TRUE 
   GROUP BY e.project_id, p.project_name, e.date_id, e.cpi 
   ORDER BY e.cpi ASC LIMIT 100
   ```
4. **Security Proof:** Explain that destructive queries (`DROP TABLE`, `UPDATE`, `INSERT`) are syntactically intercepted and blocked by the AST parser before execution.
5. **Data Product API:** Open `http://localhost:8092/docs` to demonstrate REST consumer endpoints with JWT authentication and tenant/project filtering.

---

### Segment 5: Executive BI Dashboards in Apache Superset (1 min)

**Speaker Dialogue:**
> *"Finally, we present executive dashboards hosted on Apache Superset, connected directly to Iceberg Gold tables via Trino."*

**Demo Actions:**
1. Open `http://localhost:8088` (Credentials: `admin` / `.env` password).
2. **Dashboard 1: Dar Al-Handasah — Portfolio Health & EVM Analytics**
   - CPI vs. SPI quadrant scatter plot, portfolio cost trend, project breakdown.
3. **Dashboard 2: Dar Al-Handasah — Cost, Budget & Utilisation**
   - Discipline budget distribution (Civil, Structural, MEP, Infrastructure), actual vs. planned cost variance.

---

## Fallback & Troubleshooting Notes

| Potential Issue | Symptom | Immediate Fallback Action |
|---|---|---|
| **Ollama cold start latency** | RAG query takes > 5s | The demo runner pre-warms Ollama. If cold, explain the 7B parameter local inference on CPU/WSL2; warm queries execute in ~1s. |
| **Port conflict on host** | Container fails to bind | Run `.\dar.ps1 up-lite` which operates solely on core, UC1, and UC2 ports. |
| **Trino schema lock** | Query timeout | Trino is configured with Iceberg catalog REST endpoints on `dar-lakekeeper:8181`; restart with `docker compose restart trino`. |
| **OpenSearch yellow cluster** | Replica unassigned | Normal for single-node development mode; `number_of_replicas` is configured to `0`. |
