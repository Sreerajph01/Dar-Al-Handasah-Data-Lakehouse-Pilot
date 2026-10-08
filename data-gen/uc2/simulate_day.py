#!/usr/bin/env python3
"""
data-gen/uc2/simulate_day.py
Advance the day simulator: inserts, updates, and soft-deletes rows in all three
source systems. Designed to be run via `make simulate-day` from WSL2.

Changes produced on each run:
  Postgres DW:
    - INSERT 2 new timesheet rows (new working day)
    - UPDATE dim_employee row 1 (role change + row_version bump)
    - soft-DELETE dim_employee row 2 (is_deleted=TRUE, row_version bump)
    - INSERT 1 new fact_evm_snapshot for each project (next week)

  D365 mock (JSON):
    - INSERT 1 new Project
    - UPDATE Projects[0] (status change, row_version bump, _op='U')
    - soft-DELETE Projects[1] (_op='D', if ≥2 projects exist)

  SharePoint mock (JSON):
    - INSERT 1 new DriveItem
    - UPDATE DriveItems[0] (size change, _op='U')
    - soft-DELETE DriveItems[1] (_op='D', if ≥2 items exist)

Run from WSL2:
    python data-gen/uc2/simulate_day.py
"""

import json
import os
import random
import sys
from datetime import date, datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Resolve repo root regardless of cwd
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)

# ---------------------------------------------------------------------------
# Configuration from environment (set by Makefile via .env)
# ---------------------------------------------------------------------------
PG_HOST = os.environ.get("PG_DW_HOST_ACCESS", "localhost")  # host-accessible
PG_PORT = int(os.environ.get("PG_DW_PORT", "5434"))
PG_DB   = os.environ.get("PG_DW_DB", "DAR_DW")
PG_USER = os.environ.get("PG_DW_SA_USER", "dar_dw_admin")
PG_PASS = os.environ.get("PG_DW_SA_PASSWORD", "CHANGE_ME_DW_ADMIN")

rng = random.Random()  # unseeded — want different data each simulate-day call


# ---------------------------------------------------------------------------
# Postgres mutations
# ---------------------------------------------------------------------------
def simulate_postgres():
    print("Simulating Postgres DW changes...")
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT,
                            user=PG_USER, password=PG_PASS, database=PG_DB)
    cur  = conn.cursor()
    now  = datetime.utcnow()

    # --- 1. INSERT new timesheet rows (simulate staff logging hours today) ---
    cur.execute("SELECT MAX(timesheet_id) FROM warehouse.fact_timesheet")
    max_ts = cur.fetchone()[0] or 0

    cur.execute("SELECT employee_id FROM warehouse.dim_employee WHERE is_deleted = FALSE LIMIT 10")
    emp_ids = [r[0] for r in cur.fetchall()]

    cur.execute(
        "SELECT wbs_id FROM warehouse.dim_wbs WHERE is_summary = FALSE AND is_deleted = FALSE LIMIT 20"
    )
    wbs_ids = [r[0] for r in cur.fetchall()]

    today = date.today()
    new_timesheets = []
    for i, eid in enumerate(emp_ids[:2]):
        wid = rng.choice(wbs_ids) if wbs_ids else "MISSING"
        new_timesheets.append((
            max_ts + i + 1,
            eid,
            wid,
            today,
            round(rng.uniform(1.0, 8.0), 2),
            rng.choice(["DESIGN", "SITE", "REVIEW", None]),
            False,
            None,
            now,
            now,
            1,
            False,
        ))

    execute_values(cur, """
        INSERT INTO warehouse.fact_timesheet
          (timesheet_id, employee_id, wbs_id, date_id, hours, activity_code,
           is_approved, approved_by, submitted_at, modified_at, row_version, is_deleted)
        VALUES %s
        ON CONFLICT (timesheet_id) DO NOTHING
    """, new_timesheets)
    print(f"  Inserted {len(new_timesheets)} timesheet rows")

    # UPDATE a timesheet to generate CDC history for Bronze duplicate test
    cur.execute("""
        UPDATE warehouse.fact_timesheet
        SET hours = hours + 1, modified_at = %s, row_version = row_version + 1
        WHERE timesheet_id = (SELECT MIN(timesheet_id) FROM warehouse.fact_timesheet)
    """, (now,))
    print(f"  Updated 1 timesheet row (CDC history generation)")

    # --- 2. UPDATE dim_employee row 1 (role promotion) ---
    cur.execute("""
        UPDATE warehouse.dim_employee
        SET role = 'Principal Engineer', modified_at = %s, row_version = row_version + 1
        WHERE employee_id = 1
    """, (now,))
    print(f"  Updated dim_employee id=1 (role → Principal Engineer)")

    # --- 3. Soft-DELETE dim_employee row 2 ---
    cur.execute("""
        UPDATE warehouse.dim_employee
        SET is_deleted = TRUE, modified_at = %s, row_version = row_version + 1
        WHERE employee_id = 2 AND is_deleted = FALSE
    """, (now,))
    print("  Soft-deleted dim_employee id=2")

    # --- 4. INSERT 1 new EVM snapshot per project ---
    cur.execute("""
        SELECT project_id, MAX(date_id) as last_snapshot
        FROM warehouse.fact_evm_snapshot
        WHERE is_deleted = FALSE
        GROUP BY project_id
    """)
    evm_rows = cur.fetchall()
    cur.execute("SELECT MAX(snapshot_id) FROM warehouse.fact_evm_snapshot")
    max_sid = cur.fetchone()[0] or 0

    new_evm = []
    for sid_offset, (pid, last_dt) in enumerate(evm_rows):
        next_dt = (last_dt if last_dt else date(2023, 1, 1)) + timedelta(days=7)
        pv = round(rng.uniform(10000, 100000), 2)
        ev = round(pv * rng.uniform(0.85, 1.15), 2)
        ac = round(ev * rng.uniform(0.90, 1.20), 2)
        bac = 5_000_000.00
        spi = round(ev / pv, 4) if pv else 1.0
        cpi = round(ev / ac, 4) if ac else 1.0
        new_evm.append((
            max_sid + sid_offset + 1,
            pid,
            next_dt,
            pv, ev, ac, bac,
            round(bac / cpi, 2) if cpi else bac,
            round(ev - pv, 2),
            round(ev - ac, 2),
            spi, cpi,
            round(min(100.0, (ev / bac) * 100), 2),
            now, 1, False,
        ))

    execute_values(cur, """
        INSERT INTO warehouse.fact_evm_snapshot
          (snapshot_id, project_id, date_id,
           planned_value, earned_value, actual_cost, budget_at_completion,
           estimate_at_completion, schedule_variance, cost_variance,
           spi, cpi, percent_complete, modified_at, row_version, is_deleted)
        VALUES %s
        ON CONFLICT (snapshot_id) DO NOTHING
    """, new_evm)
    print(f"  Inserted {len(new_evm)} EVM snapshot rows")

    conn.commit()
    cur.close()
    conn.close()
    print("  Postgres simulation complete.")


