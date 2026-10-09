"""
uc2-warehouse-migration/nl2sql/main.py — Natural Language to SQL Microservice
Dar Al-Handasah Data Lakehouse Pilot.

Translates business user natural language queries into valid Trino SQL over Iceberg
Silver and Gold data products. Uses SQLGlot for AST safety verification (read-only enforcement)
and Ollama Qwen2.5-7B for query formulation.
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

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_LLM_MODEL", "qwen2.5:7b-instruct-q4_K_M")
TRINO_HOST = os.environ.get("TRINO_HOST", "trino")
TRINO_PORT = int(os.environ.get("TRINO_PORT", "8080"))
TRINO_USER = os.environ.get("TRINO_USER", "admin")
TRINO_CATALOG = os.environ.get("TRINO_CATALOG", "iceberg")

app = FastAPI(
    title="Dar Lakehouse — Natural Language to SQL Service",
    version="1.0.0",
    description="Text-to-SQL engine powered by Ollama and SQLGlot validation for Trino Iceberg data",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SCHEMA_CONTEXT = """
=== AVAILABLE TRINO ICEBERG TABLES ===
1. Table: iceberg.silver.dim_project
   Columns:
     - project_id (VARCHAR): Unique project code (e.g. 'METRO-01', 'BRIDGE-02')
     - project_name (VARCHAR): Full name of the engineering project
     - client_name (VARCHAR): Name of the client entity
     - project_type (VARCHAR): Type (e.g. 'Infrastructure', 'Healthcare', 'High-Rise')
     - country (VARCHAR): Country of execution
     - status (VARCHAR): Project lifecycle status ('Active', 'Completed', 'Planning')
     - is_current (BOOLEAN): TRUE for active current record

2. Table: iceberg.silver.dim_wbs
   Columns:
     - wbs_id (VARCHAR): Unique WBS identifier
     - project_id (VARCHAR): Parent project code
     - wbs_code (VARCHAR): Hierarchical code (e.g. '1.01.02')
     - wbs_name (VARCHAR): Descriptive task name
     - discipline (VARCHAR): Engineering discipline ('Structural', 'Civil', 'MEP')

3. Table: iceberg.silver.fact_budget
   Columns:
     - budget_id (VARCHAR): Unique budget line identifier
     - wbs_id (VARCHAR): Associated WBS code
     - amount (DOUBLE): Budget amount normalized to USD
     - currency (VARCHAR): Always 'USD' in silver

4. Table: iceberg.gold.evm_metrics
   Columns:
     - project_id (VARCHAR): Project code
     - date_id (VARCHAR): Snapshot date
     - ev (DOUBLE): Earned Value (USD)
     - pv (DOUBLE): Planned Value (USD)
     - ac (DOUBLE): Actual Cost (USD)
     - bac (DOUBLE): Budget at Completion (USD)
     - sv (DOUBLE): Schedule Variance (EV - PV)
     - cv (DOUBLE): Cost Variance (EV - AC)
     - spi (DOUBLE): Schedule Performance Index (EV / PV)
     - cpi (DOUBLE): Cost Performance Index (EV / AC)
     - eac (DOUBLE): Estimate at Completion
     - vac (DOUBLE): Variance at Completion

5. Table: iceberg.gold.reconciliation
   Columns:
     - source_total (DOUBLE): Total budget from legacy SQL Server DW
     - gold_total (DOUBLE): Total budget calculated in Lakehouse
     - difference (DOUBLE): Absolute variance
     - is_within_tolerance (BOOLEAN): TRUE if variance < 0.01 USD
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


