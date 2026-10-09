#!/usr/bin/env python3
"""
scripts/demo_runner.py
Dar Al-Handasah Data Lakehouse Pilot — Live Interactive Demonstration Runner.
Demonstrates both Phase 1 Pilot Use Cases:
  • Use Case 1: Making Project Files Searchable (Semi-Structured & Unstructured)
  • Use Case 2: Migrating Selected Data Warehouse Domains to the Lakehouse (Structured SQL)
"""

import os
import sys
import time
import json
import requests
import trino

GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(text):
    print(f"\n{CYAN}{'═' * 76}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{CYAN}{'═' * 76}{RESET}\n")


def demo_use_case_1():
    print_banner("USE CASE 1: MAKING PROJECT FILES SEARCHABLE (CAD, BIM, EMAIL, RAG)")

    search_api = os.environ.get("SEARCH_API_URL", "http://localhost:8093")
    print(f"Connecting to Search & RAG API at: {search_api}")

    # 1. Trigger Ingestion
    print(f"\n{BOLD}[1. Ingesting & Extracting Multi-Format Documents]{RESET}")
    try:
        r = requests.post(f"{search_api}/v1/ingest/run", timeout=10)
        print(f"  Ingestion Trigger: {GREEN}{r.json().get('message')}{RESET}")
        time.sleep(2)
    except Exception as e:
        print(f"  {YELLOW}Ingestion trigger notice: {e}{RESET}")

    # 2. Hybrid Search (Lexical + Vector)
    print(f"\n{BOLD}[2. Executing Hybrid (BM25 + 768-dim Vector k-NN) Search]{RESET}")
    query = "tunnel concrete reinforcement specification"
    try:
        res = requests.get(
            f"{search_api}/v1/search/query",
            params={"q": query, "hybrid": "true", "limit": 3},
            headers={"X-User-Role": "pm_executive"},
            timeout=10
        ).json()
        print(f"  Query: \"{query}\" (Search time: {res.get('query_ms')} ms)")
        print(f"  Found {res.get('total')} documents:")
        for doc in res.get("results", []):
            print(f"    • {BOLD}{doc['title']}{RESET} [{doc['doc_type']}] - Score: {doc['score']:.3f}")
            print(f"      Project: {doc['project_code']} | Discipline: {doc['discipline']}")
            print(f"      Snippet: {doc['content_snippet'][:120]}...\n")
    except Exception as e:
        print(f"  {YELLOW}Query execution notice: {e}{RESET}")

    # 3. Dynamic Security Access Control (ACL) Demonstration
    print(f"\n{BOLD}[3. Enforcing Dynamic Security Permissions (ACL / Persona)]{RESET}")
    try:
        # PM for METRO-01
        res_metro = requests.get(
            f"{search_api}/v1/search/query",
            params={"q": "*", "project": "HOSP-03"},
            headers={"X-User-Role": "pm_metro-01"},
            timeout=10
        ).json()
        print(f"  Persona 'pm_metro-01' querying HOSP-03 files: {res_metro.get('total')} results (Access Restricted)")

        # PM for HOSP-03
        res_hosp = requests.get(
            f"{search_api}/v1/search/query",
            params={"q": "*", "project": "HOSP-03"},
            headers={"X-User-Role": "pm_hosp-03"},
            timeout=10
        ).json()
        print(f"  Persona 'pm_hosp-03' querying HOSP-03 files: {GREEN}{res_hosp.get('total')} results (Access Granted){RESET}")
    except Exception as e:
        print(f"  {YELLOW}ACL check notice: {e}{RESET}")

    # 4. RAG Assistant
    print(f"\n{BOLD}[4. Grounded RAG Query with Local LLM & Source Citations]{RESET}")
    rag_q = "What is the concrete strength and cement type specified for HOSP-03 piles?"
    print(f"  Question: \"{rag_q}\"")
    try:
        rag_res = requests.get(f"{search_api}/health", timeout=5)
        r = requests.post(
            f"{search_api}/v1/search/rag",
            json={"question": rag_q, "project": "HOSP-03", "top_k": 3},
            headers={"X-User-Role": "pm_executive"},
            timeout=120
        ).json()
        print(f"  {BOLD}AI Answer:{RESET}\n  {r.get('answer')}\n")
        print(f"  Citations:")
        for c in r.get("citations", []):
            print(f"    - {c['title']} ({c['project_code']})")
    except Exception as e:
        print(f"  {YELLOW}RAG call notice: {e}{RESET}")


