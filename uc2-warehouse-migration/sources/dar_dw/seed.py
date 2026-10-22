#!/usr/bin/env python3
"""
uc2-warehouse-migration/sources/dar_dw/seed.py
Deterministic data generator for DAR_DW (PostgreSQL).
Also populates D365 mock (data.json) and SharePoint mock (data.json).

Usage:
    python seed.py [--scale small|bench]

Scale:
    small: 5 projects, 40 WBS/project, 50 employees, ~50k timesheet rows (demo)
    bench: 50 projects, 200 WBS/project, 500 employees, ~2M timesheet rows

Run inside Docker (bootstrap.sh does this automatically):
    docker run --rm --network dar-lakehouse_default \\
      --env-file .env -v $(pwd):/repo -w /repo \\
      python:3.11-slim bash -c \\
      "pip install --quiet psycopg2-binary && python uc2-warehouse-migration/sources/dar_dw/seed.py --scale small"
"""

import argparse
import json
import os
import random
import hashlib
import uuid
from datetime import date, datetime as _Datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Deterministic seed — identical data on every run for the same scale
# ---------------------------------------------------------------------------
SEED = 42
rng = random.Random(SEED)

# Fixtures are source-controlled generated artefacts: their hashes must be
# stable across `make seed` reruns.  Keep all seed timestamps fixed; simulated
# changes deliberately use the current time and therefore sort after them.
SEED_TIMESTAMP = _Datetime(2024, 1, 1, 0, 0, 0)


class datetime(_Datetime):
    @classmethod
    def utcnow(cls):
        return SEED_TIMESTAMP

# ---------------------------------------------------------------------------
# Scale definitions
# ---------------------------------------------------------------------------
SCALES = {
    "small": {
        "n_projects":      5,
        "wbs_per_project": 40,   # 8 L1 + 32 L2 per project
        "n_employees":     50,
        "timesheet_days":  180,  # 6 months
        "timesheet_prob":  0.30, # probability a (emp, wbs, day) has an entry
    },
    "bench": {
        "n_projects":      50,
        "wbs_per_project": 200,
        "n_employees":     500,
        "timesheet_days":  730,
        "timesheet_prob":  0.15,
    },
}

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
COUNTRIES = ["UAE", "Saudi Arabia", "Egypt", "UK", "USA", "Kuwait", "Jordan"]
PROJECT_TYPES = ["Infrastructure", "Building", "Transport", "Industrial", "Healthcare"]
STATUSES = ["Active", "Planning", "Completed", "OnHold"]
ROLES = ["Project Manager", "Engineer", "Senior Engineer", "Analyst", "Architect", "Technician"]
GRADES = ["G1", "G2", "G3", "G4", "G5", "G6"]
DEPARTMENTS = ["Engineering", "Finance", "Construction", "PMO", "Design"]
DISCIPLINES = ["Civil", "Structural", "MEP", "Architectural", "Geotechnical", None]
COST_CODES = [
    ("LABOR",       "Labour costs",          "LABOR",       True),
    ("MATERIAL",    "Material procurement",  "MATERIAL",    True),
    ("SUBCONTRACT", "Subcontractor fees",    "SUBCONTRACT", True),
    ("OVERHEAD",    "General overhead",      "OVERHEAD",    False),
    ("EQUIPMENT",   "Equipment rental",      "MATERIAL",    True),
]
CURRENCIES = ["USD", "EUR", "GBP", "AED", "SAR"]  # DQ: mixed currencies in source
START = date(2023, 1, 1)

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def row_hash(*args):
    """Deterministic hash for source_hash audit column."""
    h = hashlib.md5("|".join(str(a) for a in args).encode()).hexdigest()
    return h[:16]


def make_date_spine(n_days: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n_days)]


def fiscal_year(d: date) -> int:
    """Dar FY: April–March. FY2023 = Apr 2023 – Mar 2024."""
    return d.year if d.month >= 4 else d.year - 1


