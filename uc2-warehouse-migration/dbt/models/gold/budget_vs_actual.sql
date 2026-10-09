{{ config(materialized='table') }}
SELECT
    b.wbs_id,
    SUM(b.amount) AS total_budget,
    b.currency
FROM {{ ref('fact_budget') }} b
GROUP BY b.wbs_id, b.currency
