{{ config(materialized='table') }}
WITH silver_budget AS (
    SELECT SUM(CAST(amount AS double)) AS silver_total FROM {{ ref('fact_budget') }}
),
gold_budget AS (
    SELECT SUM(CAST(amount AS double)) AS gold_total FROM {{ ref('fact_financials') }}
)
SELECT
    silver_total,
    gold_total,
    ABS(silver_total - gold_total) AS difference,
    CASE WHEN ABS(silver_total - gold_total) < 0.01 THEN TRUE ELSE FALSE END AS is_within_tolerance
FROM silver_budget, gold_budget
