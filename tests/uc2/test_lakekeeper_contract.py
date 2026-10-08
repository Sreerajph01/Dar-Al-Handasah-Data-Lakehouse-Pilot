"""Contract checks for the Lakekeeper v0.13.6 warehouse list response."""

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "setup-iceberg-catalog.py"
SPEC = importlib.util.spec_from_file_location("lakekeeper_setup", MODULE_PATH)
lakekeeper_setup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(lakekeeper_setup)


def test_v0136_list_shape_is_resolved():
    warehouse = {"name": "dar-lakehouse-dev", "warehouse-id": "wk-v0136"}
    assert lakekeeper_setup.warehouse_name(warehouse) == "dar-lakehouse-dev"
    assert lakekeeper_setup.warehouse_identifier(warehouse) == "wk-v0136"


def test_legacy_list_shape_is_resolved():
    warehouse = {"warehouse-name": "dar-lakehouse-dev", "id": "wk-legacy"}
    assert lakekeeper_setup.warehouse_name(warehouse) == "dar-lakehouse-dev"
    assert lakekeeper_setup.warehouse_identifier(warehouse) == "wk-legacy"
