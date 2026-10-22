"""
scripts/run_bronze_ingest.py
Standalone Bronze Loader runner for Dar Al-Handasah Lakehouse Pilot.
Loads D365, SharePoint, and PostgreSQL DW into Iceberg Bronze tables via Trino.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, "/repo/uc2-warehouse-migration/ingestion/dlt_pipelines")
import bronze_loader as bl

def main():
    batch_id = f"manual_{int(datetime.now().timestamp())}"
    now = datetime.now(timezone.utc)
    print(f"Starting Bronze Full Load (Batch: {batch_id})...")

    print("\n--- Ingesting PostgreSQL Data Warehouse to Iceberg Bronze ---")
    pg_counts = bl.full_load_postgres(batch_id, now)
    print(f"PostgreSQL loaded: {pg_counts}")

    print("\n--- Ingesting D365 F&O to Iceberg Bronze ---")
    d365_counts = bl.full_load_d365(batch_id, now)
    print(f"D365 loaded: {d365_counts}")

    print("\n--- Ingesting SharePoint to Iceberg Bronze ---")
    sp_counts = bl.full_load_sharepoint(batch_id, now)
    print(f"SharePoint loaded: {sp_counts}")

    print("\nBronze ingestion complete!")

if __name__ == "__main__":
    main()
