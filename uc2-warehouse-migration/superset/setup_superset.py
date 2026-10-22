"""
uc2-warehouse-migration/superset/setup_superset.py
Bootstrap script to provision the Trino database connection and default
EVM and Cost/Utilisation dashboards in Apache Superset for Dar Al-Handasah.
"""

import os
import json
import time
import glob
import requests

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://superset:8088")
SUPERSET_USER = os.environ.get("SUPERSET_ADMIN_USER", "admin")
SUPERSET_PASS = os.environ.get("SUPERSET_ADMIN_PASSWORD", "cZfxd4XsPLuDf-8V")
TRINO_HOST = os.environ.get("TRINO_HOST", "trino")
TRINO_PORT = "8080"


def get_authenticated_session():
    session = requests.Session()
    url = f"{SUPERSET_URL}/api/v1/security/login"
    payload = {
        "username": SUPERSET_USER,
        "password": SUPERSET_PASS,
        "provider": "db"
    }
    resp = session.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    
    # Superset 4.x requires CSRF token for state-changing POST requests
    csrf_resp = session.get(f"{SUPERSET_URL}/api/v1/security/csrf_token/", timeout=15)
    if csrf_resp.status_code == 200:
        csrf_token = csrf_resp.json().get("result")
        session.headers.update({"X-CSRFToken": csrf_token})
    return session


def create_trino_database(session):
    db_url = f"{SUPERSET_URL}/api/v1/database/"

    existing = session.get(db_url, timeout=15).json()
    for db in existing.get("result", []):
        if db.get("database_name") == "Dar Lakehouse (Trino)":
            print("Trino database connection already registered in Superset.")
            return db["id"]

    payload = {
        "database_name": "Dar Lakehouse (Trino)",
        "sqlalchemy_uri": f"trino://admin@{TRINO_HOST}:{TRINO_PORT}/iceberg/gold",
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "extra": json.dumps({"engine_params": {"connect_args": {"user": "admin"}}})
    }
    resp = session.post(db_url, json=payload, timeout=15)
    if resp.status_code == 201:
        db_id = resp.json()["id"]
        print(f"Registered Trino database in Superset (ID: {db_id}).")
        return db_id
    else:
        print(f"Notice on database creation in Superset: {resp.text}")
        return None


