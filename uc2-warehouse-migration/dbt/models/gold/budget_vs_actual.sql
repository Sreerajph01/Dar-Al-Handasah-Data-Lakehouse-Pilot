{{ config(materialized='table') }}
SELECT
    b.wbs_id,
    CAST(SUM(b.amount) AS DECIMAL(18, 4)) AS total_budget,
    b.currency
FROM {{ ref('fact_budget') }} b
GROUP BY b.wbs_id, b.currency
