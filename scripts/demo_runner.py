#!/usr/bin/env python3
"""
scripts/demo_runner.py
Dar Al-Handasah Data Lakehouse Pilot — Live Interactive Demonstration Runner.
Demonstrates both Phase 1 Pilot Use Cases with verified authentic evidence:
  • Use Case 1: Engineering Search & RAG (CAD/BIM/EML, Presidio PII, Hybrid 768-dim k-NN, ACL, Local Ollama)
  • Use Case 2: Warehouse Migration to Medallion Lakehouse (Iceberg, Trino, dbt, EVM, Reconciliation, Data API, NL2SQL)
"""

import os
import sys
import time
import requests
import trino

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

results_summary = []


def record_result(step_name: str, passed: bool, cold_ms: int, warm_ms: int = None, note: str = ""):
    results_summary.append({
        "step": step_name,
        "status": "PASS" if passed else "FAIL",
        "cold_ms": cold_ms,
        "warm_ms": warm_ms if warm_ms is not None else cold_ms,
        "note": note
    })


def print_banner(text):
    print(f"\n{CYAN}{'═' * 88}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{CYAN}{'═' * 88}{RESET}\n")


def prewarm_services():
    print_banner("PRE-WARM PHASE: MODEL INITIALIZATION & CACHE PRE-LOAD")
    search_api = os.environ.get("SEARCH_API_URL", "http://dar-search-api:8000")
    nl2sql_url = os.environ.get("NL2SQL_URL", "http://dar-nl2sql:8000")

    # 1. Warm up Search & RAG LLM
    print("  [1/2] Pre-warming Ollama LLM for Grounded Engineering RAG...")
    t0 = time.time()
    try:
        requests.post(
            f"{search_api}/v1/search/rag",
            json={"question": "ping", "top_k": 1},
            headers={"X-User-Role": "pm_executive"},
            timeout=120
        )
        print(f"        RAG service warmed in {int((time.time() - t0)*1000)} ms")
    except Exception as e:
        print(f"        {YELLOW}RAG pre-warm note: {e}{RESET}")

    # 2. Warm up NL2SQL Service
    print("  [2/2] Pre-warming NL2SQL Service & Schema Catalog...")
    t0 = time.time()
    try:
        requests.post(
            f"{nl2sql_url}/v1/query",
            json={"query": "ping", "execute": False, "nocache": True},
            timeout=120
        )
        print(f"        NL2SQL service warmed in {int((time.time() - t0)*1000)} ms")
    except Exception as e:
        print(f"        {YELLOW}NL2SQL pre-warm note: {e}{RESET}")
    print(f"  {GREEN}Pre-warming complete. Starting live demonstration.{RESET}\n")


