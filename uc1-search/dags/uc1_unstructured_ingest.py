"""
uc1-search/dags/uc1_unstructured_ingest.py
Airflow DAG: uc1_unstructured_ingest
Orchestrates unstructured & semi-structured file ingestion:
Samba File Shares / S3 -> Multi-Format Extractor -> Presidio PII Redact -> OpenSearch Hybrid Index
"""

import sys
import os
from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator

# Resolve UC1 modules
UC1_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if UC1_DIR not in sys.path:
    sys.path.insert(0, UC1_DIR)

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "retries": 1,
}


def task_generate_samples_if_needed(**context):
    sample_dir = os.environ.get("SAMPLE_DOCS_DIR", "/opt/airflow/data/sample_docs")
    if not os.path.exists(sample_dir) or len(os.listdir(sample_dir)) == 0:
        from ingestion.sample_generator import generate_all_samples
        print(f"Generating initial engineering sample documents in {sample_dir}")
        generate_all_samples(sample_dir)
    return {"status": "ready", "path": sample_dir}


def task_ingest_engineering_documents(**context):
    from ingestion.scanner import IngestionScanner
    scanner = IngestionScanner(
        tika_url=os.environ.get("TIKA_HOST", "http://tika:9998"),
        opensearch_host=os.environ.get("OPENSEARCH_HOST", "http://opensearch:9200")
    )
    samba_dir = os.environ.get("SAMBA_MOUNT_DIR", "/mnt/share/engineering-docs")
    sample_dir = os.environ.get("SAMPLE_DOCS_DIR", "/opt/airflow/data/sample_docs")

    results = []
    if os.path.exists(sample_dir):
        print(f"Scanning sample directory: {sample_dir}")
        res = scanner.scan_and_ingest(sample_dir)
        results.append(res)

    if os.path.exists(samba_dir):
        print(f"Scanning Samba share: {samba_dir}")
        res = scanner.scan_and_ingest(samba_dir)
        results.append(res)

    total_indexed = sum(r.get("indexed", 0) for r in results)
    print(f"Total documents indexed into OpenSearch: {total_indexed}")
    return {"total_indexed": total_indexed}


with DAG(
    dag_id="uc1_unstructured_ingest",
    default_args=DEFAULT_ARGS,
    description="Ingest and index unstructured engineering files into OpenSearch",
    schedule_interval=None,
    catchup=False,
    tags=["uc1", "unstructured", "search", "opensearch", "rag"],
) as dag:

    gen_samples = PythonOperator(
        task_id="generate_samples_if_needed",
        python_callable=task_generate_samples_if_needed,
    )

    ingest_docs = PythonOperator(
        task_id="ingest_engineering_documents",
        python_callable=task_ingest_engineering_documents,
    )

    gen_samples >> ingest_docs
