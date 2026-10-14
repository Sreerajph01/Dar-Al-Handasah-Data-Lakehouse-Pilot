"""
uc2-warehouse-migration/nl2sql/main.py — Natural Language to SQL Microservice
Dar Al-Handasah Data Lakehouse Pilot.

Translates business user natural language queries into valid Trino SQL over Iceberg
Silver and Gold data products. Uses SQLGlot for AST safety verification (read-only
enforcement) and Ollama Qwen2.5-7B for query formulation.

Performance notes:
  - OLLAMA_KEEP_ALIVE=15m keeps model hot between calls (set in docker-compose.yml)
  - Timeout raised to 120s to accommodate CPU-mode inference; drops to ~3s on GPU
  - Few-shot examples guide the model toward correct SQL patterns
"""

import os
import re
import time
import httpx
import sqlglot
from sqlglot import exp
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import trino
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nl2sql")

OLLAMA_HOST   = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL  = os.environ.get("OLLAMA_LLM_MODEL", "qwen2.5:7b-instruct-q4_K_M")
TRINO_HOST    = os.environ.get("TRINO_HOST", "trino")
TRINO_PORT    = int(os.environ.get("TRINO_PORT", "8080"))
TRINO_USER    = os.environ.get("TRINO_USER", "admin")
TRINO_CATALOG = os.environ.get("TRINO_CATALOG", "iceberg")
# Maximum rows returned; protects against accidental large scans
MAX_ROWS      = int(os.environ.get("NL2SQL_MAX_ROWS", "100"))