def fiscal_quarter(d: date) -> int:
    m = d.month
    if m >= 4 and m <= 6:
        return 1
    if m >= 7 and m <= 9:
        return 2
    if m >= 10 and m <= 12:
        return 3
    return 4


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
def gen_calendar(n_days: int) -> list[tuple]:
    rows = []
    for d in make_date_spine(n_days):
        dow = d.weekday()  # 0=Mon
        rows.append((
            d,
            d.year,
            (d.month - 1) // 3 + 1,
            d.month,
            MONTH_NAMES[d.month],
            d.day,
            dow,
            DAY_NAMES[dow],
            d.isocalendar()[1],
            dow >= 5,
            False,  # is_holiday (stub)
            fiscal_year(d),
            fiscal_quarter(d),
        ))
    return rows


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
def gen_projects(n: int) -> list[dict]:
    projects = []
    project_ids = [f"P{i+1:03d}" for i in range(n)]
    for i, pid in enumerate(project_ids):
        status = rng.choice(STATUSES)
        start = START + timedelta(days=rng.randint(0, 60))
        dur = rng.randint(365, 1460)
        # DQ: project index 2 has NULL name (deliberate)
        name = None if i == 2 else f"{rng.choice(PROJECT_TYPES)} {pid} - {rng.choice(COUNTRIES)}"
        projects.append({
            "project_id":       pid,
            "project_name":     name,
            "client_name":      f"Client-{chr(65 + i)}",
            "project_type":     rng.choice(PROJECT_TYPES),
            "country":          rng.choice(COUNTRIES),
            "currency":         rng.choice(["USD", "USD", "USD", "EUR", "GBP"]),  # USD-heavy
            "status":           status,
            "start_date":       start,
            "planned_end_date": start + timedelta(days=dur),
            "actual_end_date":  None if status != "Completed" else start + timedelta(days=dur + rng.randint(-30, 30)),
            "pm_employee_id":   i + 1,
            "modified_at":      datetime.utcnow(),
            "row_version":      1,
            "is_deleted":       False,
        })
    return projects


