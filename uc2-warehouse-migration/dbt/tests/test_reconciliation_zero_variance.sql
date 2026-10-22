-- ============================================================
-- test_reconciliation_zero_variance.sql
-- Fails if source-to-target financial difference exceeds 0.01 USD
-- or if is_within_tolerance is false.
-- ============================================================
SELECT
    source_total,
    gold_total,
    quarantine_total,
    reconciled_total,
    difference,
    is_within_tolerance
FROM {{ ref('reconciliation') }}
WHERE is_within_tolerance = FALSE OR difference >= 0.01
