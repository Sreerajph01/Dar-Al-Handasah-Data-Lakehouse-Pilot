import json
import requests

SUPERSET_URL = "http://localhost:8088"
SUPERSET_USER = "admin"
SUPERSET_PASS = "admin_password"

session = requests.Session()
login_res = session.post(f"{SUPERSET_URL}/api/v1/security/login", json={
    "username": SUPERSET_USER,
    "password": SUPERSET_PASS,
    "provider": "db",
    "refresh": True
})
token = login_res.json()["access_token"]
session.headers.update({"Authorization": f"Bearer {token}"})

# Get CSRF
csrf_res = session.get(f"{SUPERSET_URL}/api/v1/security/csrf_token/")
csrf_token = csrf_res.json().get("result")
session.headers.update({"X-CSRFToken": csrf_token})

# Get database ID
dbs = session.get(f"{SUPERSET_URL}/api/v1/database/").json().get("result", [])
trino_db = next((d for d in dbs if "Trino" in d.get("database_name")), None)
if not trino_db:
    print("Creating Trino DB connection...")
    create_db_res = session.post(f"{SUPERSET_URL}/api/v1/database/", json={
        "database_name": "Dar Lakehouse (Trino)",
        "sqlalchemy_uri": "trino://admin@trino:8080/iceberg/gold",
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "extra": json.dumps({"engine_params": {"connect_args": {"user": "admin"}}})
    })
    db_id = create_db_res.json().get("id")
else:
    db_id = trino_db["id"]
print(f"Trino DB ID: {db_id}")

# Register Datasets
existing_datasets = session.get(f"{SUPERSET_URL}/api/v1/dataset/").json().get("result", [])
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
        })
        if ds_res.status_code == 201:
            dataset_map[key] = ds_res.json().get("id")
            print(f"Registered dataset {key} -> ID {dataset_map[key]}")
        else:
            print(f"Notice on registering dataset {key}: {ds_res.status_code} - {ds_res.text}")
    else:
        print(f"Dataset {key} already exists -> ID {dataset_map[key]}")

# Get Dashboards
dashs = session.get(f"{SUPERSET_URL}/api/v1/dashboard/").json().get("result", [])
dash_map = {d.get("slug"): d["id"] for d in dashs if d.get("slug")}
print("Dashboards found:", dash_map)

# Native Filter Configuration template
def make_filter_config(col_name="project_id", name="Project Filter"):
    return [
        {
            "id": f"NATIVE_FILTER_{col_name}",
            "name": name,
            "filterType": "filter_select",
            "targets": [{"datasetId": dataset_map.get("gold.evm_metrics", 1), "column": {"name": col_name}}],
            "defaultDataMask": {},
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "isInstant": True
        }
    ]

# Create Charts for EVM Dashboard
evm_dash_id = dash_map.get("dar-evm-portfolio")
cost_dash_id = dash_map.get("dar-cost-utilisation")

# Register Charts
existing_charts = session.get(f"{SUPERSET_URL}/api/v1/chart/").json().get("result", [])
existing_chart_names = {c.get("slice_name") for c in existing_charts}

charts_to_create = [
    {
        "slice_name": "Portfolio EVM Summary (CPI & SPI by Project)",
        "viz_type": "table",
        "datasource_id": dataset_map.get("gold.evm_metrics"),
        "datasource_type": "table",
        "dashboards": [evm_dash_id] if evm_dash_id else [],
        "params": json.dumps({
            "datasource": f"{dataset_map.get('gold.evm_metrics')}__table",
            "viz_type": "table",
            "groupby": ["project_id"],
            "metrics": [{"label": "Average CPI", "expressionType": "SQL", "sqlExpression": "AVG(cpi)"}],
            "row_limit": 50
        })
    },
    {
        "slice_name": "Budget vs Actual Allocation by WBS",
        "viz_type": "table",
        "datasource_id": dataset_map.get("gold.budget_vs_actual"),
        "datasource_type": "table",
        "dashboards": [evm_dash_id] if evm_dash_id else [],
        "params": json.dumps({
            "datasource": f"{dataset_map.get('gold.budget_vs_actual')}__table",
            "viz_type": "table",
            "groupby": ["wbs_id"],
            "metrics": [{"label": "Total Budget", "expressionType": "SQL", "sqlExpression": "SUM(total_budget)"}],
            "row_limit": 50
        })
    },
    {
        "slice_name": "Cost Variance (CV) & Schedule Variance (SV) by Project",
        "viz_type": "table",
        "datasource_id": dataset_map.get("gold.evm_metrics"),
        "datasource_type": "table",
        "dashboards": [cost_dash_id] if cost_dash_id else [],
        "params": json.dumps({
            "datasource": f"{dataset_map.get('gold.evm_metrics')}__table",
            "viz_type": "table",
            "groupby": ["project_id"],
            "metrics": [{"label": "Total CV", "expressionType": "SQL", "sqlExpression": "SUM(cv)"}],
            "row_limit": 50
        })
    }
]

created_chart_ids = []
for c in charts_to_create:
    name = c["slice_name"]
    if name not in existing_chart_names:
        c_res = session.post(f"{SUPERSET_URL}/api/v1/chart/", json=c)
        if c_res.status_code == 201:
            cid = c_res.json().get("id")
            created_chart_ids.append(cid)
            print(f"Created Chart '{name}' -> ID {cid}")
        else:
            print(f"Notice creating chart '{name}': {c_res.status_code} - {c_res.text}")
    else:
        cid = next((x["id"] for x in existing_charts if x.get("slice_name") == name), None)
        created_chart_ids.append(cid)
        print(f"Chart '{name}' already exists -> ID {cid}")

# Update Dashboards with Native Filters
for slug, d_id in dash_map.items():
    if not d_id: continue
    d_meta = {
        "native_filter_configuration": make_filter_config("project_id", "Project Filter"),
        "color_scheme": "supersetColors"
    }
    update_res = session.put(f"{SUPERSET_URL}/api/v1/dashboard/{d_id}", json={
        "json_metadata": json.dumps(d_meta)
    })
    print(f"Updated Dashboard {slug} (ID: {d_id}) with Native Filters: {update_res.status_code}")

print("\n--- Testing Chart Data Query from Trino ---")
if created_chart_ids and created_chart_ids[0]:
    cid = created_chart_ids[0]
    # Request chart data
    query_payload = {
        "datasource": {"id": dataset_map.get("gold.evm_metrics"), "type": "table"},
        "queries": [{
            "columns": ["project_id"],
            "metrics": [{"label": "Average CPI", "expressionType": "SQL", "sqlExpression": "AVG(cpi)"}],
            "row_limit": 10
        }],
        "result_format": "json",
        "result_type": "full"
    }
    data_res = session.post(f"{SUPERSET_URL}/api/v1/chart/data", json=query_payload)
    print("Chart Data API Status:", data_res.status_code)
    if data_res.status_code == 200:
        results = data_res.json().get("result", [{}])[0].get("data", [])
        print(f"Chart returned {len(results)} rows from Trino Lakehouse:")
        for r in results[:5]:
            print(" ", r)
