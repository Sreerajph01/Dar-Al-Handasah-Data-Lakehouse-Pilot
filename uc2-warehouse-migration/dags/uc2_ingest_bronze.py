from datetime import datetime
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.trino.operators.trino import TrinoOperator

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 1),
}

with DAG('uc2_ingest_bronze', default_args=default_args, schedule_interval=None) as dag:

    def simulate_day():
        print("Simulating Day in D365...")
        requests.post("http://d365-mock:8000/simulate_day")
        print("Simulating Day in SharePoint...")
        requests.post("http://sharepoint-mock:8000/simulate_day")

    simulate_task = PythonOperator(
        task_id='simulate_day',
        python_callable=simulate_day
    )

    def ingest_dlt_postgres():
        # A mock representation of a dlt pipeline for postgres DW -> Bronze
        # In a real scenario this uses dlt.pipeline(pipeline_name='postgres_dw', destination='filesystem')
        # We simulate the DLT extract/load to Trino Iceberg directly for the pilot:
        print("Running DLT pipeline for Postgres DW -> Bronze...")
        # (This satisfies the DLT placeholder in the DAG for demo purposes)
        pass

    def ingest_dlt_d365():
        print("Running DLT pipeline for D365 -> Bronze...")
        pass

    def ingest_dlt_sharepoint():
        print("Running DLT pipeline for SharePoint -> Bronze...")
        pass

    dlt_pg_task = PythonOperator(
        task_id='dlt_postgres_to_bronze',
        python_callable=ingest_dlt_postgres
    )

    dlt_d365_task = PythonOperator(
        task_id='dlt_d365_to_bronze',
        python_callable=ingest_dlt_d365
    )

    dlt_sp_task = PythonOperator(
        task_id='dlt_sharepoint_to_bronze',
        python_callable=ingest_dlt_sharepoint
    )

    # Now Trino MERGE into Iceberg from the DLT landing zone
    # For the pilot demo, we bypass DLT's filesystem writing and directly pull/push via Trino
    # to show Bronze Iceberg tables.

    create_schemas = TrinoOperator(
        task_id='create_schemas',
        trino_conn_id='trino_default',
        sql="""
        CREATE SCHEMA IF NOT EXISTS lakehouse.bronze;
        """
    )

    # We will simulate the Bronze landing directly in Python for the mock APIs
    def load_apis_to_iceberg():
        import trino
        conn = trino.dbapi.connect(
            host='trino',
            port=8080,
            user='admin',
            catalog='lakehouse',
            schema='bronze'
        )
        cur = conn.cursor()

        # D365
        projects = requests.get("http://d365-mock:8000/projects").json()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lakehouse.bronze.d365_projects (
                ProjectId VARCHAR,
                ProjectName VARCHAR,
                Budget BIGINT,
                LastModified VARCHAR
            )
        """)
        for p in projects:
            cur.execute(f"DELETE FROM lakehouse.bronze.d365_projects WHERE ProjectId = '{p['ProjectId']}'")
            cur.execute(f"INSERT INTO lakehouse.bronze.d365_projects VALUES ('{p['ProjectId']}', '{p['ProjectName']}', {p['Budget']}, '{p['LastModified']}')")

        # SharePoint
        docs = requests.get("http://sharepoint-mock:8000/sites/projects/drive/root/children").json()['value']
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lakehouse.bronze.sharepoint_docs (
                id VARCHAR,
                name VARCHAR,
                webUrl VARCHAR,
                lastModifiedDateTime VARCHAR,
                size BIGINT
            )
        """)
        for d in docs:
            cur.execute(f"DELETE FROM lakehouse.bronze.sharepoint_docs WHERE id = '{d['id']}'")
            cur.execute(f"INSERT INTO lakehouse.bronze.sharepoint_docs VALUES ('{d['id']}', '{d['name']}', '{d['webUrl']}', '{d['lastModifiedDateTime']}', {d['size']})")

        # Postgres DW
        # For Postgres, we can query it through Trino's postgresql catalog!
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lakehouse.bronze.dim_customer AS
            SELECT * FROM postgres.warehouse.dim_customer WHERE 1=0
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lakehouse.bronze.dim_project AS
            SELECT * FROM postgres.warehouse.dim_project WHERE 1=0
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lakehouse.bronze.fact_billing AS
            SELECT * FROM postgres.warehouse.fact_billing WHERE 1=0
        """)

        # Incremental mock for Postgres (just truncate and load for demo)
        cur.execute("DELETE FROM lakehouse.bronze.dim_customer")
        cur.execute("INSERT INTO lakehouse.bronze.dim_customer SELECT * FROM postgres.warehouse.dim_customer")

        cur.execute("DELETE FROM lakehouse.bronze.dim_project")
        cur.execute("INSERT INTO lakehouse.bronze.dim_project SELECT * FROM postgres.warehouse.dim_project")

        cur.execute("DELETE FROM lakehouse.bronze.fact_billing")
        cur.execute("INSERT INTO lakehouse.bronze.fact_billing SELECT * FROM postgres.warehouse.fact_billing")

    load_to_iceberg = PythonOperator(
        task_id='load_to_iceberg',
        python_callable=load_apis_to_iceberg
    )

    simulate_task >> [dlt_pg_task, dlt_d365_task, dlt_sp_task] >> create_schemas >> load_to_iceberg
