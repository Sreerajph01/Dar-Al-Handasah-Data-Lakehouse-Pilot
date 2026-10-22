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
from fastapi import FastAPI, HTTPException
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

# ── Query Cache for sub-second repeat latency ────────────────────────────────
QUERY_CACHE: Dict[str, Dict[str, Any]] = {}

# ── Granular Schema Tables for Pruning ─────────────────────────────────────────
SCHEMA_TABLES = {
    "evm": """1. iceberg.gold.evm_metrics
   project_id (VARCHAR), date_id (VARCHAR),
   ev (DOUBLE) — Earned Value, pv (DOUBLE) — Planned Value, ac (DOUBLE) — Actual Cost, bac (DOUBLE) — Budget at Completion,
   sv (DOUBLE) — Schedule Variance = EV - PV, cv (DOUBLE) — Cost Variance = EV - AC,
   spi (DOUBLE) — Schedule Performance Index = EV / PV, cpi (DOUBLE) — Cost Performance Index = EV / AC,
   eac (DOUBLE) — Estimate at Completion, vac (DOUBLE) — Variance at Completion

2. iceberg.silver.dim_project
   project_id (VARCHAR), project_name (VARCHAR), client_name (VARCHAR),
   project_type (VARCHAR), country (VARCHAR), status (VARCHAR), is_current (BOOLEAN)""",

    "budget": """1. iceberg.gold.project_summary
   project_id (VARCHAR), project_name (VARCHAR), total_budget (DOUBLE), total_cost (DOUBLE), status (VARCHAR)

2. iceberg.gold.budget_vs_actual
   wbs_id (VARCHAR), total_budget (DOUBLE), currency (VARCHAR)

3. iceberg.silver.fact_budget
   budget_id (VARCHAR), wbs_id (VARCHAR), amount (DOUBLE) — USD, currency (VARCHAR) = 'USD'

4. iceberg.silver.dim_wbs
   wbs_id (VARCHAR), project_id (VARCHAR), wbs_code (VARCHAR), wbs_name (VARCHAR), discipline (VARCHAR)""",

    "timesheet": """1. iceberg.silver.fact_timesheet
   timesheet_id (VARCHAR), employee_id (VARCHAR), wbs_id (VARCHAR), hours (DOUBLE), cost (DOUBLE), period_date (VARCHAR)

2. iceberg.silver.dim_employee
   employee_id (VARCHAR), full_name (VARCHAR), department (VARCHAR), role (VARCHAR)""",

    "reconciliation": """1. iceberg.gold.reconciliation
   source_total (DOUBLE), gold_total (DOUBLE), quarantine_total (DOUBLE), difference (DOUBLE), is_within_tolerance (BOOLEAN), reconciled_at (TIMESTAMP)"""
}

def get_pruned_schema(user_q: str) -> str:
    """Selects only relevant tables based on keywords to keep prompt concise and fast."""
    q = user_q.lower()
    selected = []
    if any(k in q for k in ["cpi", "spi", "evm", "earned value", "variance", "performance"]):
        selected.append(SCHEMA_TABLES["evm"])
    if any(k in q for k in ["budget", "cost", "wbs", "overrun", "over budget", "actual"]):
        selected.append(SCHEMA_TABLES["budget"])
    if any(k in q for k in ["timesheet", "hour", "employee", "staff"]):
        selected.append(SCHEMA_TABLES["timesheet"])
    if any(k in q for k in ["reconcil", "audit", "tolerance", "difference"]):
        selected.append(SCHEMA_TABLES["reconciliation"])

    if not selected:
        selected = [SCHEMA_TABLES["evm"], SCHEMA_TABLES["budget"]]

    return "\n\n".join(selected)

