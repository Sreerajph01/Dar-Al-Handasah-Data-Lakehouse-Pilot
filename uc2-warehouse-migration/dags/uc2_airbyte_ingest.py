"""
DAG: uc2_airbyte_ingest
Orchestrates Airbyte-based ingestion from enterprise relational source into Iceberg Bronze tables.

Flow:
  Source DB (MySQL / PostgreSQL DAR_DW) ──► Airbyte Connector ──► Bronze Iceberg Tables
                                                                        │
                                                                        ▼
                                                           Trigger Silver / Gold dbt transform
"""

import sys
import os
from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

# Resolve Airbyte ingestion module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion", "airbyte_pipelines"))

try:
    import airbyte_bronze_loader as abl
except ImportError:
    # Fallback if mounted under /opt/airflow/dags/ingestion
    sys.path.insert(0, "/opt/airflow/dags/ingestion/airbyte_pipelines")
    import airbyte_bronze_loader as abl

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "retries": 1,
}


def task_check_connectivity(**context):
    """Verifies relational source and Trino Iceberg connectivity."""
    conn = abl._source_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    conn.close()

    t_conn = abl._trino_conn()
    cur = t_conn.cursor()
    cur.execute("SELECT 1")
    cur.close()
    t_conn.close()
    print("Airbyte source and Bronze destination connectivity verified.")
    return True


def task_sync_dim_project(**context):
    batch_id = context["dag_run"].run_id
    n = abl.run_airbyte_stream_sync(
        stream_name="pg_dim_project",
        source_table="warehouse.dim_project",
        batch_id=batch_id,
        cursor_field="modified_at",
        sync_mode="full_refresh",
    )
    context["ti"].xcom_push(key="dim_project_count", value=n)
    print(f"Airbyte synced {n} records for pg_dim_project into Bronze.")
    return n


def task_sync_fact_budget(**context):
    batch_id = context["dag_run"].run_id
    n = abl.run_airbyte_stream_sync(
        stream_name="pg_fact_budget",
        source_table="warehouse.fact_budget",
        batch_id=batch_id,
        cursor_field="modified_at",
        sync_mode="full_refresh",
    )
    context["ti"].xcom_push(key="fact_budget_count", value=n)
    print(f"Airbyte synced {n} records for pg_fact_budget into Bronze.")
    return n


def task_sync_fact_cost_actuals(**context):
    batch_id = context["dag_run"].run_id
    n = abl.run_airbyte_stream_sync(
        stream_name="pg_fact_cost_actuals",
        source_table="warehouse.fact_cost_actuals",
        batch_id=batch_id,
        cursor_field="modified_at",
        sync_mode="full_refresh",
    )
    context["ti"].xcom_push(key="cost_actuals_count", value=n)
    print(f"Airbyte synced {n} records for pg_fact_cost_actuals into Bronze.")
    return n


def task_verify_bronze(**context):
    conn = abl._trino_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM iceberg.bronze.pg_fact_budget WHERE _source_system = 'airbyte'")
    row = cur.fetchone()
    count = row[0] if row else 0
    cur.close()
    conn.close()
    print(f"Verified Iceberg Bronze table has {count} Airbyte-ingested rows.")
    return count


with DAG(
    dag_id="uc2_airbyte_ingest",
    default_args=DEFAULT_ARGS,
    description="Airbyte Source-to-Bronze Ingestion Pipeline",
    schedule_interval=None,
    catchup=False,
    tags=["uc2", "ingestion", "airbyte", "bronze"],
) as dag:

    check_conn = PythonOperator(
        task_id="airbyte_check_source_connectivity",
        python_callable=task_check_connectivity,
    )

    sync_projects = PythonOperator(
        task_id="airbyte_sync_dim_project",
        python_callable=task_sync_dim_project,
    )

    sync_budget = PythonOperator(
        task_id="airbyte_sync_fact_budget",
        python_callable=task_sync_fact_budget,
    )

    sync_cost = PythonOperator(
        task_id="airbyte_sync_fact_cost_actuals",
        python_callable=task_sync_fact_cost_actuals,
    )

    verify_bronze = PythonOperator(
        task_id="airbyte_verify_bronze_tables",
        python_callable=task_verify_bronze,
    )

    trigger_transform = TriggerDagRunOperator(
        task_id="trigger_medallion_transformation",
        trigger_dag_id="uc2_transform",
        wait_for_completion=False,
    )

    check_conn >> [sync_projects, sync_budget, sync_cost] >> verify_bronze >> trigger_transform
