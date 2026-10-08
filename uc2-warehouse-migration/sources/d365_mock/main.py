"""
D365 F&O OData-style mock (FastAPI).
Stand-in for real Dynamics 365 Finance & Operations tenant.
Real connector: dlt d365 source — swap MOCK_URL env var for production endpoint.

Endpoints:
  GET /data/{entity}?$filter=ModifiedAt ge '...'&$top=N&$skip=N
  GET /health

Entities: Projects, WBSElements, BudgetLines, LedgerJournalLines, Vendors
"""

from fastapi import FastAPI, HTTPException, Query, Request
from datetime import datetime
import json
import os

app = FastAPI(
    title="Dar D365 F&O Mock",
    description="OData-style mock for Dynamics 365 Finance & Operations. "
                "Stand-in for production D365 tenant. "
                "Swap D365_MOCK_URL environment variable for real endpoint.",
    version="1.0.0",
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data.json")

VALID_ENTITIES = {
    "Projects",
    "WBSElements",
    "BudgetLines",
    "LedgerJournalLines",
    "Vendors",
}


def load_data() -> dict:
    if not os.path.exists(DATA_PATH):
        return {e: [] for e in VALID_ENTITIES}
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def odata_filter(items: list, filter_str: str | None) -> list:
    """
    Minimal OData $filter: supports `ModifiedAt ge 'TIMESTAMP'`.
    Returns all items when no filter.
    """
    if not filter_str:
        return items
    # ModifiedAt ge 'YYYY-MM-DDTHH:MM:SS'
    if filter_str.startswith("ModifiedAt ge "):
        ts_str = filter_str[len("ModifiedAt ge "):].strip("'\" ")
        return [x for x in items if (x.get("ModifiedAt") or "") >= ts_str]
    return items


@app.get("/health")
def health():
    return {"status": "ok", "service": "d365-mock", "timestamp": datetime.utcnow().isoformat()}


@app.get("/data/{entity}")
def get_entity(
    entity: str,
    request: Request,
    top: int = Query(500, alias="$top", ge=1, le=5000),
    skip: int = Query(0, alias="$skip", ge=0),
    filter_str: str = Query(None, alias="$filter"),
    select: str = Query(None, alias="$select"),
):
    """
    OData entity endpoint.
    Returns: { "value": [...], "@odata.count": N, "@odata.nextLink": URL|null }
    """
    if entity not in VALID_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Entity '{entity}' not found. "
                                                    f"Valid: {sorted(VALID_ENTITIES)}")
    data = load_data()
    all_items = data.get(entity, [])
    filtered  = odata_filter(all_items, filter_str)
    total     = len(filtered)
    page      = filtered[skip: skip + top]

    # Field projection ($select)
    if select:
        fields = [f.strip() for f in select.split(",")]
        page = [{k: v for k, v in item.items() if k in fields} for item in page]

    response: dict = {
        "value": page,
        "@odata.count": total,
    }
    next_skip = skip + top
    if next_skip < total:
        base = str(request.url).split("?")[0]
        params = f"$top={top}&$skip={next_skip}"
        if filter_str:
            params += f"&$filter={filter_str}"
        response["@odata.nextLink"] = f"{base}?{params}"

    return response