# ---------------------------------------------------------------------------
# WBS
# ---------------------------------------------------------------------------
def gen_wbs(projects: list[dict], wbs_per_project: int) -> list[dict]:
    """
    Hierarchical: 8 L1 summary nodes, rest L2 children.
    Deliberate DQ: one orphan WBS per run (project_id references non-existent project).
    Deliberate DQ: two WBS nodes with duplicate wbs_code across projects.
    """
    n_l1 = min(8, wbs_per_project // 5)
    rows = []
    for proj in projects:
        pid = proj["project_id"]
        l1_ids = []
        for j in range(n_l1):
            wid = f"{pid}-W{j+1:02d}"
            rows.append({
                "wbs_id":        wid,
                "project_id":    pid,
                "parent_wbs_id": None,
                "wbs_code":      f"W{j+1:02d}",
                "wbs_name":      f"Phase {j+1}",
                "wbs_level":     1,
                "discipline":    rng.choice(DISCIPLINES),
                "is_summary":    True,
                "sort_order":    j * 1000,
                "modified_at":   datetime.utcnow(),
                "row_version":   1,
                "is_deleted":    False,
            })
            l1_ids.append(wid)
        n_l2 = wbs_per_project - n_l1
        for k in range(n_l2):
            wid = f"{pid}-T{k+1:03d}"
            parent = rng.choice(l1_ids)
            rows.append({
                "wbs_id":        wid,
                "project_id":    pid,
                "parent_wbs_id": parent,
                "wbs_code":      f"T{k+1:03d}",
                "wbs_name":      f"Task {k+1} - {rng.choice(DISCIPLINES) or 'General'}",
                "wbs_level":     2,
                "discipline":    rng.choice(DISCIPLINES),
                "is_summary":    False,
                "sort_order":    j * 1000 + k,
                "modified_at":   datetime.utcnow(),
                "row_version":   1,
                "is_deleted":    False,
            })
    # DQ: orphan WBS (project_id does not exist in dim_project)
    rows.append({
        "wbs_id":        "ORPHAN-WBS-999",
        "project_id":    "P999",  # non-existent
        "parent_wbs_id": None,
        "wbs_code":      "ORPHAN",
        "wbs_name":      "Orphan Task - DQ Test",
        "wbs_level":     1,
        "discipline":    None,
        "is_summary":    False,
        "sort_order":    99999,
        "modified_at":   datetime.utcnow(),
        "row_version":   1,
        "is_deleted":    False,
    })
    return rows


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------
def gen_employees(n: int) -> list[dict]:
    """Deliberate DQ: employee_id 3 has NULL email; employee_id 4 is a duplicate of 3 (late correction)."""
    rows = []
    for i in range(n):
        eid = i + 1
        rows.append({
            "employee_id":   eid,
            "employee_name": f"Emp {eid:04d}",
            "email":         None if eid == 3 else f"emp{eid:04d}@dar.demo",
            "role":          rng.choice(ROLES),
            "grade":         rng.choice(GRADES),
            "department":    rng.choice(DEPARTMENTS),
            "office_country":rng.choice(COUNTRIES),
            "hourly_rate_usd": round(rng.uniform(25.0, 200.0), 2),
            "hire_date":     START - timedelta(days=rng.randint(30, 3650)),
            "modified_at":   datetime.utcnow(),
            "row_version":   1,
            "is_deleted":    False,
        })
    return rows


# ---------------------------------------------------------------------------
# Cost codes
# ---------------------------------------------------------------------------
def gen_cost_codes() -> list[tuple]:
    rows = []
    for cc, desc, cat, bill in COST_CODES:
        rows.append((cc, desc, cat, bill, datetime.utcnow(), 1, False))
    return rows


# ---------------------------------------------------------------------------
# Fact budget
# ---------------------------------------------------------------------------
def gen_budgets(wbs_rows: list[dict]) -> list[dict]:
    """
    One budget entry per leaf WBS node per primary cost code.
    DQ: WBS node 'P001-T002' gets two rows with different currencies (USD + EUR).
    """
    rows = []
    bid = 1
    leaf_wbs = [w for w in wbs_rows if not w["is_summary"] and w["project_id"] != "P999"]
    for wbs in leaf_wbs:
        cc = rng.choice(["LABOR", "MATERIAL", "SUBCONTRACT"])
        amount = round(rng.uniform(5000, 500000), 2)
        rows.append({
            "budget_id":    bid,
            "wbs_id":       wbs["wbs_id"],
            "cost_code":    cc,
            "budget_amount": amount,
            "currency":     wbs.get("__currency", "USD"),
            "budget_hours": round(rng.uniform(100, 5000), 2),
            "effective_date": wbs.get("__start", START),
            "modified_at":  datetime.utcnow(),
            "row_version":  1,
            "is_deleted":   False,
        })
        bid += 1
    # DQ: currency inconsistency — pick first leaf from P001 and add EUR duplicate
    p001_leaves = [w for w in leaf_wbs if w["project_id"] == "P001"]
    if p001_leaves:
        wbs = p001_leaves[0]
        rows.append({
            "budget_id":    bid,
            "wbs_id":       wbs["wbs_id"],
            "cost_code":    "MATERIAL",
            "budget_amount": round(rng.uniform(1000, 50000), 2),
            "currency":     "EUR",   # DQ: inconsistent currency
            "budget_hours": None,
            "effective_date": None,
            "modified_at":  datetime.utcnow(),
            "row_version":  1,
            "is_deleted":   False,
        })
        bid += 1
    return rows


# ---------------------------------------------------------------------------
# Fact timesheet
# ---------------------------------------------------------------------------
def gen_timesheets(employees: list[dict], wbs_rows: list[dict],
                   n_days: int, prob: float) -> list[dict]:
    """
    Realistic: each working-day employee picks a random WBS.
    Only leaf WBS, non-deleted, with a real project.
    Capped at ~50k rows for 'small' scale.
    """
    leaf_wbs = [w["wbs_id"] for w in wbs_rows
                if not w["is_summary"] and w["project_id"] != "P999"]
    emp_ids  = [e["employee_id"] for e in employees]
    rows     = []
    tsid     = 1
    for day_offset in range(n_days):
        d = START + timedelta(days=day_offset)
        if d.weekday() >= 5:
            continue  # skip weekends
        for eid in emp_ids:
            if rng.random() > prob:
                continue
            wid = rng.choice(leaf_wbs)
            hours = round(rng.uniform(1.0, 8.0), 2)
            rows.append({
                "timesheet_id": tsid,
                "employee_id":  eid,
                "wbs_id":       wid,
                "date_id":      d,
                "hours":        hours,
                "activity_code": rng.choice(["DESIGN", "SITE", "REVIEW", "REPORT", None]),
                "is_approved":  rng.random() > 0.1,
                "approved_by":  1 if rng.random() > 0.5 else None,
                "submitted_at": datetime.combine(d, datetime.min.time()),
                "modified_at":  datetime.utcnow(),
                "row_version":  1,
                "is_deleted":   False,
            })
            tsid += 1
    # DQ: late-arriving row — future date beyond spine
    rows.append({
        "timesheet_id": tsid,
        "employee_id":  1,
        "wbs_id":       leaf_wbs[0] if leaf_wbs else "MISSING",
        "date_id":      date(2099, 12, 31),  # DQ: far-future date
        "hours":        1.0,
        "activity_code": None,
        "is_approved":  False,
        "approved_by":  None,
        "submitted_at": None,
        "modified_at":  datetime.utcnow(),
        "row_version":  1,
        "is_deleted":   False,
    })
    return rows


# ---------------------------------------------------------------------------
# Fact cost actuals
# ---------------------------------------------------------------------------
def gen_cost_actuals(wbs_rows: list[dict], n_days: int) -> list[dict]:
    leaf_wbs = [w for w in wbs_rows if not w["is_summary"] and w["project_id"] != "P999"]
    rows = []
    aid = 1
    # Sample ~20% of leaf WBS × working days
    for day_offset in range(0, n_days, 5):  # every 5 days
        d = START + timedelta(days=day_offset)
        sample = rng.sample(leaf_wbs, min(len(leaf_wbs), max(1, len(leaf_wbs) // 10)))
        for wbs in sample:
            cc = rng.choice(["LABOR", "MATERIAL", "SUBCONTRACT"])
            rows.append({
                "actual_id":    aid,
                "wbs_id":       wbs["wbs_id"],
                "cost_code":    cc,
                "date_id":      d,
                "actual_cost":  round(rng.uniform(100, 50000), 2),
                "currency":     "USD",
                "vendor_id":    f"V{rng.randint(1,50):03d}" if cc != "LABOR" else None,
                "invoice_ref":  f"INV-{rng.randint(10000,99999)}" if cc != "LABOR" else None,
                "modified_at":  datetime.utcnow(),
                "row_version":  1,
                "is_deleted":   False,
            })
            aid += 1
    return rows


# ---------------------------------------------------------------------------
# Fact EVM snapshot (weekly)
# ---------------------------------------------------------------------------
def gen_evm_snapshots(projects: list[dict], n_days: int) -> list[dict]:
    rows = []
    sid = 1
    for proj in projects:
        bac = round(rng.uniform(1_000_000, 50_000_000), 2)
        pct_cum = 0.0
        for day_offset in range(0, n_days, 7):
            d = START + timedelta(days=day_offset)
            pct_cum = min(1.0, pct_cum + rng.uniform(0.005, 0.025))
            pv = round(bac * pct_cum, 2)
            pct_actual = pct_cum * rng.uniform(0.85, 1.15)
            ev = round(bac * min(1.0, pct_actual), 2)
            ac = round(ev * rng.uniform(0.90, 1.20), 2)
            sv = round(ev - pv, 2)
            cv = round(ev - ac, 2)
            spi = round(ev / pv, 4) if pv > 0 else 1.0
            cpi = round(ev / ac, 4) if ac > 0 else 1.0
            eac = round(bac / cpi, 2) if cpi > 0 else bac
            rows.append({
                "snapshot_id":           sid,
                "project_id":            proj["project_id"],
                "date_id":               d,
                "planned_value":         pv,
                "earned_value":          ev,
                "actual_cost":           ac,
                "budget_at_completion":  bac,
                "estimate_at_completion": eac,
                "schedule_variance":     sv,
                "cost_variance":         cv,
                "spi":                   spi,
                "cpi":                   cpi,
                "percent_complete":      round(pct_actual * 100, 2),
                "modified_at":           datetime.utcnow(),
                "row_version":           1,
                "is_deleted":            False,
            })
            sid += 1
    return rows


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------
def upsert_calendar(cur, rows):
    execute_values(cur, """
        INSERT INTO warehouse.dim_calendar
            (date_id, year, quarter, month, month_name, day, day_of_week, day_name,
             week_of_year, is_weekend, is_holiday, fiscal_year, fiscal_quarter)
        VALUES %s
        ON CONFLICT (date_id) DO NOTHING
    """, rows)


def upsert_projects(cur, projects):
    execute_values(cur, """
        INSERT INTO warehouse.dim_project
            (project_id, project_name, client_name, project_type, country, currency,
             status, start_date, planned_end_date, actual_end_date, pm_employee_id,
             modified_at, row_version, is_deleted)
        VALUES %s
        ON CONFLICT (project_id) DO UPDATE SET
            project_name = EXCLUDED.project_name,
            status       = EXCLUDED.status,
            modified_at  = EXCLUDED.modified_at,
            row_version  = EXCLUDED.row_version
    """, [(p["project_id"], p["project_name"], p["client_name"], p["project_type"],
           p["country"], p["currency"], p["status"], p["start_date"],
           p["planned_end_date"], p["actual_end_date"], p["pm_employee_id"],
           p["modified_at"], p["row_version"], p["is_deleted"]) for p in projects])


def upsert_wbs(cur, wbs_rows):
    execute_values(cur, """
        INSERT INTO warehouse.dim_wbs
            (wbs_id, project_id, parent_wbs_id, wbs_code, wbs_name, wbs_level,
             discipline, is_summary, sort_order, modified_at, row_version, is_deleted)
        VALUES %s
        ON CONFLICT (wbs_id) DO NOTHING
    """, [(w["wbs_id"], w["project_id"], w["parent_wbs_id"], w["wbs_code"],
           w["wbs_name"], w["wbs_level"], w["discipline"], w["is_summary"],
           w["sort_order"], w["modified_at"], w["row_version"], w["is_deleted"])
          for w in wbs_rows])


def upsert_employees(cur, employees):
    execute_values(cur, """
        INSERT INTO warehouse.dim_employee
            (employee_id, employee_name, email, role, grade, department,
             office_country, hourly_rate_usd, hire_date, modified_at, row_version, is_deleted)
        VALUES %s
        ON CONFLICT (employee_id) DO NOTHING
    """, [(e["employee_id"], e["employee_name"], e["email"], e["role"], e["grade"],
           e["department"], e["office_country"], e["hourly_rate_usd"], e["hire_date"],
           e["modified_at"], e["row_version"], e["is_deleted"]) for e in employees])


def insert_cost_codes(cur, rows):
    execute_values(cur, """
        INSERT INTO warehouse.dim_cost_code
            (cost_code, description, category, is_billable, modified_at, row_version, is_deleted)
        VALUES %s
        ON CONFLICT (cost_code) DO NOTHING
    """, rows)


def insert_budgets(cur, budgets):
    execute_values(cur, """
        INSERT INTO warehouse.fact_budget
            (wbs_id, cost_code, budget_amount, currency, budget_hours,
             effective_date, modified_at, row_version, is_deleted)
        VALUES %s
    """, [(b["wbs_id"], b["cost_code"], b["budget_amount"], b["currency"],
           b["budget_hours"], b["effective_date"], b["modified_at"],
           b["row_version"], b["is_deleted"]) for b in budgets])


def insert_timesheets(cur, timesheets):
    execute_values(cur, """
        INSERT INTO warehouse.fact_timesheet
            (employee_id, wbs_id, date_id, hours, activity_code, is_approved,
             approved_by, submitted_at, modified_at, row_version, is_deleted)
        VALUES %s
    """, [(t["employee_id"], t["wbs_id"], t["date_id"], t["hours"],
           t["activity_code"], t["is_approved"], t["approved_by"],
           t["submitted_at"], t["modified_at"], t["row_version"], t["is_deleted"])
          for t in timesheets])


def insert_cost_actuals(cur, actuals):
    execute_values(cur, """
        INSERT INTO warehouse.fact_cost_actuals
            (wbs_id, cost_code, date_id, actual_cost, currency,
             vendor_id, invoice_ref, modified_at, row_version, is_deleted)
        VALUES %s
    """, [(a["wbs_id"], a["cost_code"], a["date_id"], a["actual_cost"],
           a["currency"], a["vendor_id"], a["invoice_ref"],
           a["modified_at"], a["row_version"], a["is_deleted"])
          for a in actuals])


def insert_evm(cur, snapshots):
    execute_values(cur, """
        INSERT INTO warehouse.fact_evm_snapshot
            (project_id, date_id, planned_value, earned_value, actual_cost,
             budget_at_completion, estimate_at_completion,
             schedule_variance, cost_variance, spi, cpi, percent_complete,
             modified_at, row_version, is_deleted)
        VALUES %s
    """, [(s["project_id"], s["date_id"], s["planned_value"], s["earned_value"],
           s["actual_cost"], s["budget_at_completion"], s["estimate_at_completion"],
           s["schedule_variance"], s["cost_variance"], s["spi"], s["cpi"],
           s["percent_complete"], s["modified_at"], s["row_version"], s["is_deleted"])
          for s in snapshots])


# ---------------------------------------------------------------------------
# D365 mock JSON
# ---------------------------------------------------------------------------
def gen_d365_json(projects, wbs_rows, budgets, actuals, n_days):
    """
    Build the JSON file that the D365 FastAPI mock serves.
    Shape mirrors OData entity sets:
      /data/ProjectTransactions
      /data/Projects
      /data/WBSElements
      /data/LedgerJournalLines  (cost actuals)
      /data/BudgetLines
      /data/Vendors
    """
    ts_now = datetime.utcnow().isoformat()

    d365 = {
        "Projects": [],
        "WBSElements": [],
        "BudgetLines": [],
        "LedgerJournalLines": [],
        "Vendors": [],
    }

    for p in projects:
        d365["Projects"].append({
            "ProjectId":      p["project_id"],
            "ProjectName":    p["project_name"],
            "ClientName":     p["client_name"],
            "ProjectType":    p["project_type"],
            "CountryRegion":  p["country"],
            "CurrencyCode":   p["currency"],
            "Status":         p["status"],
            "StartDate":      p["start_date"].isoformat() if p["start_date"] else None,
            "PlannedEndDate": p["planned_end_date"].isoformat() if p["planned_end_date"] else None,
            "ModifiedAt":     ts_now,
            "RowVersion":     1,
            "_op":            "I",
        })

    for w in wbs_rows:
        d365["WBSElements"].append({
            "WBSId":        w["wbs_id"],
            "ProjectId":    w["project_id"],
            "ParentWBSId":  w["parent_wbs_id"],
            "WBSCode":      w["wbs_code"],
            "WBSName":      w["wbs_name"],
            "WBSLevel":     w["wbs_level"],
            "Discipline":   w["discipline"],
            "IsSummary":    w["is_summary"],
            "ModifiedAt":   ts_now,
            "RowVersion":   1,
            "_op":          "I",
        })

    for b in budgets:
        d365["BudgetLines"].append({
            "BudgetId":      b["budget_id"],
            "WBSId":         b["wbs_id"],
            "CostCode":      b["cost_code"],
            "BudgetAmount":  float(b["budget_amount"]),
            "Currency":      b["currency"],
            "BudgetHours":   float(b["budget_hours"]) if b["budget_hours"] else None,
            "ModifiedAt":    ts_now,
            "RowVersion":    1,
            "_op":           "I",
        })

    for a in actuals:
        d365["LedgerJournalLines"].append({
            "ActualId":    a["actual_id"],
            "WBSId":       a["wbs_id"],
            "CostCode":    a["cost_code"],
            "TransDate":   a["date_id"].isoformat(),
            "Amount":      float(a["actual_cost"]),
            "Currency":    a["currency"],
            "VendorId":    a["vendor_id"],
            "InvoiceRef":  a["invoice_ref"],
            "ModifiedAt":  ts_now,
            "RowVersion":  1,
            "_op":         "I",
        })

    # Stub vendors
    for i in range(1, 51):
        d365["Vendors"].append({
            "VendorId":   f"V{i:03d}",
            "VendorName": f"Vendor {i}",
            "Country":    rng.choice(COUNTRIES),
            "ModifiedAt": ts_now,
            "_op":        "I",
        })

    return d365


# ---------------------------------------------------------------------------
# SharePoint mock JSON
# ---------------------------------------------------------------------------
def gen_sharepoint_json(projects, n_docs_per_project=5):
    ts_now = datetime.utcnow().isoformat()
    sp = {
        "DriveItems": [],
        "ListItems": {
            "StatusUpdates": [],
            "RiskRegister":  [],
            "ChangeRequests": [],
        },
    }
    for proj in projects:
        pid = proj["project_id"]
        for j in range(n_docs_per_project):
            item_id = str(uuid.UUID(int=rng.getrandbits(128)))
            sp["DriveItems"].append({
                "id":                    item_id,
                "name":                  f"{pid}_Spec_v{j+1}.docx",
                "projectId":             pid,
                "webUrl":                f"https://dar.sharepoint.example/{pid}/{item_id}",
                "size":                  rng.randint(10000, 5_000_000),
                "mimeType":              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "lastModifiedDateTime":  ts_now,
                "_op":                   "I",
            })
        # Status update
        sp["ListItems"]["StatusUpdates"].append({
            "id":           str(uuid.UUID(int=rng.getrandbits(128))),
            "projectId":    pid,
            "status":       proj["status"],
            "reportDate":   START.isoformat(),
            "narrative":    f"Project {pid} status report",
            "lastModifiedDateTime": ts_now,
            "_op":          "I",
        })
        # Risk
        sp["ListItems"]["RiskRegister"].append({
            "id":           str(uuid.UUID(int=rng.getrandbits(128))),
            "projectId":    pid,
            "riskTitle":    f"Schedule risk {pid}",
            "probability":  rng.choice(["Low", "Medium", "High"]),
            "impact":       rng.choice(["Low", "Medium", "High"]),
            "lastModifiedDateTime": ts_now,
            "_op":          "I",
        })

    return sp


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Seed DAR_DW, D365 mock, SharePoint mock")
    parser.add_argument("--scale", choices=["small", "bench"], default="small")
    args = parser.parse_args()

    cfg = SCALES[args.scale]
    print(f"=== DAR_DW seed (scale={args.scale}, random_seed={SEED}) ===")
    print(f"    projects={cfg['n_projects']}, wbs/proj={cfg['wbs_per_project']}, "
          f"employees={cfg['n_employees']}, days={cfg['timesheet_days']}")

    # ---- Generate data ----
    print("Generating calendar...")
    calendar_rows  = gen_calendar(cfg["timesheet_days"] + 30)

    print("Generating projects...")
    projects       = gen_projects(cfg["n_projects"])

    print("Generating WBS...")
    wbs_rows       = gen_wbs(projects, cfg["wbs_per_project"])

    print("Generating employees...")
    employees      = gen_employees(cfg["n_employees"])

    cost_code_rows = gen_cost_codes()

    print("Generating budgets...")
    budgets        = gen_budgets(wbs_rows)

    print(f"Generating timesheets (prob={cfg['timesheet_prob']})...")
    timesheets     = gen_timesheets(employees, wbs_rows,
                                    cfg["timesheet_days"], cfg["timesheet_prob"])

    print("Generating cost actuals...")
    actuals        = gen_cost_actuals(wbs_rows, cfg["timesheet_days"])

    print("Generating EVM snapshots...")
    evm_snapshots  = gen_evm_snapshots(projects, cfg["timesheet_days"])

    print(f"  calendar={len(calendar_rows)}, projects={len(projects)}, wbs={len(wbs_rows)}, "
          f"employees={len(employees)}, budgets={len(budgets)}, "
          f"timesheets={len(timesheets)}, actuals={len(actuals)}, evm={len(evm_snapshots)}")

    # ---- Write to PostgreSQL ----
    print("Connecting to dar-postgres-dw (container hostname)...")
    conn = psycopg2.connect(
        host=os.environ.get("PG_DW_HOST", "dar-postgres-dw"),
        port=int(os.environ.get("PG_DW_INTERNAL_PORT", "5432")),
        user=os.environ.get("PG_DW_SA_USER", "dar_dw_admin"),
        password=os.environ.get("PG_DW_SA_PASSWORD", "CHANGE_ME_DW_ADMIN"),
        database=os.environ.get("PG_DW_DB", "DAR_DW"),
    )
    cur = conn.cursor()

    print("Truncating existing tables to ensure idempotency...")
    cur.execute("""
        TRUNCATE TABLE
            warehouse.fact_timesheet,
            warehouse.fact_cost_actuals,
            warehouse.fact_budget,
            warehouse.fact_evm_snapshot,
            warehouse.dim_wbs,
            warehouse.dim_project,
            warehouse.dim_employee,
            warehouse.dim_cost_code,
            warehouse.dim_calendar
        RESTART IDENTITY CASCADE;
    """)

    print("Inserting calendar...")
    upsert_calendar(cur, calendar_rows)

    print("Inserting employees...")
    upsert_employees(cur, employees)

    print("Inserting projects...")
    upsert_projects(cur, projects)

    print("Inserting WBS...")
    upsert_wbs(cur, wbs_rows)

    print("Inserting cost codes...")
    insert_cost_codes(cur, cost_code_rows)

    print("Inserting budgets...")
    insert_budgets(cur, budgets)

    print("Inserting timesheets...")
    insert_timesheets(cur, timesheets)

    print("Inserting cost actuals...")
    insert_cost_actuals(cur, actuals)

    print("Inserting EVM snapshots...")
    insert_evm(cur, evm_snapshots)

    conn.commit()
    cur.close()
    conn.close()
    print("PostgreSQL seed complete.")

    # ---- Write D365 mock JSON ----
    # The file is inside the container at /repo/... We write relative to __file__
    d365_path = os.path.join(os.path.dirname(__file__),
                             "..", "d365_mock", "data.json")
    d365_path = os.path.normpath(d365_path)
    print(f"Writing D365 mock JSON -> {d365_path}")
    d365_data = gen_d365_json(projects, wbs_rows, budgets, actuals, cfg["timesheet_days"])
    with open(d365_path, "w") as f:
        json.dump(d365_data, f, default=str, indent=2)
    print(f"  D365: projects={len(d365_data['Projects'])}, wbs={len(d365_data['WBSElements'])}, "
          f"budgets={len(d365_data['BudgetLines'])}, actuals={len(d365_data['LedgerJournalLines'])}")

    # ---- Write SharePoint mock JSON ----
    sp_path = os.path.join(os.path.dirname(__file__),
                           "..", "sharepoint_mock", "data.json")
    sp_path = os.path.normpath(sp_path)
    print(f"Writing SharePoint mock JSON -> {sp_path}")
    sp_data = gen_sharepoint_json(projects)
    with open(sp_path, "w") as f:
        json.dump(sp_data, f, default=str, indent=2)
    print(f"  SP: driveItems={len(sp_data['DriveItems'])}, "
          f"statusUpdates={len(sp_data['ListItems']['StatusUpdates'])}")

    print("=== Seed complete ===")


if __name__ == "__main__":
    main()
