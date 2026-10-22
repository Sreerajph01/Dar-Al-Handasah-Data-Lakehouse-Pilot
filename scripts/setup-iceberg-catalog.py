#!/usr/bin/env python3
"""
scripts/setup-iceberg-catalog.py
Creates Lakekeeper warehouse + Iceberg namespaces for bronze/silver/gold
in each environment namespace. Idempotent (409 = already exists = OK).
"""
import os
import sys
import json
import urllib.request
import urllib.error

LAKEKEEPER_URL = os.environ.get("LAKEKEEPER_CATALOG_URI", "http://lakekeeper:8181")
S3_ENDPOINT    = os.environ.get("S3_ENDPOINT",    "http://seaweedfs-s3:8333")
S3_ACCESS_KEY  = os.environ.get("S3_ACCESS_KEY",  "").split("#")[0].strip()
S3_SECRET_KEY  = os.environ.get("S3_SECRET_KEY",  "").split("#")[0].strip()
S3_REGION      = os.environ.get("S3_REGION",      "us-east-1").split("#")[0].strip()
ENVIRONMENT    = os.environ.get("ENVIRONMENT",    "dev").split("#")[0].strip()

WAREHOUSES = [
    {
        "warehouse-name": f"dar-lakehouse-{ENVIRONMENT}",
        "storage-profile": {
            "type": "s3",
            "bucket": "bronze-lakehouse",
            "endpoint": S3_ENDPOINT,
            "region": S3_REGION,
            "path-style-access": True,
            "sts-enabled": False,
            "flavor": "s3-compat"
        },
        "storage-credential": {
            "type": "s3",
            "credential-type": "access-key",
            "aws-access-key-id": S3_ACCESS_KEY,
            "aws-secret-access-key": S3_SECRET_KEY
        }
    }
]

NAMESPACES = ["bronze", "silver", "gold"]


def warehouse_name(warehouse: dict) -> str | None:
    """Return the field used by Lakekeeper list responses across supported APIs."""
    return warehouse.get("name") or warehouse.get("warehouse-name")


def warehouse_identifier(warehouse: dict) -> str | None:
    return warehouse.get("warehouse-id") or warehouse.get("id")


def post_json(path: str, payload: dict, custom_headers: dict = None) -> int:
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if custom_headers:
        headers.update(custom_headers)
    req = urllib.request.Request(
        f"{LAKEKEEPER_URL}{path}",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def get_json(path: str) -> dict:
    req = urllib.request.Request(f"{LAKEKEEPER_URL}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def post_json_return_body(path, payload, custom_headers=None):
    url = f"{LAKEKEEPER_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if custom_headers:
        headers.update(custom_headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        print(f"HTTPError {e.code}: {body}")
        return e.code, {}

def main():
    # 0. Use the Lakekeeper default project which is always present after
    #    `lakekeeper-init migrate`.  The default project-id is the all-zeros UUID
    #    and is stable across resets because it is seeded by the migration.
    #    We do NOT try to create a new project; creating a random-UUID project on
    #    every fresh stack would leave Trino pointing at a stale project-id.
    DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000000"
    try:
        project_info = get_json("/management/v1/project")
        project_id = project_info.get("project-id", DEFAULT_PROJECT_ID)
        print(f"  ✓ Using Lakekeeper project: {project_id}")
    except Exception as e:
        print(f"WARN: Could not query project endpoint ({e}); falling back to default UUID")
        project_id = DEFAULT_PROJECT_ID

    # 1. List existing warehouses
    try:
        existing = get_json(f"/management/v1/warehouse?project-id={project_id}")
        # Lakekeeper's create payload uses ``warehouse-name``, but its list
        # response (v0.13.6) returns the field as ``name``.  Accept both so
        # a second seed resolves the existing warehouse instead of aborting.
        {warehouse_name(w) for w in existing.get("warehouses", [])}
    except Exception as e:
        print(f"WARN: Could not list warehouses: {e}")

    # 2. Create warehouses (idempotent – 409 = already exists = OK)
    warehouse_id = None
    for wh in WAREHOUSES:
        wh["project-id"] = project_id
        status, body = post_json_return_body("/management/v1/warehouse", wh, {"project-id": project_id})
        if status in (200, 201):
            print(f"  ✓ Created warehouse '{wh['warehouse-name']}'")
            warehouse_id = body.get("warehouse-id")
        elif status in (409, 422):
            print(f"  ✓ Warehouse '{wh['warehouse-name']}' already exists")
            existing = get_json(f"/management/v1/warehouse?project-id={project_id}")
            for w in existing.get("warehouses", []):
                if warehouse_name(w) == wh["warehouse-name"]:
                    warehouse_id = warehouse_identifier(w)
                    print(f"  ✓ Resolved warehouse-id: {warehouse_id}")
                    break
        else:
            print(f"  WARN: Create warehouse '{wh['warehouse-name']}' returned HTTP {status}")

    if not warehouse_id:
        print("FATAL: Could not obtain warehouse-id; aborting")
        sys.exit(1)

    print(f"  ✓ Warehouse-id: {warehouse_id}")

    # 3. Rewrite iceberg.properties so Trino uses the correct warehouse reference.
    #    The stable form is  <project-id>/<warehouse-name>  which Lakekeeper
    #    resolves regardless of the numeric warehouse-id.
    warehouse_ref = f"{project_id}/{WAREHOUSES[0]['warehouse-name']}"
    prop_file = "/repo/infra/trino/catalog/iceberg.properties"
    if os.path.exists(prop_file):
        import re
        with open(prop_file, "r") as f:
            content = f.read()
        content = re.sub(
            r"iceberg\.rest-catalog\.uri=.*",
            "iceberg.rest-catalog.uri=http://lakekeeper:8181/catalog",
            content
        )
        content = re.sub(
            r"iceberg\.rest-catalog\.warehouse=.*",
            f"iceberg.rest-catalog.warehouse={warehouse_ref}",
            content
        )
        if "iceberg.rest-catalog.warehouse=" not in content:
            content += f"\niceberg.rest-catalog.warehouse={warehouse_ref}\n"
        with open(prop_file, "w") as f:
            f.write(content)
        print(f"  ✓ iceberg.properties → warehouse={warehouse_ref}")
    else:
        print(f"  WARN: {prop_file} not found; skipping property update")

    # 4. Create namespaces (bronze / silver / gold) via the Iceberg REST catalog.
    for ns in NAMESPACES:
        payload = {"namespace": [ns], "properties": {}}
        path = f"/catalog/v1/{warehouse_id}/namespaces"
        status = post_json(path, payload)
        if status in (200, 201, 409):
            print(f"  ✓ Namespace '{ns}' ready (HTTP {status})")
        else:
            print(f"  WARN: Create namespace '{ns}' returned HTTP {status}")

    print("Iceberg catalog setup complete.")


if __name__ == "__main__":
    main()