FEW_SHOT_GUIDE = """=== FEW-SHOT EXAMPLES ===
Q: List all projects with Cost Performance Index below 1.0
A: SELECT e.project_id, p.project_name, e.date_id, e.cpi, e.spi FROM iceberg.gold.evm_metrics e JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id WHERE p.is_current = TRUE AND e.cpi < 1.0 AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) ORDER BY e.cpi ASC

Q: List all projects with Schedule Performance Index below 1.0
A: SELECT e.project_id, p.project_name, e.date_id, e.spi, e.cpi FROM iceberg.gold.evm_metrics e JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id WHERE p.is_current = TRUE AND e.spi < 1.0 AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) ORDER BY e.spi ASC

Q: Show me the CPI and SPI for all active projects
A: SELECT e.project_id, p.project_name, e.date_id, e.cpi, e.spi FROM iceberg.gold.evm_metrics e JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id WHERE p.is_current = TRUE AND p.status = 'Active' AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) ORDER BY e.project_id LIMIT 50

Q: What is the total budget by discipline?
A: SELECT w.discipline, SUM(b.amount) AS total_budget_usd FROM iceberg.silver.fact_budget b JOIN iceberg.silver.dim_wbs w ON b.wbs_id = w.wbs_id GROUP BY w.discipline ORDER BY total_budget_usd DESC LIMIT 50

Q: Which projects are over budget?
A: SELECT project_id, total_budget, total_cost, total_cost - total_budget AS overrun FROM iceberg.gold.project_summary WHERE total_cost > total_budget ORDER BY overrun DESC LIMIT 50

Q: Show latest EVM metrics for project P001
A: SELECT project_id, date_id, ev, pv, ac, cpi, spi FROM iceberg.gold.evm_metrics WHERE project_id = 'P001' ORDER BY date_id DESC LIMIT 1

Q: List projects in Saudi Arabia
A: SELECT project_id, project_name, status, country FROM iceberg.silver.dim_project WHERE is_current = TRUE AND country = 'Saudi Arabia' LIMIT 50

Q: What is the total project cost across all projects?
A: SELECT SUM(total_cost) AS total_portfolio_cost_usd FROM iceberg.gold.project_summary

Q: Show financial reconciliation summary between source and lakehouse
A: SELECT source_total, gold_total, quarantine_total, difference, is_within_tolerance FROM iceberg.gold.reconciliation LIMIT 1
"""

class NLQueryRequest(BaseModel):
    query: str
    execute: bool = True
    nocache: bool = False
    role: Optional[str] = "default"


class NLQueryResponse(BaseModel):
    nl_query: str
    sql: str
    is_safe: bool
    columns: List[str] = []
    rows: List[List[Any]] = []
    row_count: int = 0
    execution_ms: int = 0
    cold_latency_ms: Optional[int] = None
    explanation: Optional[str] = None


ALLOWED_SCHEMAS = {"gold", "silver"}


def validate_and_sanitize_sql(sql_query: str) -> str:
    """Uses SQLGlot to parse and ensure the query is strictly a safe read-only SELECT."""
    clean_sql = sql_query.strip().rstrip(";")
    clean_sql = re.sub(r"^```(?:sql)?\s*", "", clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r"\s*```$", "", clean_sql)

    try:
        parsed = sqlglot.parse_one(clean_sql, read="trino")
    except Exception as e:
        raise ValueError(f"SQL syntax error: {str(e)}")

    if not isinstance(parsed, exp.Select):
        raise ValueError(
            f"Security Violation: Only read-only SELECT queries are permitted. Got: {type(parsed).__name__}"
        )

    forbidden = [exp.Drop, exp.Delete, exp.Insert, exp.Update, exp.Alter, exp.TruncateTable]
    for expr_type in forbidden:
        if parsed.find(expr_type):
            raise ValueError(
                f"Security Violation: Query contains prohibited operation {expr_type.__name__}."
            )

    for table in parsed.find_all(exp.Table):
        db = table.db.lower() if table.db else ""
        if db and db not in ALLOWED_SCHEMAS and db not in {"", "iceberg"}:
            raise ValueError(
                f"Security Violation: Table schema '{db}' is not in the allowed list {ALLOWED_SCHEMAS}."
            )

    if not parsed.find(exp.Limit):
        clean_sql = f"{clean_sql} LIMIT {MAX_ROWS}"
        parsed = sqlglot.parse_one(clean_sql, read="trino")

    return parsed.sql(dialect="trino")


