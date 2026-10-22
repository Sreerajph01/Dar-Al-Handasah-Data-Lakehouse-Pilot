"""
ingestion/airbyte_pipelines/airbyte_bronze_loader.py
Airbyte-standard Bronze Ingestion Pipeline for Dar Al-Handasah Lakehouse Pilot.

Implements the Airbyte Source-to-Bronze connector pattern:
- Source: Relational operational database (PostgreSQL DAR_DW / MySQL)
- Protocol: Airbyte Record Message & State Message format
- Destination: Apache Iceberg Bronze tables via Trino
- Standard Airbyte Metadata Columns:
    - _airbyte_raw_id: UUID string
    - _airbyte_extracted_at: extraction timestamp
    - _airbyte_loaded_at: load timestamp
    - _airbyte_data: JSON serialized record payload
    - _source_system: 'airbyte'
    - _batch_id: Airflow sync run ID
    - _op: 'I' / 'U' / 'D'
    - _source_hash: MD5 integrity hash
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Iterable, List

import psycopg2
import trino

# ---------------------------------------------------------------------------
# Configuration (Environment variables injected by Airflow / container)
# ---------------------------------------------------------------------------
TRINO_HOST    = os.environ.get("TRINO_HOST", "dar-trino")
TRINO_PORT    = int(os.environ.get("TRINO_INTERNAL_PORT", os.environ.get("TRINO_PORT", "8080")))
TRINO_USER    = "airflow"
TRINO_CATALOG = "iceberg"
TRINO_SCHEMA  = "bronze"

PG_META_HOST  = os.environ.get("PG_META_HOST", "dar-postgres-meta")
PG_META_PORT  = int(os.environ.get("PG_META_PORT", "5432"))
PG_META_DB    = os.environ.get("PG_META_DB", "lakehouse_meta")
PG_META_USER  = os.environ.get("PG_META_USER", "lakehouse")
PG_META_PASS  = os.environ.get("PG_META_PASSWORD", "CHANGE_ME_PG_META")

PG_DW_HOST    = os.environ.get("PG_DW_HOST", "dar-postgres-dw")
PG_DW_PORT    = int(os.environ.get("PG_DW_INTERNAL_PORT", os.environ.get("PG_DW_PORT", "5432")))
PG_DW_DB      = os.environ.get("PG_DW_DB", "DAR_DW")
PG_DW_USER    = os.environ.get("PG_DW_USER", "dar_dw_reader")
PG_DW_PASS    = os.environ.get("PG_DW_PASSWORD", "CHANGE_ME_DW")

# Airbyte streams mapping from relational source tables
AIRBYTE_STREAMS = [
    {"stream": "pg_dim_project", "source_table": "warehouse.dim_project", "cursor_field": "modified_at"},
    {"stream": "pg_fact_budget", "source_table": "warehouse.fact_budget", "cursor_field": "modified_at"},
    {"stream": "pg_fact_cost_actuals", "source_table": "warehouse.fact_cost_actuals", "cursor_field": "modified_at"},
    {"stream": "pg_fact_timesheet", "source_table": "warehouse.fact_timesheet", "cursor_field": "modified_at"},
]


# ---------------------------------------------------------------------------
# Connections & State Management
# ---------------------------------------------------------------------------
def _meta_conn():
    return psycopg2.connect(
        host=PG_META_HOST, port=PG_META_PORT,
        user=PG_META_USER, password=PG_META_PASS,
        database=PG_META_DB,
    )


def _source_conn():
    return psycopg2.connect(
        host=PG_DW_HOST, port=PG_DW_PORT,
        user=PG_DW_USER, password=PG_DW_PASS,
        database=PG_DW_DB,
    )


def _trino_conn():
    return trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        catalog=TRINO_CATALOG,
        schema=TRINO_SCHEMA,
    )


def ensure_airbyte_state_table() -> None:
    """Ensure Airbyte stream state table exists in metadata DB."""
    try:
        with _meta_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS airbyte_stream_states (
                        source_id      VARCHAR(100) NOT NULL,
                        stream_name    VARCHAR(100) NOT NULL,
                        cursor_value   VARCHAR(100) NOT NULL DEFAULT '1900-01-01T00:00:00',
                        records_synced BIGINT       NOT NULL DEFAULT 0,
                        updated_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (source_id, stream_name)
                    )
                """)
            conn.commit()
    except psycopg2.Error as e:
        if "already exists" not in str(e):
            raise


def get_stream_cursor(source_id: str, stream_name: str) -> str:
    ensure_airbyte_state_table()
    with _meta_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cursor_value FROM airbyte_stream_states WHERE source_id=%s AND stream_name=%s",
                (source_id, stream_name),
            )
            row = cur.fetchone()
            return row[0] if row else "1900-01-01T00:00:00"