def validate_and_sanitize_sql(sql_query: str) -> str:
    """Uses SQLGlot to parse, format, and ensure query is strictly a safe read-only SELECT."""
    clean_sql = sql_query.strip().rstrip(";")
    # Strip markdown quotes if LLM wrapped in ```sql ... ```
    clean_sql = re.sub(r"^```(?:sql)?\s*", "", clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r"\s*```$", "", clean_sql)

    try:
        parsed = sqlglot.parse_one(clean_sql, read="trino")
    except Exception as e:
        raise ValueError(f"SQL syntax error: {str(e)}")

    # Strictly check that the root expression is a SELECT
    if not isinstance(parsed, exp.Select):
        raise ValueError("Security Violation: Only read-only SELECT queries are permitted.")

    # Guard against DDL/DML mutation keywords
    forbidden = [exp.Drop, exp.Delete, exp.Insert, exp.Update, exp.AlterTable, exp.TruncateTable]
    for expr_type in forbidden:
        if parsed.find(expr_type):
            raise ValueError(f"Security Violation: Query contains prohibited operation {expr_type.__name__}.")

    return parsed.sql(dialect="trino")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "dar-nl2sql",
        "ollama_host": OLLAMA_HOST,
        "llm_model": OLLAMA_MODEL,
        "trino_target": f"{TRINO_HOST}:{TRINO_PORT}"
    }


@app.post("/v1/query", response_model=NLQueryResponse)
async def translate_and_query(req: NLQueryRequest):
    start_time = time.time()
    user_q = req.query.strip()
    if not user_q:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    system_prompt = f"""You are an expert Trino SQL engineer for the Dar Al-Handasah Data Lakehouse.
Your task is to translate the user's natural language question into a clean, syntactically correct Trino SQL query over Apache Iceberg tables.

{SCHEMA_CONTEXT}

RULES:
1. Output ONLY the raw SQL query. Do NOT add any preamble, markdown formatting, backticks, or commentary.
2. The query MUST be a read-only SELECT statement.
3. Always prefix tables with the catalog and schema: `iceberg.silver.<table_name>` or `iceberg.gold.<table_name>`.
4. Use standard ANSI/Trino SQL functions. Use NULLIF to avoid division by zero when calculating ratios.
5. Limit results to 50 rows unless explicitly requested otherwise.
"""

    raw_sql = ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"{system_prompt}\nUser Question: {user_q}\nSQL Query:",
                    "stream": False,
                    "options": {"temperature": 0.1, "top_p": 0.8}
                }
            )
            if resp.status_code == 200:
                raw_sql = resp.json().get("response", "").strip()
    except Exception as e:
        print(f"Ollama call failed ({e}); checking fallback heuristics.")

    # Fallback heuristic templates if Ollama is offline or warming up
    if not raw_sql or "SELECT" not in raw_sql.upper():
        lower_q = user_q.lower()
        if "cpi" in lower_q or "evm" in lower_q or "performance" in lower_q:
            raw_sql = "SELECT project_id, date_id, ev, pv, ac, cpi, spi FROM iceberg.gold.evm_metrics ORDER BY date_id DESC LIMIT 20"
        elif "budget" in lower_q:
            raw_sql = "SELECT wbs_id, total_budget, currency FROM iceberg.gold.budget_vs_actual ORDER BY total_budget DESC LIMIT 20"
        elif "reconcil" in lower_q:
            raw_sql = "SELECT source_total, gold_total, difference, is_within_tolerance FROM iceberg.gold.reconciliation"
        else:
            raw_sql = "SELECT project_id, project_name, client_name, status, country FROM iceberg.silver.dim_project WHERE is_current = TRUE LIMIT 20"

    # SQLGlot Safety Validation
    try:
        safe_sql = validate_and_sanitize_sql(raw_sql)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    columns = []
    rows = []
    if req.execute:
        try:
            conn = trino.dbapi.connect(
                host=TRINO_HOST,
                port=TRINO_PORT,
                user=TRINO_USER,
                catalog=TRINO_CATALOG
            )
            cursor = conn.cursor()
            cursor.execute(safe_sql)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            raw_rows = cursor.fetchall()
            rows = [[str(val) if val is not None else None for val in r] for r in raw_rows]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Trino execution error: {str(e)}")

    exec_time_ms = int((time.time() - start_time) * 1000)
    return NLQueryResponse(
        nl_query=user_q,
        sql=safe_sql,
        is_safe=True,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_ms=exec_time_ms,
        explanation=f"Executed against Trino Iceberg engine ({len(rows)} records returned)."
    )
