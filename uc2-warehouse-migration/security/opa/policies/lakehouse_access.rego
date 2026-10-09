# =============================================================================
# uc2-warehouse-migration/security/opa/policies/lakehouse_access.rego
# Fine-Grained Access Control (RLS & Column Masking) for Dar Al-Handasah
# =============================================================================
package trino

import future.keywords.if
import future.keywords.in
import future.keywords.contains

# ── Dynamic Project Row Filter ─────────────────────────────────────────────
# Enforces that project managers with role 'pm_metro' can only see METRO-01 data
rowFilters contains {"expression": "project_id = 'METRO-01'"} if {
    input.action.operation == "SelectFromColumns"
    input.context.identity.user == "pm_metro"
    input.action.resource.table.tableName in ["dim_project", "evm_metrics", "fact_evm", "project_summary"]
}

# ── Financial / Salary Column Masking ──────────────────────────────────────
# Masks confidential cost and rate figures for general users
columnMask := {"expression": "CAST('***CONFIDENTIAL***' AS VARCHAR(255))"} if {
    input.action.operation == "SelectFromColumns"
    input.context.identity.user != "admin"
    input.context.identity.user != "finance_admin"
    input.action.resource.table.tableName in ["fact_timesheet", "timesheet_utilisation"]
    input.action.resource.column in ["cost_rate", "hourly_rate", "rate"]
}