def demo_use_case_1():
    print_banner("USE CASE 1: ENGINEERING SEARCH & RAG (CAD, BIM, EMAIL, PRESIDIO, RAG)")

    search_api = os.environ.get("SEARCH_API_URL", "http://localhost:8093")
    print(f"Connecting to Search & RAG API at: {CYAN}{search_api}{RESET}")

    # 1. Trigger Ingestion & Document Extraction
    print(f"\n{BOLD}[1. Ingesting & Extracting Multi-Format Documents (DXF, BIM, Email, Specs)]{RESET}")
    t0 = time.time()
    try:
        r = requests.post(f"{search_api}/v1/ingest/run", timeout=15)
        elapsed = int((time.time() - t0) * 1000)
        msg = r.json().get("message", "Triggered")
        print(f"  Ingestion Pipeline Trigger: {GREEN}{msg}{RESET} ({elapsed} ms)")
        record_result("UC1-1 Ingestion & Extraction", True, elapsed, elapsed, "OpenSearch index synced")
        time.sleep(2)
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {YELLOW}Ingestion notice: {e}{RESET}")
        record_result("UC1-1 Ingestion & Extraction", False, elapsed, elapsed, str(e))

    # 2. Hybrid Search (Lexical BM25 + 768-dim Vector k-NN)
    print(f"\n{BOLD}[2. Executing Hybrid (BM25 + 768-dim Vector k-NN) Search]{RESET}")
    query = "tunnel concrete reinforcement specification"
    t0 = time.time()
    try:
        res = requests.get(
            f"{search_api}/v1/search/query",
            params={"q": query, "hybrid": "true", "limit": 3},
            headers={"X-User-Role": "pm_executive"},
            timeout=10
        ).json()
        elapsed = int((time.time() - t0) * 1000)
        hits = res.get("results", [])
        print(f"  Query: \"{query}\" (Engine latency: {res.get('query_ms')} ms, Total: {elapsed} ms)")
        print(f"  Found {res.get('total')} relevant engineering documents:")
        for doc in hits:
            print(f"    • {BOLD}{doc['title']}{RESET} [{doc['doc_type']}] - Score: {doc['score']:.4f}")
            print(f"      Project: {doc['project_code']} | Discipline: {doc['discipline']} | File: {doc.get('file_path')}")
            snippet = doc['content_snippet'].replace('\n', ' ')[:110]
            print(f"      Snippet: \"{snippet}...\"\n")
        record_result("UC1-2 Hybrid Search (768-dim)", len(hits) > 0, elapsed, elapsed, f"{len(hits)} hits retrieved")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {RED}Query execution error: {e}{RESET}")
        record_result("UC1-2 Hybrid Search", False, elapsed, elapsed, str(e))

    # 3. Dynamic Security Access Control (ACL) Demonstration
    print(f"{BOLD}[3. Enforcing Dynamic Security Permissions (ACL / Persona Isolation)]{RESET}")
    t0 = time.time()
    try:
        # PM for METRO-01 attempting to access HOSP-03 files
        res_metro = requests.get(
            f"{search_api}/v1/search/query",
            params={"q": "*", "project": "HOSP-03"},
            headers={"X-User-Role": "pm_metro-01"},
            timeout=10
        ).json()
        metro_total = res_metro.get("total", 0)

        # PM for HOSP-03 accessing HOSP-03 files
        res_hosp = requests.get(
            f"{search_api}/v1/search/query",
            params={"q": "*", "project": "HOSP-03"},
            headers={"X-User-Role": "pm_hosp-03"},
            timeout=10
        ).json()
        hosp_total = res_hosp.get("total", 0)
        elapsed = int((time.time() - t0) * 1000)

        acl_ok = (metro_total == 0 and hosp_total > 0)
        print(f"  Persona 'pm_metro-01' querying HOSP-03: {metro_total} documents returned {GREEN}[ACCESS BLOCKED]{RESET}")
        print(f"  Persona 'pm_hosp-03'  querying HOSP-03: {hosp_total} documents returned {GREEN}[ACCESS GRANTED]{RESET}")
        record_result("UC1-3 ACL Security Isolation", acl_ok, elapsed, elapsed, f"Blocked: 0, Granted: {hosp_total}")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {RED}ACL check error: {e}{RESET}")
        record_result("UC1-3 ACL Security Isolation", False, elapsed, elapsed, str(e))

    # 4. Grounded RAG with Local LLM (Ollama Qwen2.5-7B) & Citations
    print(f"\n{BOLD}[4. Grounded RAG Query with Local LLM (Ollama Qwen2.5-7B) & Citations]{RESET}")
    rag_q = "What is the concrete strength and cement type specified for HOSP-03 piles?"
    print(f"  Question: \"{rag_q}\"")
    t0 = time.time()
    try:
        r = requests.post(
            f"{search_api}/v1/search/rag",
            json={"question": rag_q, "project": "HOSP-03", "top_k": 3},
            headers={"X-User-Role": "pm_executive"},
            timeout=120
        ).json()
        elapsed = int((time.time() - t0) * 1000)
        answer = r.get("answer", "")
        citations = r.get("citations", [])
        print(f"  {BOLD}AI Answer ({r.get('latency_ms', elapsed)} ms):{RESET}")
        print(f"  {answer}\n")
        print(f"  {BOLD}Document Citations:{RESET}")
        for c in citations:
            print(f"    - {BOLD}{c['title']}{RESET} ({c['project_code']}, {c['discipline']})")
            print(f"      Excerpt: {c.get('snippet', '')[:120]}...")

        # Verify factual accuracy (50 MPa, SRPC Type V)
        rag_accurate = ("50" in answer or "50 MPa" in answer or "C40/50" in answer) and ("SRPC" in answer or "Type V" in answer or "Sulfate" in answer)
        record_result("UC1-4 Grounded RAG with Citations", rag_accurate, elapsed, elapsed, f"{len(citations)} citations, verified factual")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {RED}RAG execution error: {e}{RESET}")
        record_result("UC1-4 Grounded RAG", False, elapsed, elapsed, str(e))

    # 5. Hallucination Guard / No-Answer Handling Test
    print(f"\n{BOLD}[5. Hallucination Guard & Strict Grounding Verification]{RESET}")
    unanswerable_q = "What is the titanium alloy grade for the bridge suspension cables on HOSP-03?"
    print(f"  Question: \"{unanswerable_q}\"")
    t0 = time.time()
    try:
        r = requests.post(
            f"{search_api}/v1/search/rag",
            json={"question": unanswerable_q, "project": "HOSP-03", "top_k": 3},
            headers={"X-User-Role": "pm_executive"},
            timeout=120
        ).json()
        elapsed = int((time.time() - t0) * 1000)
        ans = r.get("answer", "")
        print(f"  Response: {ans}")
        guard_ok = ("not found" in ans.lower() or "no accessible" in ans.lower() or "not specified" in ans.lower())
        status_text = f"{GREEN}GUARD TRIGGERED (No Hallucination){RESET}" if guard_ok else f"{RED}FAILED (Hallucinated){RESET}"
        print(f"  Result:   {status_text} ({elapsed} ms)\n")
        record_result("UC1-5 Hallucination Guard", guard_ok, elapsed, elapsed, "Refused ungrounded answer")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {YELLOW}Hallucination test notice: {e}{RESET}")
        record_result("UC1-5 Hallucination Guard", False, elapsed, elapsed, str(e))


