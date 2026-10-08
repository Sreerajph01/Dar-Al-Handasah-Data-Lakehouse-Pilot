"""
DAG: uc2_full_load
Full load of all UC2 sources into Bronze Iceberg tables.
Resets all watermarks; intended for initial or re-baseline loads.

Sources:
  1. D365 F&O mock  (OData /data/Projects, /data/WBSElements, ...)
  2. SharePoint mock (Graph-style /sites/projects/drive/root/delta, /sites/.../lists/...)
  3. PostgreSQL DAR_DW (warehouse.dim_*, warehouse.fact_*)

Bronze tables (Iceberg, PARQUET, append-only):
  iceberg.bronze.d365_projects
  iceberg.bronze.d365_wbselements
  iceberg.bronze.d365_budgetlines
  iceberg.bronze.d365_ledgerjournallines
  iceberg.bronze.d365_vendors
  iceberg.bronze.sp_driveitems
  iceberg.bronze.sp_statusupdates
  iceberg.bronze.sp_riskregister
  iceberg.bronze.sp_changerequests
  iceberg.bronze.pg_dim_calendar
  iceberg.bronze.pg_dim_project
  iceberg.bronze.pg_dim_wbs
  iceberg.bronze.pg_dim_employee
  iceberg.bronze.pg_dim_cost_code
  iceberg.bronze.pg_fact_budget
  iceberg.bronze.pg_fact_timesheet
  iceberg.bronze.pg_fact_cost_actuals
  iceberg.bronze.pg_fact_evm_snapshot

Note: this DAG does NOT use direct psycopg2-to-Iceberg inserts.
All Bronze writes go through the Trino connector (JDBC-less INSERT).
"""

import sys
import os
from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator

# Resolve ingestion module from DAG directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion", "dlt_pipelines"))

import bronze_loader as bl

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "retries": 1,
}


def task_full_load_d365(**context):
    batch_id = context["dag_run"].run_id
    now = datetime.now(timezone.utc)
    counts = bl.full_load_d365(batch_id, now)
    context["ti"].xcom_push(key="d365_counts", value=counts)
    print(f"D365 full load complete: {counts}")
    return counts


def task_full_load_sharepoint(**context):
    batch_id = context["dag_run"].run_id
    now = datetime.now(timezone.utc)
    counts = bl.full_load_sharepoint(batch_id, now)
    context["ti"].xcom_push(key="sp_counts", value=counts)
    print(f"SharePoint full load complete: {counts}")
    return counts


def task_full_load_postgres(**context):
    batch_id = context["dag_run"].run_id
    now = datetime.now(timezone.utc)
    counts = bl.full_load_postgres(batch_id, now)
    context["ti"].xcom_push(key="pg_counts", value=counts)
    print(f"Postgres full load complete: {counts}")
    return counts


def task_report(**context):
    ti = context["ti"]
    d365 = ti.xcom_pull(key="d365_counts", task_ids="full_load_d365") or {}
    sp   = ti.xcom_pull(key="sp_counts",   task_ids="full_load_sharepoint") or {}
    pg   = ti.xcom_pull(key="pg_counts",   task_ids="full_load_postgres") or {}
    all_counts = {**d365, **sp, **pg}
    total = sum(all_counts.values())
    print("=== uc2_full_load report ===")
    for tbl, n in sorted(all_counts.items()):
        print(f"  {tbl}: {n} rows")
    print(f"Total rows ingested: {total}")
    if total == 0:
        raise ValueError("Full load produced 0 rows — source data may be missing. "
                         "Run 'make seed' first.")


with DAG(
    dag_id="uc2_full_load",
    default_args=DEFAULT_ARGS,
    schedule=None,          # manual trigger only
    catchup=False,
    tags=["uc2", "bronze", "full-load"],
    doc_md=__doc__,
) as dag:

    t_d365 = PythonOperator(
        task_id="full_load_d365",
        python_callable=task_full_load_d365,
    )

    t_sp = PythonOperator(
        task_id="full_load_sharepoint",
        python_callable=task_full_load_sharepoint,
    )

    t_pg = PythonOperator(
        task_id="full_load_postgres",
        python_callable=task_full_load_postgres,
    )

    t_report = PythonOperator(
        task_id="report",
        python_callable=task_report,
        trigger_rule="all_success",
    )

    # Sources load in parallel; report after all succeed
    [t_d365, t_sp, t_pg] >> t_report