app = FastAPI(
    title="Dar Lakehouse — Natural Language to SQL Service",
    version="1.1.0",
    description="Text-to-SQL engine powered by Ollama and SQLGlot validation for Trino Iceberg data",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Schema context + few-shot examples ────────────────────────────────────────
SCHEMA_CONTEXT = """
=== AVAILABLE TRINO ICEBERG TABLES ===
1. iceberg.silver.dim_project
   project_id (VARCHAR), project_name (VARCHAR), client_name (VARCHAR),
   project_type (VARCHAR), country (VARCHAR), status (VARCHAR),
   is_current (BOOLEAN) — TRUE for the active SCD2 record

2. iceberg.silver.dim_wbs
   wbs_id (VARCHAR), project_id (VARCHAR), wbs_code (VARCHAR),
   wbs_name (VARCHAR), discipline (VARCHAR)

3. iceberg.silver.fact_budget
   budget_id (VARCHAR), wbs_id (VARCHAR),
   amount (DOUBLE) — USD-normalised, currency (VARCHAR) = 'USD'

4. iceberg.silver.fact_timesheet
   timesheet_id (VARCHAR), employee_id (VARCHAR), wbs_id (VARCHAR),
   hours (DOUBLE), cost (DOUBLE), period_date (VARCHAR)

5. iceberg.gold.evm_metrics
   project_id (VARCHAR), date_id (VARCHAR),
   ev (DOUBLE), pv (DOUBLE), ac (DOUBLE), bac (DOUBLE),
   sv (DOUBLE)  — Schedule Variance  = EV - PV,
   cv (DOUBLE)  — Cost Variance      = EV - AC,
   spi (DOUBLE) — Schedule Performance Index = EV / PV,
   cpi (DOUBLE) — Cost Performance Index     = EV / AC,
   eac (DOUBLE) — Estimate at Completion,
   vac (DOUBLE) — Variance at Completion

6. iceberg.gold.budget_vs_actual
   wbs_id (VARCHAR), total_budget (DOUBLE), currency (VARCHAR)

7. iceberg.gold.project_summary
   project_id (VARCHAR), project_name (VARCHAR), total_budget (DOUBLE),
   total_cost (DOUBLE), status (VARCHAR)

8. iceberg.gold.reconciliation
   source_total (DOUBLE), gold_total (DOUBLE), quarantine_total (DOUBLE),
   difference (DOUBLE), is_within_tolerance (BOOLEAN), reconciled_at (TIMESTAMP)

=== FEW-SHOT EXAMPLES ===
Q: List all projects with Cost Performance Index below 1.0
A: SELECT project_id, MAX(date_id) AS latest_date, AVG(cpi) AS avg_cpi, AVG(spi) AS avg_spi
   FROM iceberg.gold.evm_metrics
   WHERE cpi < 1.0
   GROUP BY project_id
   ORDER BY avg_cpi ASC
   LIMIT 50

Q: Show me the CPI and SPI for all active projects
A: SELECT e.project_id, p.project_name, e.date_id, e.cpi, e.spi
   FROM iceberg.gold.evm_metrics e
   JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id
   WHERE p.is_current = TRUE AND p.status = 'Active'
     AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id)
   ORDER BY e.project_id
   LIMIT 50

Q: What is the total budget by discipline?
A: SELECT w.discipline, SUM(b.amount) AS total_budget_usd
   FROM iceberg.silver.fact_budget b
   JOIN iceberg.silver.dim_wbs w ON b.wbs_id = w.wbs_id
   WHERE b.is_deleted = FALSE OR b.is_deleted IS NULL
   GROUP BY w.discipline
   ORDER BY total_budget_usd DESC
   LIMIT 50

Q: Which projects are over budget?
A: SELECT project_id, total_budget, total_cost,
          total_cost - total_budget AS overrun
   FROM iceberg.gold.project_summary
   WHERE total_cost > total_budget
   ORDER BY overrun DESC
   LIMIT 50
"""

SYSTEM_PROMPT = f"""You are an expert Trino SQL engineer for the Dar Al-Handasah Data Lakehouse.
Translate the user's natural language question into a correct, read-only Trino SQL query.

{SCHEMA_CONTEXT}

STRICT RULES:
1. Output ONLY the raw SQL query. No markdown, no backticks, no preamble, no explanation.
2. Must be a single SELECT statement. Never use DROP, DELETE, INSERT, UPDATE, CREATE, ALTER, TRUNCATE.
3. Always qualify tables: iceberg.silver.<table> or iceberg.gold.<table>.
4. Use NULLIF to avoid division by zero. Use LIMIT (max {MAX_ROWS}) unless user asks for all.
5. Follow the few-shot examples above — they show the correct pattern for common queries.
6. For CPI/SPI filter queries, ALWAYS include the filter in the WHERE clause (e.g. WHERE cpi < 1.0).
"""


class NLQueryRequest(BaseModel):
    query: str
    execute: bool = True


class NLQueryResponse(BaseModel):
    nl_query: str
    sql: str
    is_safe: bool
    columns: List[str] = []
    rows: List[List[Any]] = []
    row_count: int = 0
    execution_ms: int = 0
    explanation: Optional[str] = None


# ── Allowed table allowlist (Gold and Silver only — no DDL targets) ────────────
ALLOWED_SCHEMAS = {"gold", "silver"}


def validate_and_sanitize_sql(sql_query: str) -> str:
    """Uses SQLGlot to parse and ensure the query is strictly a safe read-only SELECT."""
    clean_sql = sql_query.strip().rstrip(";")
    # Strip markdown code fences if LLM wrapped in ```sql ... ```
    clean_sql = re.sub(r"^```(?:sql)?\s*", "", clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r"\s*```$", "", clean_sql)

    try:
        parsed = sqlglot.parse_one(clean_sql, read="trino")
    except Exception as e:
        raise ValueError(f"SQL syntax error: {str(e)}")

    # Root must be a SELECT
    if not isinstance(parsed, exp.Select):
        raise ValueError(
            f"Security Violation: Only read-only SELECT queries are permitted. "
            f"Got: {type(parsed).__name__}"
        )

    # Forbidden mutation operations
    forbidden = [exp.Drop, exp.Delete, exp.Insert, exp.Update, exp.Alter, exp.TruncateTable]
    for expr_type in forbidden:
        if parsed.find(expr_type):
            raise ValueError(
                f"Security Violation: Query contains prohibited operation {expr_type.__name__}."
            )

    # Validate all referenced tables are in allowed schemas
    for table in parsed.find_all(exp.Table):
        # table.db is a string property (empty string if no schema prefix)
        db = table.db.lower() if table.db else ""
        if db and db not in ALLOWED_SCHEMAS and db not in {"", "iceberg"}:
            raise ValueError(
                f"Security Violation: Table schema '{db}' is not in the allowed list {ALLOWED_SCHEMAS}."
            )

    # Ensure LIMIT exists (add one if missing)
    if not parsed.find(exp.Limit):
        clean_sql = f"{clean_sql} LIMIT {MAX_ROWS}"
        parsed = sqlglot.parse_one(clean_sql, read="trino")

    return parsed.sql(dialect="trino")


def _heuristic_fallback(user_q: str) -> str:
    """
    Keyword-based fallback SQL templates when Ollama is unavailable or times out.
    Fallback templates MUST include correct WHERE clauses matching the user intent.
    """
    lower_q = user_q.lower()

    if ("cpi" in lower_q or "cost performance" in lower_q) and (
        "below" in lower_q or "less than" in lower_q or "under" in lower_q or "< 1" in lower_q
    ):
        return (
            "SELECT project_id, AVG(cpi) AS avg_cpi, AVG(spi) AS avg_spi "
            "FROM iceberg.gold.evm_metrics "
            "WHERE cpi < 1.0 "
            "GROUP BY project_id ORDER BY avg_cpi ASC "
            f"LIMIT {MAX_ROWS}"
        )
    elif "spi" in lower_q and ("below" in lower_q or "less" in lower_q or "behind" in lower_q):
        return (
            "SELECT project_id, AVG(spi) AS avg_spi "
            "FROM iceberg.gold.evm_metrics "
            "WHERE spi < 1.0 "
            "GROUP BY project_id ORDER BY avg_spi ASC "
            f"LIMIT {MAX_ROWS}"
        )
    elif "evm" in lower_q or "cpi" in lower_q or "spi" in lower_q or "earned value" in lower_q:
        return (
            "SELECT e.project_id, e.date_id, e.ev, e.pv, e.ac, e.cpi, e.spi "
            "FROM iceberg.gold.evm_metrics e "
            "WHERE e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) "
            "ORDER BY e.project_id "
            f"LIMIT {MAX_ROWS}"
        )
    elif "budget" in lower_q and ("over" in lower_q or "exceed" in lower_q):
        return (
            "SELECT project_id, total_budget, total_cost, total_cost - total_budget AS overrun "
            "FROM iceberg.gold.project_summary "
            "WHERE total_cost > total_budget "
            "ORDER BY overrun DESC "
            f"LIMIT {MAX_ROWS}"
        )
    elif "budget" in lower_q:
        return (
            "SELECT wbs_id, total_budget, currency "
            "FROM iceberg.gold.budget_vs_actual "
            "ORDER BY total_budget DESC "
            f"LIMIT {MAX_ROWS}"
        )
    elif "reconcil" in lower_q:
        return (
            "SELECT source_total, gold_total, quarantine_total, difference, is_within_tolerance, reconciled_at "
            "FROM iceberg.gold.reconciliation"
        )
    elif "project" in lower_q and "active" in lower_q:
        return (
            "SELECT project_id, project_name, client_name, status, country "
            "FROM iceberg.silver.dim_project "
            "WHERE is_current = TRUE AND status = 'Active' "
            f"LIMIT {MAX_ROWS}"
        )
    else:
        return (
            "SELECT project_id, project_name, client_name, status "
            "FROM iceberg.silver.dim_project "
            "WHERE is_current = TRUE "
            f"LIMIT {MAX_ROWS}"
        )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "dar-nl2sql",
        "ollama_host": OLLAMA_HOST,
        "llm_model": OLLAMA_MODEL,
        "trino_target": f"{TRINO_HOST}:{TRINO_PORT}",
    }