# ---------------------------------------------------------------------------
# D365 JSON mutations
# ---------------------------------------------------------------------------
def simulate_d365():
    print("Simulating D365 mock changes...")
    d365_path = os.path.join(
        REPO_ROOT, "uc2-warehouse-migration", "sources", "d365_mock", "data.json"
    )
    if not os.path.exists(d365_path):
        print("  WARN: D365 data.json not found — run make seed first")
        return

    with open(d365_path, "r") as f:
        data = json.load(f)

    now = datetime.utcnow().isoformat()

    # INSERT new project
    new_pid = f"SIM-{rng.randint(10000, 99999)}"
    data["Projects"].append({
        "ProjectId":      new_pid,
        "ProjectName":    f"Simulated Project {new_pid}",
        "ClientName":     "Sim Client",
        "ProjectType":    "Infrastructure",
        "CountryRegion":  "UAE",
        "CurrencyCode":   "USD",
        "Status":         "Active",
        "StartDate":      date.today().isoformat(),
        "PlannedEndDate": (date.today() + timedelta(days=365)).isoformat(),
        "ModifiedAt":     now,
        "RowVersion":     1,
        "_op":            "I",
    })
    print(f"  Inserted D365 project {new_pid}")

    # UPDATE Projects[0]
    if data["Projects"]:
        p = data["Projects"][0]
        old_status = p.get("Status", "Active")
        p["Status"]    = "Completed" if old_status == "Active" else "Active"
        p["ModifiedAt"] = now
        p["RowVersion"] = (p.get("RowVersion", 1) or 1) + 1
        p["_op"]        = "U"
        print(f"  Updated D365 project {p['ProjectId']} (status → {p['Status']})")

    # Soft-DELETE Projects[1]
    if len(data["Projects"]) > 1:
        p = data["Projects"][1]
        p["_op"]        = "D"
        p["ModifiedAt"] = now
        p["RowVersion"] = (p.get("RowVersion", 1) or 1) + 1
        print(f"  Soft-deleted D365 project {p['ProjectId']}")

    with open(d365_path, "w") as f:
        json.dump(data, f, default=str, indent=2)
    print("  D365 JSON written.")


# ---------------------------------------------------------------------------
# SharePoint JSON mutations
# ---------------------------------------------------------------------------
def simulate_sharepoint():
    print("Simulating SharePoint mock changes...")
    sp_path = os.path.join(
        REPO_ROOT, "uc2-warehouse-migration", "sources", "sharepoint_mock", "data.json"
    )
    if not os.path.exists(sp_path):
        print("  WARN: SharePoint data.json not found — run make seed first")
        return

    with open(sp_path, "r") as f:
        data = json.load(f)

    now = datetime.utcnow().isoformat()

    drive = data.get("DriveItems", [])

    # INSERT new drive item
    new_id = f"SIM-{rng.randint(10000, 99999)}"
    drive.append({
        "id":                    new_id,
        "name":                  f"SimSpec_{new_id}.docx",
        "projectId":             "SIM",
        "webUrl":                f"https://dar.sharepoint.example/SIM/{new_id}",
        "size":                  rng.randint(10000, 500000),
        "mimeType":              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "lastModifiedDateTime":  now,
        "_op":                   "I",
    })
    print(f"  Inserted SP drive item {new_id}")

    # UPDATE DriveItems[0]
    if drive:
        d = drive[0]
        d["size"]                   = (d.get("size", 0) or 0) + rng.randint(100, 10000)
        d["lastModifiedDateTime"]   = now
        d["_op"]                    = "U"
        print(f"  Updated SP drive item {d['id']}")

    # Soft-DELETE DriveItems[1]
    if len(drive) > 1:
        d = drive[1]
        d["_op"]                    = "D"
        d["lastModifiedDateTime"]   = now
        print(f"  Soft-deleted SP drive item {d['id']}")

    data["DriveItems"] = drive
    with open(sp_path, "w") as f:
        json.dump(data, f, default=str, indent=2)
    print("  SharePoint JSON written.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ts = datetime.utcnow().isoformat()
    print(f"=== simulate_day at {ts} ===")
    simulate_postgres()
    simulate_d365()
    simulate_sharepoint()
    print("=== simulate_day complete ===")
