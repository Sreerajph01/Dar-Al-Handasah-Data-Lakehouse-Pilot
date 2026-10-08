{{ config(materialized='table') }}
WITH source_budget AS (
    SELECT SUM(CAST(amount AS double)) AS source_total FROM postgresql.public.fact_budget
),
gold_budget AS (
    SELECT SUM(total_budget) AS gold_total FROM {{ ref('budget_vs_actual') }}
)
SELECT
    source_total,
    gold_total,
    ABS(source_total - gold_total) AS difference,
    CASE WHEN ABS(source_total - gold_total) < 0.01 THEN TRUE ELSE FALSE END AS is_within_tolerance
FROM source_budget, gold_budget