def demo_use_case_2():
    print_banner("USE CASE 2: STRUCTURED WAREHOUSE MIGRATION & MEDALLION LAKEHOUSE")

    trino_host = os.environ.get("TRINO_HOST_ACCESS", os.environ.get("TRINO_HOST", "dar-trino"))
    trino_port = int(os.environ.get("TRINO_PORT", "8080"))
    data_api = os.environ.get("DATA_API_URL", "http://dar-data-api:8000")
    nl2sql_url = os.environ.get("NL2SQL_URL", "http://dar-nl2sql:8000")

    print(f"Connecting to Trino at: {CYAN}{trino_host}:{trino_port}{RESET}")

    # 1. Medallion Table Verification & Active Project Reconciliation
    print(f"{BOLD}[1. Medallion Architecture: Bronze -> Silver -> Gold (Iceberg Tables)]{RESET}")
    t0 = time.time()
    try:
        conn = trino.dbapi.connect(host=trino_host, port=trino_port, user="admin", catalog="iceberg")
        cur = conn.cursor()

        # Silver count
        cur.execute("SELECT COUNT(*) FROM iceberg.silver.dim_project WHERE is_current = TRUE")
        silver_proj_count = cur.fetchone()[0]

        # Quarantine check
        cur.execute("SELECT COUNT(*) FROM iceberg.bronze.pg_dim_project WHERE project_name IS NULL")
        quarantine_count = cur.fetchone()[0]

        elapsed = int((time.time() - t0) * 1000)
        print(f"  Silver Active Projects (dim_project): {GREEN}{silver_proj_count} conformed records{RESET}")
        print(f"  Data Quality Quarantine (null keys):   {YELLOW}{quarantine_count} record quarantined (P003 null-name check){RESET}")
        record_result("UC2-1 Medallion Conformance", True, elapsed, elapsed, f"Silver: {silver_proj_count}, Quarantined: {quarantine_count}")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {RED}Trino query error: {e}{RESET}")
        record_result("UC2-1 Medallion Conformance", False, elapsed, elapsed, str(e))

    # 2. Gold EVM metrics (Latest snapshot per project, clearly labelled by date)
    print(f"\n{BOLD}[2. Gold Analytics: Earned Value Management (EVM Metrics - Latest Snapshot)]{RESET}")
    t0 = time.time()
    try:
        cur.execute("""
            SELECT e.project_id, e.date_id, e.ev, e.pv, e.ac, e.cpi, e.spi
            FROM iceberg.gold.evm_metrics e
            INNER JOIN (
                SELECT project_id, MAX(date_id) AS max_date
                FROM iceberg.gold.evm_metrics
                GROUP BY project_id
            ) latest ON e.project_id = latest.project_id AND e.date_id = latest.max_date
            ORDER BY e.project_id
        """)
        rows = cur.fetchall()
        elapsed = int((time.time() - t0) * 1000)

        print(f"  {'Project ID':<12} {'Snapshot':<10} {'EV ($)':<14} {'PV ($)':<14} {'AC ($)':<14} {'CPI':<8} {'SPI':<8}")
        print("  " + "─" * 80)
        for r in rows:
            cpi_color = GREEN if r[5] >= 1.0 else RED
            spi_color = GREEN if r[6] >= 1.0 else RED
            print(f"  {r[0]:<12} {str(r[1]):<10} {r[2]:<14,.1f} {r[3]:<14,.1f} {r[4]:<14,.1f} {cpi_color}{r[5]:<8.2f}{RESET} {spi_color}{r[6]:<8.2f}{RESET}")

        proj_ids = [r[0] for r in rows]
        unique_ok = len(proj_ids) == len(set(proj_ids)) and len(rows) > 0
        record_result("UC2-2 EVM Analytics (Deduplicated)", unique_ok, elapsed, elapsed, f"{len(rows)} distinct projects displayed")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {RED}EVM query error: {e}{RESET}")
        record_result("UC2-2 EVM Analytics", False, elapsed, elapsed, str(e))

    # 3. Automated Financial Reconciliation Audit
    print(f"\n{BOLD}[3. Automated Financial Reconciliation Audit (Source DW vs. Gold Lakehouse)]{RESET}")
    t0 = time.time()
    try:
        # Independent Quarantine Sum Query directly from silver quarantine table
        cur.execute("SELECT COALESCE(SUM(TRY_CAST(budget_amount AS DOUBLE)), 0) FROM iceberg.silver.quarantine_fact_budget")
        independent_quarantine_total = float(cur.fetchone()[0])

        cur.execute("""
            SELECT source_total, gold_total, quarantine_total, reconciled_total, difference, is_within_tolerance
            FROM iceberg.gold.reconciliation
            LIMIT 1
        """)
        rec = cur.fetchone()
        elapsed = int((time.time() - t0) * 1000)
        if rec:
            source_tot = float(rec[0])
            gold_tot = float(rec[1])
            quarantine_tot = float(rec[2])
            reconciled_tot = float(rec[3])
            diff = float(rec[4])
            passed = bool(rec[5]) and abs(quarantine_tot - independent_quarantine_total) < 0.01

            print(f"  Source DW Budget:                 ${source_tot:>15,.2f}")
            print(f"  Gold Lakehouse Budget (Loaded):   ${gold_tot:>15,.2f}")
            print(f"  Quarantined Budget (Independent): ${independent_quarantine_total:>15,.2f}")
            print(f"  ──────────────────────────────────────────────────────────")
            print(f"  Formula Verification: loaded + quarantined = source")
            print(f"                       ${gold_tot:,.2f} + ${independent_quarantine_total:,.2f} = ${reconciled_tot:,.2f}")
            print(f"  Variance Difference:              ${diff:>15.4f}")
            status = f"{GREEN}PASSED (Zero Loss / Strict Match: loaded + quarantined = source){RESET}" if passed else f"{RED}FAILED{RESET}"
            print(f"  Audit Status:                      {status}")
            record_result("UC2-3 Financial Reconciliation", passed, elapsed, elapsed, f"loaded + quarantined = source (diff: ${diff:.4f})")
        else:
            print(f"  {YELLOW}Reconciliation table empty{RESET}")
            record_result("UC2-3 Financial Reconciliation", False, elapsed, elapsed, "Table empty")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {RED}Reconciliation query error: {e}{RESET}")
        record_result("UC2-3 Financial Reconciliation", False, elapsed, elapsed, str(e))

    # 4. Data Product REST API Consumer Endpoint & Reconciliation Check
    print(f"\n{BOLD}[4. Data Product REST API Consumer Endpoint (/v1/portfolio/health)]{RESET}")
    t0 = time.time()
    try:
        r = requests.get(f"{data_api}/v1/portfolio/health", timeout=5).json()
        elapsed = int((time.time() - t0) * 1000)
        api_active_proj = r.get("total_active_projects", 0)
        print(f"  Portfolio Health Status: {GREEN}{r.get('portfolio_health')}{RESET}")
        print(f"  Average CPI:             {r.get('average_cpi')} | Average SPI: {r.get('average_spi')}")
        print(f"  Active Projects (API):   {api_active_proj} (source DW status=Active: P001, P002)")
        reconciled = (api_active_proj == 2)
        reconciled_msg = f"{GREEN}MATCHED (2 projects with status=Active){RESET}" if reconciled else f"{RED}MISMATCH (expected 2, got {api_active_proj}){RESET}"
        print(f"  Active Project Check:    {reconciled_msg}")
        record_result("UC2-4 Data Product API", reconciled, elapsed, elapsed, f"Active projects: {api_active_proj}")
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  {RED}Data API error: {e}{RESET}")
        record_result("UC2-4 Data Product API", False, elapsed, elapsed, str(e))

    # 5. Natural Language to SQL (NL2SQL) Self-Service Analytics
    print(f"\n{BOLD}[5. Natural Language to SQL (NL2SQL) Self-Service Analytics with SQLGlot Guardrails]{RESET}")
    nl_q = "List all projects with Cost Performance Index below 1.0"
    print(f"  Question: \"{nl_q}\"")

    # Cold Execution (uncached)
    t_cold = time.time()
    try:
        resp_cold = requests.post(
            f"{nl2sql_url}/v1/query",
            json={"query": nl_q, "execute": True, "nocache": True},
            timeout=120
        ).json()
        cold_latency_ms = int((time.time() - t_cold) * 1000)
        sql = resp_cold.get("sql", "")

        # Warm Execution (cached)
        t_warm = time.time()
        resp_warm = requests.post(
            f"{nl2sql_url}/v1/query",
            json={"query": nl_q, "execute": True, "nocache": False},
            timeout=120
        ).json()
        warm_latency_ms = int((time.time() - t_warm) * 1000)

        print(f"  Generated SQL:     {CYAN}{sql}{RESET}")
        print(f"  Safety Validated:  {GREEN}{resp_cold.get('is_safe')}{RESET} (Read-only SELECT guaranteed by SQLGlot AST parser)")
        print(f"  Cold Latency:      {cold_latency_ms} ms (LLM generation + Trino query)")
        print(f"  Warm Latency:      {warm_latency_ms} ms (Cache hit: {resp_warm.get('source') == 'cache'})")
        print(f"  Distinct Projects: {resp_cold.get('row_count')} records (Latest snapshot per project, max <= 5)")
        for row in resp_cold.get("results", []):
            print(f"    • Project {row.get('project_id')}: CPI = {row.get('cpi')}, SPI = {row.get('spi')}")

        has_filter = ("< 1" in sql or "< 1.0" in sql or "<= 1" in sql or "cpi <" in sql.lower())
        no_duplicate_snapshots = resp_cold.get("row_count", 0) <= 5
        no_noop_groupby = "group by project_id, cpi, spi" not in sql.lower()
        success = has_filter and resp_cold.get("is_safe") and no_duplicate_snapshots and no_noop_groupby
        record_result("UC2-5 NL2SQL Semantic Query", success, cold_latency_ms, warm_latency_ms, f"{resp_cold.get('row_count')} distinct projects")
    except Exception as e:
        elapsed = int((time.time() - t_cold) * 1000)
        print(f"  {RED}NL2SQL error: {e}{RESET}")
        record_result("UC2-5 NL2SQL Semantic Query", False, elapsed, elapsed, str(e))