@app.post("/v1/query", response_model=NLQueryResponse)
async def translate_and_query(req: NLQueryRequest):
    start_time = time.time()
    user_q = req.query.strip()
    if not user_q:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    raw_sql = ""
    ollama_ok = False

    try:
        # Raise timeout to 120s for CPU-mode inference; ~3s expected on GPU
        async with httpx.AsyncClient(timeout=120.0) as client:
            t0 = time.time()
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"{SYSTEM_PROMPT}\nUser Question: {user_q}\nSQL Query:",
                    "stream": False,
                    "keep_alive": "15m",
                    "options": {"temperature": 0.05, "top_p": 0.9, "num_predict": 512},
                },
            )
            ollama_ms = int((time.time() - t0) * 1000)
            logger.info("Ollama responded in %d ms", ollama_ms)
            if resp.status_code == 200:
                raw_sql = resp.json().get("response", "").strip()
                ollama_ok = bool(raw_sql and "SELECT" in raw_sql.upper())
    except Exception as e:
        logger.warning("Ollama call failed (%s) — using heuristic fallback.", e)

    # If Ollama failed or returned unusable output, use heuristic templates
    if not ollama_ok:
        logger.info("Using heuristic fallback for query: %r", user_q)
        raw_sql = _heuristic_fallback(user_q)

    # SQLGlot Safety Validation
    try:
        safe_sql = validate_and_sanitize_sql(raw_sql)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    columns: List[str] = []
    rows: List[List[Any]] = []
    if req.execute:
        try:
            conn = trino.dbapi.connect(
                host=TRINO_HOST,
                port=TRINO_PORT,
                user=TRINO_USER,
                catalog=TRINO_CATALOG,
            )
            cursor = conn.cursor()
            cursor.execute(safe_sql)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            raw_rows = cursor.fetchmany(MAX_ROWS)
            rows = [[str(val) if val is not None else None for val in r] for r in raw_rows]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Trino execution error: {str(e)}")

    exec_time_ms = int((time.time() - start_time) * 1000)
    source = "ollama" if ollama_ok else "heuristic-fallback"
    return NLQueryResponse(
        nl_query=user_q,
        sql=safe_sql,
        is_safe=True,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_ms=exec_time_ms,
        explanation=(
            f"SQL generated via {source}. "
            f"Executed against Trino Iceberg engine ({len(rows)} records returned)."
        ),
    )
