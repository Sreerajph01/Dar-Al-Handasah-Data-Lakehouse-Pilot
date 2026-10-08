"""
SharePoint / Microsoft Graph-style mock (FastAPI).
Stand-in for real Microsoft 365 / SharePoint Online tenant.
Real connector: dlt Microsoft Graph source or custom HTTP source.
Swap SHAREPOINT_MOCK_URL env var for production Graph endpoint.

Endpoints:
  GET /sites/projects/drive/root/children          — list all drive items
  GET /sites/projects/drive/root/delta             — delta query (incremental)
  GET /sites/projects/lists/{listName}/items       — list items (StatusUpdates, RiskRegister, ChangeRequests)
  GET /health
"""

from fastapi import FastAPI, HTTPException, Query, Request
from datetime import datetime
import json
import os

app = FastAPI(
    title="Dar SharePoint / Graph Mock",
    description="Microsoft Graph-style REST mock for SharePoint. "
                "Stand-in for production M365 tenant. "
                "Swap SHAREPOINT_MOCK_URL for real Graph endpoint.",
    version="1.0.0",
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data.json")
VALID_LISTS = {"StatusUpdates", "RiskRegister", "ChangeRequests"}


def load_data() -> dict:
    if not os.path.exists(DATA_PATH):
        return {"DriveItems": [], "ListItems": {}}
    with open(DATA_PATH, "r") as f:
        return json.load(f)


@app.get("/health")
def health():
    return {"status": "ok", "service": "sharepoint-mock", "timestamp": datetime.utcnow().isoformat()}


@app.get("/sites/projects/drive/root/children")
def list_drive_items(
    request: Request,
    top: int = Query(200, alias="$top", ge=1, le=1000),
    skip_token: str = Query(None, alias="$skiptoken"),
):
    """
    Enumerate drive items (documents) with pagination.
    Uses $skiptoken as integer offset.
    """
    data  = load_data()
    items = data.get("DriveItems", [])
    skip  = int(skip_token) if skip_token else 0
    page  = items[skip: skip + top]

    response: dict = {"value": page}
    if skip + top < len(items):
        base = str(request.url).split("?")[0]
        response["@odata.nextLink"] = f"{base}?$top={top}&$skiptoken={skip + top}"
    return response


@app.get("/sites/projects/drive/root/delta")
def drive_delta(
    request: Request,
    delta_token: str = Query(None, alias="$deltatoken"),
):
    """
    Delta query — returns items modified since deltaToken (ISO timestamp).
    On first call (no token) returns everything.
    Always returns @odata.deltaLink with the current server time as the next token.
    """
    data  = load_data()
    items = data.get("DriveItems", [])

    if delta_token:
        items = [x for x in items if (x.get("lastModifiedDateTime") or "") >= delta_token]

    new_token = datetime.utcnow().isoformat()
    base = str(request.url).split("?")[0]
    return {
        "value": items,
        "@odata.deltaLink": f"{base}?$deltatoken={new_token}",
    }


@app.get("/sites/projects/lists/{list_name}/items")
def list_items(
    list_name: str,
    request: Request,
    top: int = Query(200, alias="$top", ge=1, le=1000),
    skip_token: str = Query(None, alias="$skiptoken"),
    modified_since: str = Query(None, alias="$filter"),
):
    """
    SharePoint list items (StatusUpdates, RiskRegister, ChangeRequests).
    """
    if list_name not in VALID_LISTS:
        raise HTTPException(status_code=404,
                            detail=f"List '{list_name}' not found. Valid: {sorted(VALID_LISTS)}")
    data  = load_data()
    items = data.get("ListItems", {}).get(list_name, [])

    if modified_since and "lastModifiedDateTime ge" in modified_since:
        ts = modified_since.split("ge")[1].strip().strip("'\" ")
        items = [x for x in items if (x.get("lastModifiedDateTime") or "") >= ts]

    skip = int(skip_token) if skip_token else 0
    page = items[skip: skip + top]

    response: dict = {"value": page}
    if skip + top < len(items):
        base = str(request.url).split("?")[0]
        response["@odata.nextLink"] = f"{base}?$top={top}&$skiptoken={skip + top}"
    return response
