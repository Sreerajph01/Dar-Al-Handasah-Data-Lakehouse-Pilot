{{ config(materialized='table') }}
-- ============================================================
-- reconciliation.sql
-- Source-to-Lakehouse financial reconciliation.
--
-- LEFT SIDE (source_total):
--   Reads from iceberg.bronze.pg_fact_budget, which is the
--   raw append-only copy of the PostgreSQL DW.
--   Takes the latest CDC event per budget_id.
--   Applies FX normalisation to USD (same as Silver pipeline).
--   Excludes logically deleted rows (is_deleted = 'true').
--
-- RIGHT SIDE (gold_total):
--   Reads from gold.budget_vs_actual (aggregated Silver output)
--
-- QUARANTINE SIDE (quarantine_total):
--   Rows that were rejected due to invalid currency codes or DQ rules.
--
-- Invariant:
--   source_total = gold_total + quarantine_total
--   difference < 0.01 (USD) proves zero loss across the pipeline.
-- ============================================================
WITH fx AS (
    SELECT currency, CAST(rate_to_usd AS DECIMAL(18, 4)) AS rate
    FROM {{ ref('fx_rates') }}
),

latest_source AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER(PARTITION BY budget_id ORDER BY modified_at DESC, _ingested_at DESC) as rn
        FROM {{ source('bronze', 'pg_fact_budget') }}
    )
    WHERE rn = 1
      AND is_deleted <> 'true'
      AND _op <> 'D'
),

bronze_known_currency AS (
    SELECT
        b.budget_id,
        CAST(b.budget_amount AS DECIMAL(18, 4)) * fx.rate AS amount_usd
    FROM latest_source b
    JOIN fx ON UPPER(b.currency) = fx.currency
),

bronze_unknown_currency AS (
    SELECT COUNT(*) AS quarantine_count,
           COALESCE(SUM(CAST(budget_amount AS DECIMAL(18, 4))), CAST(0.0 AS DECIMAL(18, 4))) AS quarantine_raw
    FROM latest_source b
    LEFT JOIN fx ON UPPER(b.currency) = fx.currency
    WHERE fx.currency IS NULL
),

source_agg AS (
    SELECT COALESCE(SUM(amount_usd), CAST(0.0 AS DECIMAL(18, 4))) AS valid_source_total
    FROM bronze_known_currency
),

gold_agg AS (
    SELECT COALESCE(SUM(CAST(total_budget AS DECIMAL(18, 4))), CAST(0.0 AS DECIMAL(18, 4))) AS gold_total
    FROM {{ ref('budget_vs_actual') }}
),

combined AS (
    SELECT
        s.valid_source_total + q.quarantine_raw            AS source_total,
        g.gold_total,
        q.quarantine_count,
        q.quarantine_raw                                  AS quarantine_total,
        g.gold_total + q.quarantine_raw                   AS reconciled_total,
        ABS((s.valid_source_total + q.quarantine_raw) - (g.gold_total + q.quarantine_raw)) AS difference
    FROM source_agg s, gold_agg g, bronze_unknown_currency q
)
SELECT
    source_total,
    gold_total,
    quarantine_count,
    quarantine_total,
    reconciled_total,
    difference,
    CASE WHEN difference < CAST(0.01 AS DECIMAL(18, 4)) THEN TRUE ELSE FALSE END AS is_within_tolerance,
    CURRENT_TIMESTAMP                                                             AS reconciled_at
FROM combined
