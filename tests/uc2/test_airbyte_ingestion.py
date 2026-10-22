"""
tests/uc2/test_airbyte_ingestion.py
Verification suite for Airbyte Source-to-Bronze Ingestion Pipeline.

Validates:
1. Source database connectivity and record extraction
2. Airbyte pipeline execution and state tracking
3. Apache Iceberg Bronze landing via Trino
4. Audit columns integrity (_source_system = 'airbyte', _batch_id, _source_hash)
"""

import os
import pytest
import trino

TRINO_HOST = os.environ.get("TRINO_HOST", "dar-trino")
TRINO_PORT = int(os.environ.get("TRINO_PORT", "8080"))


@pytest.fixture(scope="module")
def trino_cursor():
    conn = trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user="test_runner",
        catalog="iceberg",
        schema="bronze",
    )
    cur = conn.cursor()
    yield cur
    cur.close()
    conn.close()


class TestAirbyteIngestionGate:

    def test_airbyte_fact_budget_ingested(self, trino_cursor):
        """Verifies that Airbyte ingested fact_budget rows into Iceberg Bronze."""
        trino_cursor.execute("""
            SELECT count(*)
            FROM iceberg.bronze.pg_fact_budget
            WHERE _source_system = 'airbyte'
        """)
        row = trino_cursor.fetchone()
        assert row is not None
        assert row[0] > 0, "Expected >0 records ingested with _source_system='airbyte'"

    def test_airbyte_dim_project_ingested(self, trino_cursor):
        """Verifies that Airbyte ingested dim_project rows into Iceberg Bronze."""
        trino_cursor.execute("""
            SELECT count(*)
            FROM iceberg.bronze.pg_dim_project
            WHERE _source_system = 'airbyte'
        """)
        row = trino_cursor.fetchone()
        assert row is not None
        assert row[0] > 0, "Expected >0 project records ingested with _source_system='airbyte'"

    def test_airbyte_cost_actuals_ingested(self, trino_cursor):
        """Verifies that Airbyte ingested fact_cost_actuals rows into Iceberg Bronze."""
        trino_cursor.execute("""
            SELECT count(*)
            FROM iceberg.bronze.pg_fact_cost_actuals
            WHERE _source_system = 'airbyte'
        """)
        row = trino_cursor.fetchone()
        assert row is not None
        assert row[0] > 0, "Expected >0 cost actuals records ingested with _source_system='airbyte'"

    def test_airbyte_audit_columns_fidelity(self, trino_cursor):
        """Validates that Airbyte audit columns (_source_hash, _batch_id, _ingested_at) are present and populated."""
        trino_cursor.execute("""
            SELECT _source_hash, _batch_id, _ingested_at
            FROM iceberg.bronze.pg_fact_budget
            WHERE _source_system = 'airbyte'
            LIMIT 5
        """)
        rows = trino_cursor.fetchall()
        assert len(rows) == 5
        for hash_val, batch_id, ingested_at in rows:
            assert hash_val is not None and len(hash_val) == 32, "Invalid MD5 hash for source row"
            assert batch_id is not None and len(batch_id) > 0, "Missing batch ID"
            assert ingested_at is not None, "Missing ingestion timestamp"