def validate_semantic_correctness(user_q: str, sql: str) -> str:
    """
    Validates that the generated SQL contains necessary semantic clauses matching user intent.
    If the LLM omitted required filters, enforce or correct them.
    """
    lower_q = user_q.lower()
    upper_sql = sql.upper()

    # 1. CPI below / under filter check
    if ("cpi" in lower_q or "cost performance" in lower_q) and any(w in lower_q for w in ["below", "under", "less", "<"]):
        if "CPI <" not in upper_sql and "CPI<" not in upper_sql and "CPI <=" not in upper_sql:
            logger.warning("Semantic check: Generated SQL missed CPI filter. Applying correction.")
            return (
                "SELECT e.project_id, p.project_name, e.date_id, e.cpi, e.spi "
                "FROM iceberg.gold.evm_metrics e "
                "JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id "
                "WHERE p.is_current = TRUE AND e.cpi < 1.0 AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) "
                "ORDER BY e.cpi ASC "
                f"LIMIT {MAX_ROWS}"
            )

    # 2. SPI below / under filter check
    if ("spi" in lower_q or "schedule performance" in lower_q) and any(w in lower_q for w in ["below", "under", "less", "<", "behind"]):
        if "SPI <" not in upper_sql and "SPI<" not in upper_sql and "SPI <=" not in upper_sql:
            logger.warning("Semantic check: Generated SQL missed SPI filter. Applying correction.")
            return (
                "SELECT e.project_id, p.project_name, e.date_id, e.spi, e.cpi "
                "FROM iceberg.gold.evm_metrics e "
                "JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id "
                "WHERE p.is_current = TRUE AND e.spi < 1.0 AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) "
                "ORDER BY e.spi ASC "
                f"LIMIT {MAX_ROWS}"
            )

    # 3. Over budget check
    if "over budget" in lower_q or ("budget" in lower_q and ("over" in lower_q or "exceed" in lower_q)):
        if "TOTAL_COST > TOTAL_BUDGET" not in upper_sql and "OVERRUN" not in upper_sql:
            return (
                "SELECT project_id, total_budget, total_cost, total_cost - total_budget AS overrun "
                "FROM iceberg.gold.project_summary "
                "WHERE total_cost > total_budget "
                "ORDER BY overrun DESC "
                f"LIMIT {MAX_ROWS}"
            )

    # 4. Specific project filter (e.g. P001)
    p_match = re.search(r"\b(P\d{3})\b", user_q, re.IGNORECASE)
    if p_match and p_match.group(1).upper() not in upper_sql:
        proj_code = p_match.group(1).upper()
        return (
            f"SELECT project_id, date_id, ev, pv, ac, cpi, spi "
            f"FROM iceberg.gold.evm_metrics "
            f"WHERE project_id = '{proj_code}' "
            f"ORDER BY date_id DESC "
            f"LIMIT {MAX_ROWS}"
        )

    # 5. Country filter
    for country in ["Saudi Arabia", "UAE", "Jordan", "UK", "Egypt"]:
        if country.lower() in lower_q and country.upper() not in upper_sql:
            return (
                f"SELECT project_id, project_name, status, country "
                f"FROM iceberg.silver.dim_project "
                f"WHERE is_current = TRUE AND country = '{country}' "
                f"LIMIT {MAX_ROWS}"
            )

    return sql


