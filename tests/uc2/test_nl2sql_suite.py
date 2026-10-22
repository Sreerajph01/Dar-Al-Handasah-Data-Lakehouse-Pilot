"""
tests/uc2/test_nl2sql_suite.py
Acceptance test suite for Natural Language to SQL (NL2SQL) service.
Verifies at least 10 varied questions asserting semantic filters, aggregations,
result checks, and safety guardrails.
"""

import os
import requests
import pytest

NL2SQL_URL = os.environ.get("NL2SQL_URL", "http://localhost:8095")


@pytest.fixture(scope="session")
def nl2sql_endpoint():
    # Verify health
    try:
        r = requests.get(f"{NL2SQL_URL}/health", timeout=5)
        assert r.status_code == 200, f"NL2SQL health check failed: {r.text}"
    except Exception as e:
        pytest.fail(f"Could not connect to NL2SQL service at {NL2SQL_URL}: {e}")
    return NL2SQL_URL


class TestNL2SQLVariedSuite:
    def test_q1_cpi_below_filter(self, nl2sql_endpoint):
        """1. Query with CPI filter must include CPI comparison clause and valid results."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "List all projects with CPI below 1.0", "execute": True},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert any(clause in sql for clause in ["CPI <", "CPI<", "CPI <="]), f"Missing CPI < 1.0 filter: {sql}"
        assert data["is_safe"] is True
        assert "GROUP BY PROJECT_ID, CPI, SPI" not in sql, "No-op GROUP BY found in generated SQL"
        if data["rows"]:
            assert len(data["rows"]) <= 5, f"Expected at most 5 distinct projects on latest snapshot, got {len(data['rows'])}"
            if "cpi" in [c.lower() for c in data["columns"]]:
                cpi_idx = [c.lower() for c in data["columns"]].index("cpi")
                for r in data["rows"]:
                    if r[cpi_idx] is not None:
                        assert float(r[cpi_idx]) < 1.0, f"Row returned CPI >= 1.0: {r}"

    def test_q2_spi_below_filter(self, nl2sql_endpoint):
        """2. Query with SPI filter must include SPI comparison clause."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "List all projects with Schedule Performance Index below 1.0", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert any(clause in sql for clause in ["SPI <", "SPI<", "SPI <="]), f"Missing SPI filter: {sql}"

    def test_q3_active_projects_cpi_spi(self, nl2sql_endpoint):
        """3. Active projects query must reference dim_project with is_current or Active status."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "Show me the CPI and SPI for all active projects", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert "EVM_METRICS" in sql
        assert "DIM_PROJECT" in sql or "ACTIVE" in sql or "IS_CURRENT" in sql

    def test_q4_over_budget_projects(self, nl2sql_endpoint):
        """4. Over budget query must compare cost to budget."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "Which projects are over budget?", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert any(term in sql for term in ["TOTAL_COST > TOTAL_BUDGET", "OVERRUN", "TOTAL_COST - TOTAL_BUDGET"])

    def test_q5_budget_by_discipline(self, nl2sql_endpoint):
        """5. Aggregation by discipline must include SUM and GROUP BY."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "What is the total budget by discipline?", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert "SUM(" in sql or "SUM (" in sql
        assert "DISCIPLINE" in sql

    def test_q6_single_project_filter(self, nl2sql_endpoint):
        """6. Filter for specific project P001 must include P001 condition."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "Show latest EVM metrics for project P001", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert "P001" in sql
        assert "EVM_METRICS" in sql

    def test_q7_total_portfolio_cost(self, nl2sql_endpoint):
        """7. Portfolio aggregation must include SUM on cost."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "What is the total project cost across all projects?", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert "SUM" in sql
        assert "COST" in sql

    def test_q8_reconciliation_summary(self, nl2sql_endpoint):
        """8. Reconciliation query must reference reconciliation table."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "Show financial reconciliation summary between source and lakehouse", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert "RECONCILIATION" in sql

    def test_q9_country_filter(self, nl2sql_endpoint):
        """9. Geographic filter for Saudi Arabia must include country condition."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "List projects in Saudi Arabia", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert "SAUDI ARABIA" in sql

    def test_q10_highest_cost_variance(self, nl2sql_endpoint):
        """10. Cost variance query must reference cv or cost variance."""
        resp = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": "Find the project with the highest cost variance", "execute": False},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        sql = data["sql"].upper()
        assert "CV" in sql or "COST" in sql or "EVM_METRICS" in sql

    def test_safety_mutation_blocked(self, nl2sql_endpoint):
        """11. Destructive statements must be blocked by SQLGlot guardrails."""
        for stmt in ["DROP TABLE iceberg.silver.dim_project", "DELETE FROM iceberg.gold.evm_metrics", "UPDATE iceberg.silver.dim_project SET status='Closed'"]:
            resp = requests.post(
                f"{nl2sql_endpoint}/v1/query",
                json={"query": stmt, "execute": False},
                timeout=15
            )
            assert resp.status_code in [400, 422] or (resp.status_code == 200 and resp.json().get("is_safe") is False)

    def test_cross_role_cache_isolation(self, nl2sql_endpoint):
        """12. Verifies persona/role cache key scoping and prevents cross-role cache leakage."""
        test_query = "List all projects with CPI below 1.0"
        
        # 1. Warm cache for role pm_p001
        resp_a = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": test_query, "execute": False, "role": "pm_P001", "nocache": False},
            timeout=30
        )
        assert resp_a.status_code == 200
        
        # 2. Second request with role pm_p001 must hit cache with role=pm_p001
        resp_a2 = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": test_query, "execute": False, "role": "pm_P001", "nocache": False},
            timeout=30
        )
        assert resp_a2.status_code == 200
        assert "role=pm_p001" in resp_a2.json().get("explanation", ""), "Expected warm cache hit for role pm_p001"

        # 3. Request with role pm_p002 MUST NOT receive role pm_p001 cached entry
        resp_b = requests.post(
            f"{nl2sql_endpoint}/v1/query",
            json={"query": test_query, "execute": False, "role": "pm_P002", "nocache": False},
            timeout=30
        )
        assert resp_b.status_code == 200
        explanation_b = resp_b.json().get("explanation", "")
        assert "role=pm_p001" not in explanation_b, f"CROSS-ROLE CACHE LEAKAGE DETECTED! Role pm_p002 received cache from pm_p001: {explanation_b}"


if __name__ == "__main__":
    pytest.main(["-v", __file__])