def provision_datasets_and_charts(session, db_id, dash_map):
    # Register Datasets
    existing_datasets = session.get(f"{SUPERSET_URL}/api/v1/dataset/", timeout=15).json().get("result", [])
    dataset_map = {}
    for ds in existing_datasets:
        key = f"{ds.get('schema')}.{ds.get('table_name')}"
        dataset_map[key] = ds["id"]

    tables_to_register = [
        ("gold", "evm_metrics"),
        ("gold", "budget_vs_actual"),
        ("gold", "project_summary"),
        ("silver", "fact_timesheet")
    ]

    for schema, table in tables_to_register:
        key = f"{schema}.{table}"
        if key not in dataset_map:
            ds_res = session.post(f"{SUPERSET_URL}/api/v1/dataset/", json={
                "database": db_id,
                "schema": schema,
                "table_name": table
            }, timeout=15)
            if ds_res.status_code == 201:
                dataset_map[key] = ds_res.json().get("id")
                print(f"Registered dataset {key} -> ID {dataset_map[key]}")
            else:
                print(f"Notice on registering dataset {key}: {ds_res.status_code} - {ds_res.text}")
        else:
            print(f"Dataset {key} already exists -> ID {dataset_map[key]}")

    # Register Charts
    existing_charts = session.get(f"{SUPERSET_URL}/api/v1/chart/", timeout=15).json().get("result", [])
    existing_chart_names = {c.get("slice_name") for c in existing_charts}

    evm_dash_id = dash_map.get("dar-evm-portfolio")
    cost_dash_id = dash_map.get("dar-cost-utilisation")

    charts_to_create = [
        {
            "slice_name": "Portfolio EVM Summary (CPI & SPI by Project)",
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": dataset_map.get("gold.evm_metrics"),
            "datasource_type": "table",
            "dashboards": [evm_dash_id] if evm_dash_id else [],
            "params": json.dumps({
                "datasource": f"{dataset_map.get('gold.evm_metrics')}__table",
                "viz_type": "echarts_timeseries_bar",
                "groupby": ["project_id"],
                "metrics": [
                    {"label": "Average CPI", "expressionType": "SQL", "sqlExpression": "AVG(cpi)"},
                    {"label": "Average SPI", "expressionType": "SQL", "sqlExpression": "AVG(spi)"}
                ],
                "orientation": "vertical",
                "show_legend": True,
                "row_limit": 50
            })
        },
        {
            "slice_name": "Budget vs Actual Allocation by WBS",
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": dataset_map.get("gold.budget_vs_actual"),
            "datasource_type": "table",
            "dashboards": [evm_dash_id] if evm_dash_id else [],
            "params": json.dumps({
                "datasource": f"{dataset_map.get('gold.budget_vs_actual')}__table",
                "viz_type": "echarts_timeseries_bar",
                "groupby": ["wbs_id"],
                "metrics": [{"label": "Total Budget", "expressionType": "SQL", "sqlExpression": "SUM(total_budget)"}],
                "orientation": "vertical",
                "show_legend": True,
                "row_limit": 25
            })
        },
        {
            "slice_name": "Cost Variance (CV) & Schedule Variance (SV) by Project",
            "viz_type": "echarts_timeseries_line",
            "datasource_id": dataset_map.get("gold.evm_metrics"),
            "datasource_type": "table",
            "dashboards": [cost_dash_id] if cost_dash_id else [],
            "params": json.dumps({
                "datasource": f"{dataset_map.get('gold.evm_metrics')}__table",
                "viz_type": "echarts_timeseries_line",
                "x_axis": "date_id",
                "metrics": [
                    {"label": "Total CV", "expressionType": "SQL", "sqlExpression": "SUM(cv)"},
                    {"label": "Total SV", "expressionType": "SQL", "sqlExpression": "SUM(sv)"}
                ],
                "show_legend": True,
                "row_limit": 100
            })
        }
    ]

    for c in charts_to_create:
        name = c["slice_name"]
        if name not in existing_chart_names:
            c_res = session.post(f"{SUPERSET_URL}/api/v1/chart/", json=c, timeout=15)
            if c_res.status_code == 201:
                print(f"Created Chart '{name}' -> ID {c_res.json().get('id')}")
            else:
                print(f"Notice creating chart '{name}': {c_res.status_code} - {c_res.text}")

    # Add Native Filters to Dashboards
    for slug, d_id in dash_map.items():
        if not d_id: continue
        filter_cfg = [
            {
                "id": "NATIVE_FILTER_project_id",
                "name": "Project Filter",
                "filterType": "filter_select",
                "targets": [{"datasetId": dataset_map.get("gold.evm_metrics", 1), "column": {"name": "project_id"}}],
                "defaultDataMask": {},
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True
            }
        ]
        d_meta = {
            "native_filter_configuration": filter_cfg,
            "color_scheme": "supersetColors"
        }
        session.put(f"{SUPERSET_URL}/api/v1/dashboard/{d_id}", json={
            "json_metadata": json.dumps(d_meta)
        }, timeout=15)
        print(f"Configured Native Project Filter on Dashboard {slug} (ID: {d_id})")


def provision_dashboards(session):
    dash_url = f"{SUPERSET_URL}/api/v1/dashboard/"

    # Fetch existing dashboards
    existing_resp = session.get(dash_url, timeout=15).json()
    dash_map = {d.get("slug"): d["id"] for d in existing_resp.get("result", []) if d.get("slug")}

    # Look for dashboard json files
    dash_dir = os.path.join(os.path.dirname(__file__), "dashboards")
    if not os.path.exists(dash_dir):
        dash_dir = "/app/superset_home/dashboards"

    json_files = glob.glob(os.path.join(dash_dir, "*.json"))
    for jf in json_files:
        try:
            with open(jf, "r") as f:
                data = json.load(f)
            slug = data.get("slug")
            title = data.get("dashboard_title", "Dar Dashboard")
            if slug in dash_map:
                print(f"Dashboard '{title}' ({slug}) already exists in Superset (ID: {dash_map[slug]}).")
                continue

            payload = {
                "dashboard_title": title,
                "slug": slug,
                "json_metadata": json.dumps(data.get("metadata", {})),
                "published": True
            }
            resp = session.post(dash_url, json=payload, timeout=15)
            if resp.status_code in (200, 201):
                new_id = resp.json()["id"]
                dash_map[slug] = new_id
                print(f"Provisioned dashboard: '{title}' ({slug}) -> ID {new_id}")
            else:
                print(f"Notice on provisioning '{title}': {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Error provisioning dashboard from {jf}: {e}")

    return dash_map


def main():
    print("Checking Superset readiness...")
    for attempt in range(1, 15):
        try:
            session = get_authenticated_session()
            db_id = create_trino_database(session)
            dash_map = provision_dashboards(session)
            if db_id:
                provision_datasets_and_charts(session, db_id, dash_map)
            print("Superset bootstrap and dashboard provisioning completed successfully.")
            return
        except Exception as e:
            print(f"Waiting for Superset (attempt {attempt}/15): {e}")
            time.sleep(5)
    print("Superset bootstrap timed out.")


if __name__ == "__main__":
    main()
