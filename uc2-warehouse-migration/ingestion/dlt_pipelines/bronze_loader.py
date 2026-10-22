"""
ingestion/dlt_pipelines/bronze_loader.py
Core Bronze loading logic shared by full-load and incremental DAGs.

Design constraints:
- Bronze tables are APPEND-ONLY Iceberg tables.
- Every row has: _ingested_at, _source_system, _batch_id, _op (I/U/D), _source_hash.
- No direct psycopg2-to-Iceberg inserts; all writes go through Trino.
- Watermarks are stored in postgres_meta.uc2_watermarks (durable across resets).
- Schema is inferred per entity, then hardened per source spec.

Supported sources: d365, sharepoint, postgres
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any, Generator, Iterable

import psycopg2
import requests
import trino

# ---------------------------------------------------------------------------
# Configuration (from environment — injected by Airflow task)
# ---------------------------------------------------------------------------
TRINO_HOST    = os.environ.get("TRINO_HOST", "dar-trino")
TRINO_PORT    = int(os.environ.get("TRINO_INTERNAL_PORT", "8080"))
TRINO_USER    = "airflow"
TRINO_CATALOG = "iceberg"
TRINO_SCHEMA  = "bronze"

PG_META_HOST  = os.environ.get("PG_META_HOST", "dar-postgres-meta")
PG_META_PORT  = int(os.environ.get("PG_META_PORT", "5432"))
PG_META_DB    = os.environ.get("PG_META_DB", "lakehouse_meta")
PG_META_USER  = os.environ.get("PG_META_USER", "lakehouse")
PG_META_PASS  = os.environ.get("PG_META_PASSWORD", "CHANGE_ME_PG_META")

PG_DW_HOST    = os.environ.get("PG_DW_HOST", "dar-postgres-dw")
PG_DW_PORT    = int(os.environ.get("PG_DW_INTERNAL_PORT", "5432"))
PG_DW_DB      = os.environ.get("PG_DW_DB", "DAR_DW")
PG_DW_USER    = os.environ.get("PG_DW_USER", "dar_dw_reader")
PG_DW_PASS    = os.environ.get("PG_DW_PASSWORD", "CHANGE_ME_DW")

D365_BASE_URL = os.environ.get("D365_MOCK_URL", "http://dar-d365-mock:8000/data")
SP_BASE_URL   = os.environ.get("SHAREPOINT_MOCK_URL", "http://dar-sharepoint-mock:8000")

# Bronze audit columns (always appended)
AUDIT_COLS = ["_ingested_at", "_source_system", "_batch_id", "_op", "_source_hash"]

# ---------------------------------------------------------------------------
# Watermark management (postgres_meta)
# ---------------------------------------------------------------------------
def _meta_conn():
    return psycopg2.connect(
        host=PG_META_HOST, port=PG_META_PORT,
        user=PG_META_USER, password=PG_META_PASS,
        database=PG_META_DB,
    )


def ensure_watermark_table() -> None:
    """Create uc2_watermarks table if absent."""
    try:
        with _meta_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS uc2_watermarks (
                        source_system  VARCHAR(50)  NOT NULL,
                        entity_name    VARCHAR(100) NOT NULL,
                        watermark      VARCHAR(100) NOT NULL DEFAULT '1900-01-01T00:00:00',
                        updated_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (source_system, entity_name)
                    )
                """)
            conn.commit()
    except psycopg2.Error as e:
        if "already exists" not in str(e):
            raise


def get_watermark(source: str, entity: str) -> str:
    ensure_watermark_table()
    with _meta_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT watermark FROM uc2_watermarks WHERE source_system=%s AND entity_name=%s",
                (source, entity),
            )
            row = cur.fetchone()
            return row[0] if row else "1900-01-01T00:00:00"