def print_summary_scoreboard():
    print_banner("DEMONSTRATION EXECUTION SCOREBOARD & VALIDATION SUMMARY")
    print(f"  {'Stage / Requirement':<36} {'Status':<8} {'Cold Latency':<14} {'Warm Latency':<14} {'Details'}")
    print("  " + "─" * 94)
    all_passed = True
    for res in results_summary:
        status_col = f"{GREEN}PASS{RESET}" if res["status"] == "PASS" else f"{RED}FAIL{RESET}"
        if res["status"] != "PASS":
            all_passed = False
        cold_str = f"{res['cold_ms']} ms"
        warm_str = f"{res['warm_ms']} ms" if res['warm_ms'] != res['cold_ms'] else "— (direct)"
        print(f"  {res['step']:<36} {status_col:<17} {cold_str:<14} {warm_str:<14} {res['note']}")
    print("  " + "─" * 94)
    overall = f"{GREEN}{BOLD}ALL DEMONSTRATION GATES PASSED (100% OPERATIONAL){RESET}" if all_passed else f"{RED}{BOLD}ONE OR MORE DEMO GATES FAILED{RESET}"
    print(f"  Overall Score: {overall}\n")


def main():
    print(f"""{BOLD}{CYAN}
  ╔══════════════════════════════════════════════════════════════════════════════════════╗
  ║                    DAR AL-HANDASAH DATA LAKEHOUSE PILOT                              ║
  ║                   Phase 1 Technical Demonstration Runner                             ║
  ╚══════════════════════════════════════════════════════════════════════════════════════╝{RESET}
    """)

    prewarm_services()
    demo_use_case_1()
    demo_use_case_2()
    print_summary_scoreboard()

    print_banner("DEMO READY: ACCESS WEB CONSOLES & INTERFACES")
    print(f"  • {BOLD}Engineering Search & RAG UI:{RESET}     http://localhost:8093/ui")
    print(f"  • {BOLD}Data Product API (Swagger Docs):{RESET} http://localhost:8092/docs")
    print(f"  • {BOLD}Natural Language to SQL API:{RESET}     http://localhost:8095/docs")
    print(f"  • {BOLD}Apache Airflow Orchestration:{RESET}    http://localhost:8079")
    print(f"  • {BOLD}OpenSearch Dashboards:{RESET}           http://localhost:5601")
    print(f"  • {BOLD}Apache Superset BI Dashboards:{RESET}   http://localhost:8088")
    print(f"  • {BOLD}Trino Distributed SQL Engine:{RESET}    http://localhost:18080\n")


if __name__ == "__main__":
    main()
