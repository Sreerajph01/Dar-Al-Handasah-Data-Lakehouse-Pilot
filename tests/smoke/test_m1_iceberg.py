#!/usr/bin/env python3
"""
tests/smoke/test_m1_iceberg.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
M1 gate test: Verify Iceberg table CREATE / INSERT / SELECT / DROP
works end-to-end via Trino → Lakekeeper → SeaweedFS.

This is the primary M1 acceptance test.  A passing run proves:
  1. Trino connects to Lakekeeper REST catalog
  2. Lakekeeper resolves warehouse storage on SeaweedFS S3
  3. Path-style access works for Iceberg metadata and data files
  4. Trino can execute DML (INSERT) and queries on Iceberg tables

Run: python tests/smoke/test_m1_iceberg.py
Requires: pip install trino
"""
import os
import sys
import uuid
import datetime
import trino

TRINO_HOST   = os.environ.get("TRINO_HOST",    "localhost")
TRINO_PORT   = int(os.environ.get("TRINO_PORT", "18080"))
TRINO_USER   = os.environ.get("TRINO_USER",    "admin")
CATALOG      = os.environ.get("TRINO_CATALOG", "iceberg")
SCHEMA       = "bronze"
TABLE        = f"m1_smoke_test_{uuid.uuid4().hex[:8]}"

GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"


def conn():
    return trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        catalog=CATALOG,
        schema=SCHEMA,
    )


def run_sql(cursor, sql: str):
    print(f"  SQL: {sql[:120]}")
    cursor.execute(sql)
    return cursor.fetchall()


def main():
    print(f"\nM1 Iceberg Smoke Test — {TRINO_HOST}:{TRINO_PORT}/{CATALOG}.{SCHEMA}\n")
    passed = []
    failed = []

    try:
        c = conn()
        cur = c.cursor()

        # ── 1. List catalogs ──────────────────────────────────────────────────
        try:
            rows = run_sql(cur, "SHOW CATALOGS")
            catalogs = [r[0] for r in rows]
            assert CATALOG in catalogs, f"'{CATALOG}' not in catalogs: {catalogs}"
            passed.append("Show catalogs")
        except Exception as e:
            failed.append(("Show catalogs", str(e)))

        # ── 2. Create schema (namespace) ──────────────────────────────────────
        try:
            run_sql(cur, f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
            passed.append("Create schema")
        except Exception as e:
            failed.append(("Create schema", str(e)))

        # ── 3. Create Iceberg table ───────────────────────────────────────────
        try:
            run_sql(cur, f"""
                CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{TABLE} (
                    id           BIGINT,
                    project_code VARCHAR(20),
                    description  VARCHAR(255),
                    amount       DECIMAL(15,2),
                    ingested_at  TIMESTAMP(6) WITH TIME ZONE
                )
                WITH (
                    format            = 'PARQUET',
                    partitioning      = ARRAY['project_code'],
                    sorted_by         = ARRAY['id']
                )
            """)
            passed.append("Create Iceberg table (Parquet, partitioned)")
        except Exception as e:
            failed.append(("Create Iceberg table", str(e)))
            # Cannot continue without table
            raise

        # ── 4. Insert rows ────────────────────────────────────────────────────
        try:
            now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000000 UTC")
            run_sql(cur, f"""
                INSERT INTO {CATALOG}.{SCHEMA}.{TABLE}
                    (id, project_code, description, amount, ingested_at)
                VALUES
                    (1, 'METRO-01', 'Phase 1 civil works',  1500000.00, TIMESTAMP '{now}'),
                    (2, 'METRO-01', 'Phase 1 MEP works',    890000.00,  TIMESTAMP '{now}'),
                    (3, 'BRIDGE-02', 'Structural steel',    620000.00,  TIMESTAMP '{now}')
            """)
            passed.append("INSERT 3 rows")
        except Exception as e:
            failed.append(("INSERT rows", str(e)))
            raise

        # ── 5. SELECT and verify count ────────────────────────────────────────
        try:
            rows = run_sql(cur, f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.{TABLE}")
            count = rows[0][0]
            assert count == 3, f"Expected 3 rows, got {count}"
            passed.append(f"SELECT COUNT(*) = {count}")
        except Exception as e:
            failed.append(("SELECT COUNT", str(e)))

        # ── 6. SELECT with predicate (partition pruning) ──────────────────────
        try:
            rows = run_sql(cur, f"""
                SELECT project_code, SUM(amount)
                FROM {CATALOG}.{SCHEMA}.{TABLE}
                WHERE project_code = 'METRO-01'
                GROUP BY project_code
            """)
            assert len(rows) == 1
            assert float(rows[0][1]) == 2390000.00
            passed.append("SELECT with partition filter + aggregation")
        except Exception as e:
            failed.append(("SELECT with predicate", str(e)))

        # ── 7. Snapshot metadata and time travel ─────────────────────────────
        try:
            # 7a. Query snapshots
            rows = run_sql(cur, f"""
                SELECT snapshot_id FROM {CATALOG}.{SCHEMA}."{TABLE}$snapshots"
                ORDER BY committed_at DESC
            """)
            assert len(rows) >= 1, "Expected at least 1 snapshot"
            snapshot_id = rows[0][0]
            passed.append("Query Iceberg snapshots metadata")

            # 7b. Time travel (Version AS OF)
            rows = run_sql(cur, f"""
                SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.{TABLE} FOR VERSION AS OF {snapshot_id}
            """)
            assert rows[0][0] == 3, "Time travel should return 3 rows"
            passed.append("Time travel (FOR VERSION AS OF)")

            # 7c. Time travel (Timestamp AS OF)
            rows = run_sql(cur, f"""
                SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.{TABLE} FOR TIMESTAMP AS OF (CURRENT_TIMESTAMP)
            """)
            assert rows[0][0] == 3, "Time travel by timestamp should return 3 rows"
            passed.append("Time travel (FOR TIMESTAMP AS OF)")

            # 7d. Rollback
            run_sql(cur, f"""
                CALL {CATALOG}.system.rollback_to_snapshot('{SCHEMA}', '{TABLE}', {snapshot_id})
            """)
            passed.append("Rollback to snapshot")

        except Exception as e:
            failed.append(("Snapshot / Time travel tests", str(e)))

        # ── 8. DROP table (cleanup) ───────────────────────────────────────────
        try:
            run_sql(cur, f"DROP TABLE {CATALOG}.{SCHEMA}.{TABLE}")
            passed.append("DROP table (cleanup)")
        except Exception as e:
            failed.append(("DROP table", str(e)))

        cur.close()
        c.close()

    except Exception as e:
        failed.append(("Connection / fatal", str(e)))

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("M1 ICEBERG SMOKE TEST RESULTS")
    print(f"{'='*60}")
    for p in passed:
        print(f"  {GREEN}✅ PASS{RESET}: {p}")
    for name, err in failed:
        print(f"  {RED}❌ FAIL{RESET}: {name} — {err}")

    print(f"\n  Passed: {len(passed)} / {len(passed) + len(failed)}")

    if failed:
        print(f"\n{RED}❌ M1 GATE FAILED — Iceberg/Trino integration not working.{RESET}")
        print("   Check: Lakekeeper, SeaweedFS S3, Trino catalog config.")
        sys.exit(1)
    else:
        print(f"\n{GREEN}✅ M1 GATE PASSED — Iceberg read/write/delete on SeaweedFS works.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
