# =============================================================================
# OPA policy for Trino access control — Bootstrap (OPEN, dev mode)
# M1: Allow all for service account; real RBAC added in M5.
# =============================================================================
package trino

import future.keywords.if
import future.keywords.in
import future.keywords.contains

# ── Main allow rule ───────────────────────────────────────────────────────────
# In dev mode, allow everything. M5 will replace this with persona-based rules.
allow if {
  true
}

# ── Row filters ─────────────────────────────────────────────────────────────
rowFilters contains {"expression": "amount < 1000000"} if {
    input.action.operation == "SelectFromColumns"
    input.action.resource.table.tableName == "m1_masked_test"
}

# ── Column masks ────────────────────────────────────────────────────────────
columnMask := {"expression": "CAST('***MASKED***' AS VARCHAR(255))"} if {
    input.action.operation == "SelectFromColumns"
    input.action.resource.table.tableName == "m1_masked_test"
    input.action.resource.column == "description"
}
