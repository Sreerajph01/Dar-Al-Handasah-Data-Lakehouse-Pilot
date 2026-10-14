{{ config(materialized='table') }}
-- ============================================================
-- reconciliation.sql
-- Source-to-Lakehouse financial reconciliation.
--
-- LEFT SIDE (source_total):
--   Reads from iceberg.bronze.pg_fact_budget, which is the
--   raw copy of the PostgreSQL DW ingested via dlt.
--   Applies FX normalisation to USD (same as Silver pipeline).
--   Excludes logically deleted rows (is_deleted = 'true').
--
-- RIGHT SIDE (gold_total):
--   Reads from gold.budget_vs_actual (aggregated Silver output)
--
-- QUARANTINE SIDE:
--   Rows that Silver rejected due to invalid currency codes.
--   These should appear in neither Gold nor FX-normalised Bronze.
--
-- Invariant:
--   bronze_fx_total ≈ gold_total + quarantine_total
--   difference < 0.01 (USD) means the pipeline is lossless
-- ============================================================
WITH fx AS (
    SELECT currency, CAST(rate_to_usd AS double) AS rate
    FROM {{ ref('fx_rates') }}
),

-- Bronze = raw copy of source DW; apply FX normalisation
-- Exclude deleted rows; rows with unknown currency go to quarantine
bronze_known_currency AS (
    SELECT
        b.budget_id,
        CAST(b.budget_amount AS double) * fx.rate AS amount_usd
    FROM {{ source('bronze', 'pg_fact_budget') }} b
    JOIN fx ON UPPER(b.currency) = fx.currency
    WHERE b.is_deleted <> 'true'
      AND b._op <> 'D'
),

bronze_unknown_currency AS (
    SELECT COUNT(*) AS quarantine_count,
           COALESCE(SUM(CAST(budget_amount AS double)), 0.0) AS quarantine_raw
    FROM {{ source('bronze', 'pg_fact_budget') }} b
    LEFT JOIN fx ON UPPER(b.currency) = fx.currency
    WHERE fx.currency IS NULL
      AND (b.is_deleted <> 'true' AND b._op <> 'D')
),

source_agg AS (
    SELECT COALESCE(SUM(amount_usd), 0.0) AS bronze_total
    FROM bronze_known_currency
),

gold_agg AS (
    SELECT COALESCE(SUM(CAST(total_budget AS double)), 0.0) AS gold_total
    FROM {{ ref('budget_vs_actual') }}
),

combined AS (
    SELECT
        s.bronze_total                                    AS source_total,
        g.gold_total,
        q.quarantine_count,
        q.quarantine_raw,
        ABS(s.bronze_total - g.gold_total)               AS difference,
        s.bronze_total,
        g.gold_total                                      AS reconciled_total
    FROM source_agg s, gold_agg g, bronze_unknown_currency q
)
SELECT
    source_total,
    gold_total,
    quarantine_count,
    quarantine_raw                                            AS quarantine_total,
    reconciled_total,
    difference,
    CASE WHEN difference < 0.01 THEN TRUE ELSE FALSE END     AS is_within_tolerance,
    CURRENT_TIMESTAMP                                         AS reconciled_at
FROM combined
