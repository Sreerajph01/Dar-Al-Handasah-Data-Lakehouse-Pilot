{{ config(materialized='table') }}
SELECT
    wbs_id,
    CAST(amount AS double) AS amount,
    currency,
    modified_at
FROM {{ ref('fact_budget') }}
