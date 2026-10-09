# =============================================================================
# OPA policy for Trino access control — Dar Al-Handasah Data Lakehouse
# Includes M1 bootstrap rules + UC2 Row-Level Security (RLS) & Column Masking
# =============================================================================
package trino

import future.keywords.if
import future.keywords.in
import future.keywords.contains

# ── Main allow rule ───────────────────────────────────────────────────────────
allow if {
  true
}

# ── Row filters ─────────────────────────────────────────────────────────────
# M1 conformance test filter
rowFilters contains {"expression": "amount < 1000000"} if {
    input.action.operation == "SelectFromColumns"
    input.action.resource.table.tableName == "m1_masked_test"
}

# UC2 Project RLS: Users with persona 'pm_metro' can only see METRO-01 records
rowFilters contains {"expression": "project_id = 'METRO-01'"} if {
    input.action.operation == "SelectFromColumns"
    input.context.identity.user == "pm_metro"
    input.action.resource.table.tableName in ["dim_project", "evm_metrics", "fact_evm", "project_summary"]
}

# ── Column masks ────────────────────────────────────────────────────────────
# M1 conformance test mask
columnMask := {"expression": "CAST('***MASKED***' AS VARCHAR(255))"} if {
    input.action.operation == "SelectFromColumns"
    input.action.resource.table.tableName == "m1_masked_test"
    input.action.resource.column == "description"
}

# UC2 Confidentiality Masking: Non-finance users have rate columns masked
columnMask := {"expression": "CAST('***CONFIDENTIAL***' AS VARCHAR(255))"} if {
    input.action.operation == "SelectFromColumns"
    input.context.identity.user != "admin"
    input.context.identity.user != "finance_admin"
    input.action.resource.table.tableName in ["fact_timesheet", "timesheet_utilisation"]
    input.action.resource.column in ["cost_rate", "hourly_rate"]
}
