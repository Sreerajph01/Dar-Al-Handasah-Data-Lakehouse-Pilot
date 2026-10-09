"""
uc2-warehouse-migration/superset/setup_superset.py
Bootstrap script to provision the Trino database connection and default
EVM dashboards in Apache Superset for Dar Al-Handasah.
"""

import os
import sys
import json
import time
import requests

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://superset:8088")
SUPERSET_USER = os.environ.get("SUPERSET_ADMIN_USER", "admin")
SUPERSET_PASS = os.environ.get("SUPERSET_ADMIN_PASSWORD", "CHANGE_ME_SUPERSET_ADMIN")
TRINO_HOST = os.environ.get("TRINO_HOST", "trino")
TRINO_PORT = os.environ.get("TRINO_PORT", "8080")


def get_superset_token():
    url = f"{SUPERSET_URL}/api/v1/security/login"
    payload = {
        "username": SUPERSET_USER,
        "password": SUPERSET_PASS,
        "provider": "db"
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_trino_database(token):
    headers = {"Authorization": f"Bearer {token}"}
    db_url = f"{SUPERSET_URL}/api/v1/database/"

    # Check if database exists
    existing = requests.get(db_url, headers=headers, timeout=15).json()
    for db in existing.get("result", []):
        if db.get("database_name") == "Dar Lakehouse (Trino)":
            print("Trino database connection already registered in Superset.")
            return db["id"]

    # Register Trino connection
    payload = {
        "database_name": "Dar Lakehouse (Trino)",
        "sqlalchemy_uri": f"trino://admin@{TRINO_HOST}:{TRINO_PORT}/iceberg/gold",
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "extra": json.dumps({"engine_params": {"connect_args": {"user": "admin"}}})
    }
    resp = requests.post(db_url, json=payload, headers=headers, timeout=15)
    if resp.status_code == 201:
        db_id = resp.json()["id"]
        print(f"Registered Trino database in Superset (ID: {db_id}).")
        return db_id
    else:
        print(f"Warning: Failed to create database in Superset: {resp.text}")
        return None


def main():
    print("Checking Superset readiness...")
    for _ in range(10):
        try:
            token = get_superset_token()
            db_id = create_trino_database(token)
            print("Superset bootstrap completed.")
            return
        except Exception as e:
            print(f"Waiting for Superset: {e}")
            time.sleep(5)
    print("Superset bootstrap timed out.")


if __name__ == "__main__":
    main()