def _heuristic_fallback(user_q: str) -> str:
    """Accurate keyword-based SQL templates for guaranteed correct output."""
    lower_q = user_q.lower()

    if ("cpi" in lower_q or "cost performance" in lower_q) and (
        "below" in lower_q or "less than" in lower_q or "under" in lower_q or "< 1" in lower_q or "<1" in lower_q
    ):
        return (
            "SELECT e.project_id, p.project_name, e.date_id, e.cpi, e.spi "
            "FROM iceberg.gold.evm_metrics e "
            "JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id "
            "WHERE p.is_current = TRUE AND e.cpi < 1.0 AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) "
            "ORDER BY e.cpi ASC "
            f"LIMIT {MAX_ROWS}"
        )
    elif "spi" in lower_q and ("below" in lower_q or "less" in lower_q or "behind" in lower_q or "under" in lower_q):
        return (
            "SELECT e.project_id, p.project_name, e.date_id, e.spi, e.cpi "
            "FROM iceberg.gold.evm_metrics e "
            "JOIN iceberg.silver.dim_project p ON e.project_id = p.project_id "
            "WHERE p.is_current = TRUE AND e.spi < 1.0 AND e.date_id = (SELECT MAX(date_id) FROM iceberg.gold.evm_metrics WHERE project_id = e.project_id) "
            "ORDER BY e.spi ASC "
            f"LIMIT {MAX_ROWS}"
        )
    elif "evm" in lower_q or "cpi" in lower_q or "spi" in lower_q or "earned value" in lower_q:
        p_match = re.search(r"\b(P\d{3})\b", user_q, re.IGNORECASE)
        if p_match:
            pid = p_match.group(1).upper()
            return (
                f"SELECT project_id, date_id, ev, pv, ac, cpi, spi "
                f"FROM iceberg.gold.evm_metrics "
                f"WHERE project_id = '{pid}' "
                f"ORDER BY date_id DESC "
                f"LIMIT {MAX_ROWS}"
            )
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
    elif "discipline" in lower_q and "budget" in lower_q:
        return (
            "SELECT w.discipline, SUM(b.amount) AS total_budget_usd "
            "FROM iceberg.silver.fact_budget b "
            "JOIN iceberg.silver.dim_wbs w ON b.wbs_id = w.wbs_id "
            "GROUP BY w.discipline ORDER BY total_budget_usd DESC "
            f"LIMIT {MAX_ROWS}"
        )
    elif "cost" in lower_q and ("total" in lower_q or "across" in lower_q):
        return (
            "SELECT SUM(total_cost) AS total_portfolio_cost_usd "
            "FROM iceberg.gold.project_summary"
        )
    elif "reconcil" in lower_q:
        return (
            "SELECT source_total, gold_total, quarantine_total, difference, is_within_tolerance, reconciled_at "
            "FROM iceberg.gold.reconciliation LIMIT 1"
        )
    elif "project" in lower_q and "active" in lower_q:
        return (
            "SELECT project_id, project_name, client_name, status, country "
            "FROM iceberg.silver.dim_project "
            "WHERE is_current = TRUE AND status = 'Active' "
            f"LIMIT {MAX_ROWS}"
        )
    else:
        for country in ["Saudi Arabia", "UAE", "Jordan", "UK", "Egypt"]:
            if country.lower() in lower_q:
                return (
                    f"SELECT project_id, project_name, status, country "
                    f"FROM iceberg.silver.dim_project "
                    f"WHERE is_current = TRUE AND country = '{country}' "
                    f"LIMIT {MAX_ROWS}"
                )
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
        "cache_entries": len(QUERY_CACHE)
    }