def set_watermark(source: str, entity: str, value: str) -> None:
    ensure_watermark_table()
    with _meta_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO uc2_watermarks (source_system, entity_name, watermark, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (source_system, entity_name) DO UPDATE
                    SET watermark   = EXCLUDED.watermark,
                        updated_at  = CURRENT_TIMESTAMP
            """, (source, entity, value))
        conn.commit()


def reset_watermarks(source: str) -> None:
    """Reset all watermarks for a source (called by full_load)."""
    ensure_watermark_table()
    with _meta_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM uc2_watermarks WHERE source_system = %s",
                (source,),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Source row hash
# ---------------------------------------------------------------------------
def compute_hash(row: dict) -> str:
    """MD5 of sorted key=value pairs, hex-encoded."""
    parts = "|".join(f"{k}={v}" for k, v in sorted(row.items()))
    return hashlib.md5(parts.encode()).hexdigest()


# ---------------------------------------------------------------------------
# D365 OData source
# ---------------------------------------------------------------------------
D365_ENTITIES = [
    "Projects",
    "WBSElements",
    "BudgetLines",
    "LedgerJournalLines",
    "Vendors",
]


def fetch_d365_entity(entity: str, modified_since: str | None) -> Generator[dict, None, None]:
    """
    OData pagination. Returns individual rows.
    Filters on ModifiedAt >= modified_since when provided.
    """
    url = f"{D365_BASE_URL}/{entity}?$top=500"
    if modified_since and modified_since > "1900-01-01T00:00:00":
        url += f"&$filter=ModifiedAt ge '{modified_since}'"
    while url:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise RuntimeError(f"D365 fetch {entity}: {exc}") from exc
        for item in body.get("value", []):
            yield item
        url = body.get("@odata.nextLink")


# ---------------------------------------------------------------------------
# SharePoint Graph source
# ---------------------------------------------------------------------------
SP_ENTITIES = {
    "DriveItems":    "drive",
    "StatusUpdates": "list",
    "RiskRegister":  "list",
    "ChangeRequests":"list",
}


def fetch_sp_drive_items(delta_token: str | None) -> Generator[dict, None, None]:
    if delta_token and delta_token > "1900-01-01T00:00:00":
        url = f"{SP_BASE_URL}/sites/projects/drive/root/delta?$deltatoken={delta_token}"
    else:
        url = f"{SP_BASE_URL}/sites/projects/drive/root/delta"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        raise RuntimeError(f"SP drive delta: {exc}") from exc
    for item in body.get("value", []):
        yield item
    # Store the new deltaLink token in the watermark after caller finishes


def fetch_sp_list(list_name: str, modified_since: str | None) -> Generator[dict, None, None]:
    url = f"{SP_BASE_URL}/sites/projects/lists/{list_name}/items?$top=200"
    if modified_since and modified_since > "1900-01-01T00:00:00":
        url += f"&$filter=lastModifiedDateTime ge '{modified_since}'"
    while url:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise RuntimeError(f"SP list {list_name}: {exc}") from exc
        for item in body.get("value", []):
            yield item
        url = body.get("@odata.nextLink")


# ---------------------------------------------------------------------------
# Postgres DW source
# ---------------------------------------------------------------------------
DW_TABLES = [
    "dim_calendar",
    "dim_project",
    "dim_wbs",
    "dim_employee",
    "dim_cost_code",
    "fact_budget",
    "fact_timesheet",
    "fact_cost_actuals",
    "fact_evm_snapshot",
]

# Tables without a modified_at column (static dims — always full load).
# To prevent duplicating unchanged rows in the append-only Bronze layer on every incremental run,
# we explicitly skip fetching them during incremental loads if they already have an existing watermark.
# Limitation: Retroactive changes to these tables require a full load (documented in KNOWN_GAPS.md).
STATIC_TABLES = {"dim_calendar"}


def fetch_pg_table(table: str, modified_since: str | None) -> Generator[dict, None, None]:
    """
    Read one warehouse table. Uses modified_at watermark for incrementals.
    Static tables are always fully fetched.
    """
    conn = psycopg2.connect(
        host=PG_DW_HOST, port=PG_DW_PORT,
        user=PG_DW_USER, password=PG_DW_PASS,
        database=PG_DW_DB,
    )
    cur = conn.cursor()
    if table in STATIC_TABLES or not modified_since or modified_since <= "1900-01-01T00:00:00":
        query = f"SELECT * FROM warehouse.{table}"
    else:
        query = (
            f"SELECT * FROM warehouse.{table} "
            f"WHERE modified_at >= '{modified_since}'"
        )
    cur.execute(query)
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        yield dict(zip(cols, row))
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Trino Bronze writer
# ---------------------------------------------------------------------------
def _trino_conn():
    return trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        catalog=TRINO_CATALOG,
        schema=TRINO_SCHEMA,
    )


def _trino_type(val: Any) -> str:
    """Map a Python sample value to a Trino column type."""
    if isinstance(val, bool):
        return "BOOLEAN"
    if isinstance(val, int):
        return "BIGINT"
    if isinstance(val, float):
        return "DOUBLE"
    return "VARCHAR"


def _esc(v: Any) -> str:
    """Escape a value for inline Trino VALUES."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        v_str = "true" if v else "false"
        return "'" + v_str + "'"
    return "'" + str(v).replace("'", "''") + "'"


def ensure_bronze_table(cur, table_name: str, sample_row: dict, source_col_types: dict) -> None:
    """
    CREATE TABLE IF NOT EXISTS iceberg.bronze.<table_name>
    with source columns + audit columns.
    All source columns are VARCHAR to stay source-faithful (Bronze = raw).
    Audit columns have their true types.
    """
    col_defs = []
    for col in sample_row.keys():
        col_defs.append(f'"{col}" VARCHAR')
    col_defs += [
        '"_ingested_at" TIMESTAMP(6) WITH TIME ZONE',
        '"_source_system" VARCHAR',
        '"_batch_id" VARCHAR',
        '"_op" VARCHAR',           # I / U / D
        '"_source_hash" VARCHAR',
    ]
    ddl = (
        f"CREATE TABLE IF NOT EXISTS {TRINO_CATALOG}.{TRINO_SCHEMA}.{table_name} ("
        + ", ".join(col_defs)
        + ") WITH (format = 'PARQUET',"
        + " partitioning = ARRAY['\"_source_system\"'])"
    )
    cur.execute(ddl)


def load_rows_to_bronze(
    rows: Iterable[dict],
    table_name: str,
    source_system: str,
    batch_id: str,
    ingested_at: datetime,
    op_resolver=None,
) -> int:
    """
    Append rows to iceberg.bronze.<table_name> in batches.
    """
    conn = _trino_conn()
    cur  = conn.cursor()

    ingested_ts = ingested_at.strftime("%Y-%m-%d %H:%M:%S.000 UTC")
    n_appended = 0
    table_created = False
    source_col_names: list[str] = []

    batch_vals = []

    def execute_batch():
        nonlocal n_appended
        if not batch_vals:
            return
        all_cols = [f'"{c}"' for c in source_col_names] + \
                   ['"_ingested_at"', '"_source_system"', '"_batch_id"', '"_op"', '"_source_hash"']
        insert = (
            f"INSERT INTO {TRINO_CATALOG}.{TRINO_SCHEMA}.{table_name} "
            f"({', '.join(all_cols)}) VALUES " + ", ".join(f"({', '.join(v)})" for v in batch_vals)
        )
        cur.execute(insert)
        n_appended += len(batch_vals)
        batch_vals.clear()

    for row in rows:
        src = {k: v for k, v in row.items() if k not in ("_op",)}

        if not table_created:
            ensure_bronze_table(cur, table_name, src, {})
            source_col_names = list(src.keys())
            table_created = True
        else:
            src = {k: src.get(k) for k in source_col_names}

        if op_resolver:
            op = op_resolver(row)
        elif "is_deleted" in row and row["is_deleted"]:
            op = "D"
        else:
            op = row.get("_op", "I")

        src_hash = compute_hash(src)
        vals = [_esc(src[c]) for c in source_col_names]
        vals += [
            f"TIMESTAMP '{ingested_ts}'",
            f"'{source_system}'",
            f"'{batch_id}'",
            f"'{op}'",
            f"'{src_hash}'",
        ]
        batch_vals.append(vals)

        if len(batch_vals) >= 500:
            execute_batch()

    execute_batch()
    conn.close()
    return n_appended


# ---------------------------------------------------------------------------
# High-level load functions called from DAGs
# ---------------------------------------------------------------------------

def full_load_d365(batch_id: str, ingested_at: datetime) -> dict[str, int]:
    """Full load: reset watermarks then load all D365 entities."""
    reset_watermarks("d365")
    counts: dict[str, int] = {}
    for entity in D365_ENTITIES:
        table_name = f"d365_{entity.lower()}"
        rows = fetch_d365_entity(entity, modified_since=None)
        n = load_rows_to_bronze(rows, table_name, "d365", batch_id, ingested_at)
        set_watermark("d365", entity, ingested_at.isoformat())
        counts[table_name] = n
        print(f"  d365.{entity} -> bronze.{table_name}: {n} rows")
    return counts


def incremental_load_d365(batch_id: str, ingested_at: datetime) -> dict[str, int]:
    """Incremental: load only rows modified after watermark."""
    counts: dict[str, int] = {}
    for entity in D365_ENTITIES:
        wm = get_watermark("d365", entity)
        table_name = f"d365_{entity.lower()}"
        rows = fetch_d365_entity(entity, modified_since=wm)
        n = load_rows_to_bronze(rows, table_name, "d365", batch_id, ingested_at)
        if n > 0:
            set_watermark("d365", entity, ingested_at.isoformat())
        counts[table_name] = n
        print(f"  d365.{entity} (since {wm}) -> {n} rows")
    return counts


def full_load_sharepoint(batch_id: str, ingested_at: datetime) -> dict[str, int]:
    reset_watermarks("sharepoint")
    counts: dict[str, int] = {}
    # Drive items
    rows = fetch_sp_drive_items(delta_token=None)
    n = load_rows_to_bronze(rows, "sp_driveitems", "sharepoint", batch_id, ingested_at)
    set_watermark("sharepoint", "DriveItems", ingested_at.isoformat())
    counts["sp_driveitems"] = n
    print(f"  sp.DriveItems -> bronze.sp_driveitems: {n} rows")
    # List items
    for list_name in ["StatusUpdates", "RiskRegister", "ChangeRequests"]:
        table_name = f"sp_{list_name.lower()}"
        rows = fetch_sp_list(list_name, modified_since=None)
        n = load_rows_to_bronze(rows, table_name, "sharepoint", batch_id, ingested_at)
        set_watermark("sharepoint", list_name, ingested_at.isoformat())
        counts[table_name] = n
        print(f"  sp.{list_name} -> bronze.{table_name}: {n} rows")
    return counts


def incremental_load_sharepoint(batch_id: str, ingested_at: datetime) -> dict[str, int]:
    counts: dict[str, int] = {}
    wm_drive = get_watermark("sharepoint", "DriveItems")
    rows = fetch_sp_drive_items(delta_token=wm_drive)
    n = load_rows_to_bronze(rows, "sp_driveitems", "sharepoint", batch_id, ingested_at)
    if n > 0:
        set_watermark("sharepoint", "DriveItems", ingested_at.isoformat())
    counts["sp_driveitems"] = n
    print(f"  sp.DriveItems (since {wm_drive}) -> {n} rows")

    for list_name in ["StatusUpdates", "RiskRegister", "ChangeRequests"]:
        wm = get_watermark("sharepoint", list_name)
        table_name = f"sp_{list_name.lower()}"
        rows = fetch_sp_list(list_name, modified_since=wm)
        n = load_rows_to_bronze(rows, table_name, "sharepoint", batch_id, ingested_at)
        if n > 0:
            set_watermark("sharepoint", list_name, ingested_at.isoformat())
        counts[table_name] = n
        print(f"  sp.{list_name} (since {wm}) -> {n} rows")
    return counts


def full_load_postgres(batch_id: str, ingested_at: datetime) -> dict[str, int]:
    reset_watermarks("postgres")
    counts: dict[str, int] = {}
    for table in DW_TABLES:
        table_name = f"pg_{table}"
        rows = fetch_pg_table(table, modified_since=None)
        n = load_rows_to_bronze(rows, table_name, "postgres", batch_id, ingested_at)
        set_watermark("postgres", table, ingested_at.isoformat())
        counts[table_name] = n
        print(f"  pg.warehouse.{table} -> bronze.{table_name}: {n} rows")
    return counts


def incremental_load_postgres(batch_id: str, ingested_at: datetime) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in DW_TABLES:
        wm = get_watermark("postgres", table)
        if table in STATIC_TABLES and wm and wm > "1900-01-01T00:00:00":
            counts[f"pg_{table}"] = 0
            continue
        table_name = f"pg_{table}"
        rows = fetch_pg_table(table, modified_since=wm)
        n = load_rows_to_bronze(rows, table_name, "postgres", batch_id, ingested_at)
        if n > 0:
            set_watermark("postgres", table, ingested_at.isoformat())
        counts[table_name] = n
        print(f"  pg.{table} (since {wm}) -> {n} rows")
    return counts