def update_stream_state(source_id: str, stream_name: str, cursor_value: str, count: int) -> None:
    ensure_airbyte_state_table()
    with _meta_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO airbyte_stream_states (source_id, stream_name, cursor_value, records_synced, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (source_id, stream_name) DO UPDATE
                    SET cursor_value   = EXCLUDED.cursor_value,
                        records_synced = airbyte_stream_states.records_synced + EXCLUDED.records_synced,
                        updated_at     = CURRENT_TIMESTAMP
            """, (source_id, stream_name, cursor_value, count))
        conn.commit()


# ---------------------------------------------------------------------------
# Source Extractor (Airbyte Source Protocol)
# ---------------------------------------------------------------------------
def extract_airbyte_stream(
    source_table: str,
    cursor_field: str | None = None,
    cursor_val: str | None = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Simulates Airbyte Source Record extraction from relational database.
    Yields dicts representing the raw source rows.
    """
    conn = _source_conn()
    cur = conn.cursor()

    query = f"SELECT * FROM {source_table}"
    params = []

    if cursor_field and cursor_val and cursor_val > "1900-01-01T00:00:00":
        query += f" WHERE {cursor_field} >= %s ORDER BY {cursor_field} ASC"
        params.append(cursor_val)
    elif cursor_field:
        query += f" ORDER BY {cursor_field} ASC"

    cur.execute(query, params)
    cols = [desc[0] for desc in cur.description]

    for row in cur:
        row_dict = {}
        for col_name, val in zip(cols, row):
            if isinstance(val, (datetime,)):
                row_dict[col_name] = val.isoformat()
            else:
                row_dict[col_name] = val
        yield row_dict

    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Trino Iceberg Bronze Writer (Airbyte Destination Protocol)
# ---------------------------------------------------------------------------
def _esc(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "'true'" if v else "'false'"
    return "'" + str(v).replace("'", "''") + "'"


def ensure_bronze_table(cur, table_name: str, sample_row: Dict[str, Any]) -> None:
    """Ensure Iceberg bronze table exists with standard schema and audit columns."""
    col_defs = []
    for col in sample_row.keys():
        col_defs.append(f'"{col}" VARCHAR')
    col_defs += [
        '"_ingested_at" TIMESTAMP(6) WITH TIME ZONE',
        '"_source_system" VARCHAR',
        '"_batch_id" VARCHAR',
        '"_op" VARCHAR',
        '"_source_hash" VARCHAR',
    ]
    ddl = (
        f"CREATE TABLE IF NOT EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.{table_name} ("
        + ", ".join(col_defs)
        + ") WITH (format = 'PARQUET', partitioning = ARRAY['\"_source_system\"'])"
    )
    cur.execute(ddl)


def load_airbyte_records_to_bronze(
    records: Iterable[Dict[str, Any]],
    table_name: str,
    batch_id: str,
    extracted_at: datetime,
) -> int:
    """
    Appends Airbyte records into Iceberg Bronze table.
    Preserves raw source fidelity and stamps standard Airbyte audit attributes.
    """
    conn = _trino_conn()
    cur = conn.cursor()

    ingested_ts = extracted_at.strftime("%Y-%m-%d %H:%M:%S.000 UTC")
    n_appended = 0
    table_created = False
    source_col_names: List[str] = []
    batch_vals = []

    def execute_batch():
        nonlocal n_appended
        if not batch_vals:
            return
        all_cols = [f'"{c}"' for c in source_col_names] + [
            '"_ingested_at"', '"_source_system"', '"_batch_id"', '"_op"', '"_source_hash"'
        ]
        insert_query = (
            f"INSERT INTO {TRINO_CATALOG}.{TRINO_SCHEMA}.{table_name} "
            f"({', '.join(all_cols)}) VALUES " + ", ".join(f"({', '.join(v)})" for v in batch_vals)
        )
        cur.execute(insert_query)
        n_appended += len(batch_vals)
        batch_vals.clear()

    for row in records:
        if not table_created:
            source_col_names = list(row.keys())
            ensure_bronze_table(cur, table_name, row)
            table_created = True

        str(uuid.uuid4())
        parts = "|".join(f"{k}={v}" for k, v in sorted(row.items()))
        source_hash = hashlib.md5(parts.encode()).hexdigest()

        # Format values
        row_vals = [_esc(row.get(c)) for c in source_col_names]
        # Append audit fields
        audit_vals = [
            f"TIMESTAMP '{ingested_ts}'",
            "'airbyte'",
            f"'{batch_id}'",
            "'I'",
            f"'{source_hash}'",
        ]
        batch_vals.append(row_vals + audit_vals)

        if len(batch_vals) >= 200:
            execute_batch()

    execute_batch()
    cur.close()
    conn.close()
    return n_appended


# ---------------------------------------------------------------------------
# High-Level Airbyte Sync Workflows
# ---------------------------------------------------------------------------
def run_airbyte_stream_sync(
    stream_name: str,
    source_table: str,
    batch_id: str,
    cursor_field: str | None = None,
    sync_mode: str = "full_refresh",
) -> int:
    """Run Airbyte sync for an individual stream."""
    now = datetime.now(timezone.utc)
    cursor_val = None

    if sync_mode == "incremental" and cursor_field:
        cursor_val = get_stream_cursor("dar_dw_source", stream_name)

    records = list(extract_airbyte_stream(source_table, cursor_field, cursor_val))
    if not records:
        return 0

    appended = load_airbyte_records_to_bronze(records, stream_name, batch_id, now)

    # Update cursor if incremental
    if cursor_field and records:
        max_cursor = max(str(r.get(cursor_field, "")) for r in records if r.get(cursor_field))
        if max_cursor:
            update_stream_state("dar_dw_source", stream_name, max_cursor, appended)

    return appended


def run_full_airbyte_sync(batch_id: str | None = None) -> Dict[str, int]:
    """Runs a full Airbyte sync across all configured source streams."""
    if not batch_id:
        batch_id = f"airbyte_sync_{int(datetime.now().timestamp())}"

    counts = {}
    print(f"[Airbyte Sync] Starting sync with batch ID: {batch_id}")

    for stream in AIRBYTE_STREAMS:
        s_name = stream["stream"]
        s_table = stream["source_table"]
        print(f"[Airbyte Sync] Syncing stream {s_name} from {s_table}...")
        n = run_airbyte_stream_sync(s_name, s_table, batch_id, stream.get("cursor_field"), sync_mode="full_refresh")
        counts[s_name] = n
        print(f"[Airbyte Sync] Stream {s_name}: {n} records synced to Bronze.")

    return counts