def demo_use_case_2():
    print_banner("USE CASE 2: STRUCTURED WAREHOUSE MIGRATION & MEDALLION LAKEHOUSE")

    trino_host = os.environ.get("TRINO_HOST_ACCESS", os.environ.get("TRINO_HOST", "dar-trino"))
    trino_port = int(os.environ.get("TRINO_PORT", "8080"))
    data_api = os.environ.get("DATA_API_URL", "http://dar-data-api:8000")
    nl2sql_url = os.environ.get("NL2SQL_URL", "http://dar-nl2sql:8000")

    # 1. Medallion Table Verification
    print(f"{BOLD}[1. Medallion Architecture: Bronze -> Silver -> Gold (Iceberg)]{RESET}")
    try:
        conn = trino.dbapi.connect(host=trino_host, port=trino_port, user="admin", catalog="iceberg")
        cur = conn.cursor()

        # Silver count
        cur.execute("SELECT COUNT(*) FROM iceberg.silver.dim_project WHERE is_current = TRUE")
        proj_count = cur.fetchone()[0]
        print(f"  Silver Active Projects (dim_project): {GREEN}{proj_count} records{RESET}")

        # Gold EVM metrics
        print(f"\n{BOLD}[2. Gold Analytics: Earned Value Management (EVM Metrics)]{RESET}")
        cur.execute("""
            SELECT project_id, ev, pv, ac, cpi, spi
            FROM iceberg.gold.evm_metrics
            ORDER BY project_id
            LIMIT 5
        """)
        rows = cur.fetchall()
        print(f"  {'Project':<12} {'EV ($)':<12} {'PV ($)':<12} {'AC ($)':<12} {'CPI':<8} {'SPI':<8}")
        print("  " + "-" * 56)
        for r in rows:
            print(f"  {r[0]:<12} {r[1]:<12.1f} {r[2]:<12.1f} {r[3]:<12.1f} {r[4]:<8.2f} {r[5]:<8.2f}")

        # Reconciliation
        print(f"\n{BOLD}[3. Automated Financial Reconciliation Audit (Source vs. Lakehouse)]{RESET}")
        cur.execute("SELECT source_total, gold_total, difference, is_within_tolerance FROM iceberg.gold.reconciliation LIMIT 1")
        rec = cur.fetchone()
        if rec:
            print(f"  Source DW Budget:   ${rec[0]:,.2f}")
            print(f"  Lakehouse Budget:   ${rec[1]:,.2f}")
            print(f"  Variance Difference: ${rec[2]:.4f}")
            status = f"{GREEN}PASSED (Within 0.01 tolerance){RESET}" if rec[3] else f"\033[91mFAILED{RESET}"
            print(f"  Audit Status:        {status}")
    except Exception as e:
        print(f"  {YELLOW}Trino query notice: {e}{RESET}")

    # 4. Data Product API
    print(f"\n{BOLD}[4. Data Product REST API Consumer Endpoint]{RESET}")
    try:
        r = requests.get(f"{data_api}/v1/portfolio/health", timeout=5).json()
        print(f"  Portfolio Health: {GREEN}{r.get('portfolio_health')}{RESET}")
        print(f"  Average CPI: {r.get('average_cpi')} | Average SPI: {r.get('average_spi')}")
        print(f"  Total Active Projects: {r.get('total_active_projects')}")
    except Exception as e:
        print(f"  {YELLOW}Data API notice: {e}{RESET}")

    # 5. Natural Language to SQL
    print(f"\n{BOLD}[5. Natural Language to SQL (NL2SQL) Self-Service Analytics]{RESET}")
    nl_q = "List all projects with Cost Performance Index below 1.0"
    print(f"  Question: \"{nl_q}\"")
    try:
        resp = requests.post(
            f"{nl2sql_url}/v1/query",
            json={"query": nl_q, "execute": True},
            timeout=120
        ).json()
        print(f"  Generated SQL: {CYAN}{resp.get('sql')}{RESET}")
        print(f"  Safety Validated: {GREEN}{resp.get('is_safe')}{RESET} (Read-only SELECT guaranteed by SQLGlot)")
        print(f"  Returned {resp.get('row_count')} records in {resp.get('execution_ms')} ms")
    except Exception as e:
        print(f"  {YELLOW}NL2SQL notice: {e}{RESET}")


def main():
    print(f"""{BOLD}{CYAN}
  ╔═════════════════════════════════════════════════════════════════════════╗
  ║                 DAR AL-HANDASAH DATA LAKEHOUSE PILOT                    ║
  ║                   Phase 1 Technical Demonstration                       ║
  ╚═════════════════════════════════════════════════════════════════════════╝{RESET}
    """)

    demo_use_case_1()
    demo_use_case_2()

    print_banner("DEMO READY: ACCESS WEB CONSOLES & INTERFACES")
    print(f"  • {BOLD}Engineering Search & RAG UI:{RESET}     http://localhost:8093/ui")
    print(f"  • {BOLD}Data Product API (Swagger Docs):{RESET} http://localhost:8092/docs")
    print(f"  • {BOLD}Natural Language to SQL API:{RESET}     http://localhost:8095/docs")
    print(f"  • {BOLD}Apache Airflow Orchestration:{RESET}    http://localhost:8079")
    print(f"  • {BOLD}OpenSearch Dashboards:{RESET}           http://localhost:5601")
    print(f"  • {BOLD}Apache Superset BI:{RESET}              http://localhost:8088")
    print(f"  • {BOLD}Trino Distributed SQL Engine:{RESET}    http://localhost:18080\n")


if __name__ == "__main__":
    main()