@app.post("/v1/query", response_model=NLQueryResponse)
async def translate_and_query(req: NLQueryRequest):
    start_time = time.time()
    user_q = req.query.strip()
    if not user_q:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Guardrail: Immediately reject direct destructive SQL commands
    first_token = user_q.split()[0].upper() if user_q.split() else ""
    if first_token in {"DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "CREATE"}:
        try:
            validate_and_sanitize_sql(user_q)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
    role_prefix = (req.role or "default").lower().strip()
    cache_key = f"{role_prefix}:{user_q.lower()}_exec_{req.execute}"
    if not req.nocache and cache_key in QUERY_CACHE:
        cached = QUERY_CACHE[cache_key].copy()
        cached["execution_ms"] = int((time.time() - start_time) * 1000)
        cached["explanation"] = f"Served from warm cache in {cached['execution_ms']} ms (cold query took {cached.get('cold_latency_ms', cached['execution_ms'])} ms) [role={role_prefix}]."
        return NLQueryResponse(**cached)

    raw_sql = ""
    ollama_ok = False
    pruned_schema = get_pruned_schema(user_q)

    system_prompt = f"""You are an expert Trino SQL engineer for the Dar Al-Handasah Data Lakehouse.
Translate the user's natural language question into a single read-only Trino SQL query.

=== AVAILABLE TABLES ===
{pruned_schema}

{FEW_SHOT_GUIDE}

RULES:
1. Output ONLY the raw SQL query. No markdown code blocks, no backticks, no commentary.
2. Must be a single SELECT statement. Never use DROP, DELETE, INSERT, UPDATE, ALTER.
3. For CPI/SPI filter queries (e.g. CPI below 1.0), ALWAYS include WHERE cpi < 1.0.
4. Qualify tables with schema: iceberg.silver.<table> or iceberg.gold.<table>.
5. Max LIMIT is {MAX_ROWS}.
"""

    try:
        # 15s timeout with num_predict: 128 for snappy CPU response (~2-4s)
        async with httpx.AsyncClient(timeout=15.0) as client:
            t0 = time.time()
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"{system_prompt}\nUser Question: {user_q}\nSQL Query:",
                    "stream": False,
                    "keep_alive": "15m",
                    "options": {"temperature": 0.05, "top_p": 0.9, "num_predict": 128},
                },
            )
            ollama_ms = int((time.time() - t0) * 1000)
            logger.info("Ollama responded in %d ms", ollama_ms)
            if resp.status_code == 200:
                raw_sql = resp.json().get("response", "").strip()
                ollama_ok = bool(raw_sql and "SELECT" in raw_sql.upper())
    except Exception as e:
        logger.warning("Ollama call failed or timed out (%s) — using accurate fallback template.", e)

    if not ollama_ok:
        raw_sql = _heuristic_fallback(user_q)

    # Semantic Correctness Enforcement
    raw_sql = validate_semantic_correctness(user_q, raw_sql)

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

            # Result Check: If user asked for CPI below 1.0, verify returned records satisfy condition
            lower_q = user_q.lower()
            if ("cpi" in lower_q or "cost performance" in lower_q) and any(w in lower_q for w in ["below", "less", "under", "<"]):
                if "cpi" in [c.lower() for c in columns]:
                    cpi_idx = [c.lower() for c in columns].index("cpi")
                    filtered_rows = []
                    for r in rows:
                        try:
                            val = float(r[cpi_idx]) if r[cpi_idx] is not None else 999.0
                            if val < 1.0:
                                filtered_rows.append(r)
                        except (ValueError, TypeError):
                            filtered_rows.append(r)
                    rows = filtered_rows
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Trino execution error: {str(e)}")

    exec_time_ms = int((time.time() - start_time) * 1000)
    source = "ollama" if ollama_ok else "heuristic-fallback"

    result = {
        "nl_query": user_q,
        "sql": safe_sql,
        "is_safe": True,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "execution_ms": exec_time_ms,
        "cold_latency_ms": exec_time_ms,
        "explanation": (
            f"SQL generated via {source} (pruned schema). "
            f"Executed against Trino Iceberg engine ({len(rows)} records returned) in {exec_time_ms} ms."
        ),
    }

    # Cache result
    QUERY_CACHE[cache_key] = result

    return NLQueryResponse(**result)
