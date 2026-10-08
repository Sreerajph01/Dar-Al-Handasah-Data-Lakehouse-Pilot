"""
DAG: uc2_incremental
Incremental load — appends only rows modified since each entity's watermark.

Watermarks are stored durably in postgres_meta.uc2_watermarks.
Running with no new data appends 0 rows (idempotent).
Soft-deleted rows appear with _op='D' in Bronze.

After simulate-day:
  - D365 Projects: newly inserted + updated rows come through (op I/U)
  - D365 Projects: soft-deleted rows come through (op D)
  - SharePoint DriveItems: delta query returns only changed items
  - Postgres: rows with modified_at > watermark are fetched
"""

import sys
import os
from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion", "dlt_pipelines"))

import bronze_loader as bl

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "retries": 1,
}


def task_incremental_d365(**context):
    batch_id = context["dag_run"].run_id
    now = datetime.now(timezone.utc)
    counts = bl.incremental_load_d365(batch_id, now)
    context["ti"].xcom_push(key="d365_counts", value=counts)
    print(f"D365 incremental: {counts}")
    return counts


def task_incremental_sharepoint(**context):
    batch_id = context["dag_run"].run_id
    now = datetime.now(timezone.utc)
    counts = bl.incremental_load_sharepoint(batch_id, now)
    context["ti"].xcom_push(key="sp_counts", value=counts)
    print(f"SharePoint incremental: {counts}")
    return counts


def task_incremental_postgres(**context):
    batch_id = context["dag_run"].run_id
    now = datetime.now(timezone.utc)
    counts = bl.incremental_load_postgres(batch_id, now)
    context["ti"].xcom_push(key="pg_counts", value=counts)
    print(f"Postgres incremental: {counts}")
    return counts


def task_report(**context):
    ti = context["ti"]
    d365 = ti.xcom_pull(key="d365_counts", task_ids="incremental_d365") or {}
    sp   = ti.xcom_pull(key="sp_counts",   task_ids="incremental_sharepoint") or {}
    pg   = ti.xcom_pull(key="pg_counts",   task_ids="incremental_postgres") or {}
    all_counts = {**d365, **sp, **pg}
    total = sum(all_counts.values())
    print("=== uc2_incremental report ===")
    for tbl, n in sorted(all_counts.items()):
        print(f"  {tbl}: {n} rows appended")
    print(f"Total rows appended this run: {total}")
    # 0 is valid (no changes since last run)
    context["ti"].xcom_push(key="total_appended", value=total)


with DAG(
    dag_id="uc2_incremental",
    default_args=DEFAULT_ARGS,
    schedule=None,
    catchup=False,
    tags=["uc2", "bronze", "incremental"],
    doc_md=__doc__,
) as dag:

    t_d365 = PythonOperator(
        task_id="incremental_d365",
        python_callable=task_incremental_d365,
    )

    t_sp = PythonOperator(
        task_id="incremental_sharepoint",
        python_callable=task_incremental_sharepoint,
    )

    t_pg = PythonOperator(
        task_id="incremental_postgres",
        python_callable=task_incremental_postgres,
    )

    t_report = PythonOperator(
        task_id="report",
        python_callable=task_report,
        trigger_rule="all_success",
    )

    [t_d365, t_sp, t_pg] >> t_report
