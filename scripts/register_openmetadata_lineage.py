"""
scripts/register_openmetadata_lineage.py
Registers Trino Lakehouse entities and end-to-end lineage into OpenMetadata,
then fetches and displays the complete Lineage Graph for Gold budget_vs_actual.
"""

import base64
import json
import requests
import sys

OM_URL = "http://openmetadata:8585"

def main():
    print(f"Connecting to OpenMetadata at {OM_URL}...")
    pwd = base64.b64encode(b"admin").decode()
    login_resp = requests.post(
        f"{OM_URL}/api/v1/users/login",
        json={"email": "admin@open-metadata.org", "password": pwd},
        timeout=10
    )
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.status_code} {login_resp.text}")
        sys.exit(1)

    token = login_resp.json()["accessToken"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("Authenticated successfully with OpenMetadata.")

    # 1. Create Database Service: Trino
    service_payload = {
        "name": "trino_lakehouse",
        "serviceType": "Trino",
        "description": "Dar Al-Handasah Iceberg Lakehouse Engine on Trino"
    }
    svc_resp = requests.post(f"{OM_URL}/api/v1/services/databaseServices", headers=headers, json=service_payload)
    if svc_resp.status_code in (200, 201):
        print("Created DatabaseService 'trino_lakehouse'")
    elif svc_resp.status_code == 409:
        print("DatabaseService 'trino_lakehouse' already exists.")

    # 2. Create Database: iceberg
    db_payload = {
        "name": "iceberg",
        "service": "trino_lakehouse",
        "description": "Apache Iceberg catalog database"
    }
    db_resp = requests.post(f"{OM_URL}/api/v1/databases", headers=headers, json=db_payload)
    if db_resp.status_code in (200, 201):
        print("Created Database 'iceberg'")
    elif db_resp.status_code == 409:
        print("Database 'iceberg' already exists.")

    # 3. Create Schemas: bronze, silver, gold
    for schema_name in ["bronze", "silver", "gold"]:
        schema_payload = {
            "name": schema_name,
            "database": "trino_lakehouse.iceberg",
            "description": f"Medallion {schema_name.capitalize()} tier"
        }
        s_resp = requests.post(f"{OM_URL}/api/v1/databaseSchemas", headers=headers, json=schema_payload)
        if s_resp.status_code in (200, 201):
            print(f"Created Schema '{schema_name}'")

    # 4. Create Tables
    # Bronze
    bronze_resp = requests.post(
        f"{OM_URL}/api/v1/tables",
        headers=headers,
        json={
            "name": "pg_fact_budget",
            "databaseSchema": "trino_lakehouse.iceberg.bronze",
            "description": "Bronze append-only CDC mirror of Postgres DW fact_budget",
            "columns": [
                {"name": "budget_id", "dataType": "VARCHAR", "dataLength": 100},
                {"name": "wbs_id", "dataType": "VARCHAR", "dataLength": 100},
                {"name": "budget_amount", "dataType": "VARCHAR", "dataLength": 100},
                {"name": "currency", "dataType": "VARCHAR", "dataLength": 10}
            ]
        }
    )
    bronze_tbl = bronze_resp.json()

    # Silver
    silver_resp = requests.post(
        f"{OM_URL}/api/v1/tables",
        headers=headers,
        json={
            "name": "fact_budget",
            "databaseSchema": "trino_lakehouse.iceberg.silver",
            "description": "Silver cleansed and FX-normalized budget facts in USD",
            "columns": [
                {"name": "budget_id", "dataType": "VARCHAR", "dataLength": 100},
                {"name": "wbs_id", "dataType": "VARCHAR", "dataLength": 100},
                {"name": "amount", "dataType": "NUMERIC"},
                {"name": "currency", "dataType": "VARCHAR", "dataLength": 10}
            ]
        }
    )
    silver_tbl = silver_resp.json()

    # Gold
    gold_resp = requests.post(
        f"{OM_URL}/api/v1/tables",
        headers=headers,
        json={
            "name": "budget_vs_actual",
            "databaseSchema": "trino_lakehouse.iceberg.gold",
            "description": "Gold aggregated budget and cost analysis per WBS",
            "columns": [
                {"name": "wbs_id", "dataType": "VARCHAR", "dataLength": 100},
                {"name": "total_budget", "dataType": "NUMERIC"},
                {"name": "currency", "dataType": "VARCHAR", "dataLength": 10}
            ]
        }
    )
    gold_tbl = gold_resp.json()

    bronze_id = bronze_tbl.get("id") or requests.get(f"{OM_URL}/api/v1/tables/name/trino_lakehouse.iceberg.bronze.pg_fact_budget", headers=headers).json()["id"]
    silver_id = silver_tbl.get("id") or requests.get(f"{OM_URL}/api/v1/tables/name/trino_lakehouse.iceberg.silver.fact_budget", headers=headers).json()["id"]
    gold_id   = gold_tbl.get("id")   or requests.get(f"{OM_URL}/api/v1/tables/name/trino_lakehouse.iceberg.gold.budget_vs_actual", headers=headers).json()["id"]

    print(f"Bronze Table ID: {bronze_id}")
    print(f"Silver Table ID: {silver_id}")
    print(f"Gold Table ID:   {gold_id}")

    # 5. Create Lineage Edges
    # Edge 1: Bronze -> Silver
    edge1 = requests.put(
        f"{OM_URL}/api/v1/lineage",
        headers=headers,
        json={
            "edge": {
                "fromEntity": {"id": bronze_id, "type": "table"},
                "toEntity": {"id": silver_id, "type": "table"},
                "description": "dbt bronze-to-silver FX normalization transformation"
            }
        }
    )
    print(f"Lineage Bronze -> Silver: {edge1.status_code}")

    # Edge 2: Silver -> Gold
    edge2 = requests.put(
        f"{OM_URL}/api/v1/lineage",
        headers=headers,
        json={
            "edge": {
                "fromEntity": {"id": silver_id, "type": "table"},
                "toEntity": {"id": gold_id, "type": "table"},
                "description": "dbt silver-to-gold WBS aggregation transformation"
            }
        }
    )
    print(f"Lineage Silver -> Gold: {edge2.status_code}")

    # 6. Fetch Lineage Graph for Gold table
    gold_fqn = "trino_lakehouse.iceberg.gold.budget_vs_actual"
    graph_resp = requests.get(
        f"{OM_URL}/api/v1/lineage/table/name/{gold_fqn}?upstreamDepth=3&downstreamDepth=3",
        headers=headers
    )
    print(f"\n========================================================")
    print(f"OPENMETADATA LINEAGE GRAPH FOR {gold_fqn}")
    print(f"========================================================")
    print(json.dumps(graph_resp.json(), indent=2))

if __name__ == "__main__":
    main()
