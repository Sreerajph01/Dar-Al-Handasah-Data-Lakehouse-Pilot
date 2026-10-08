{{ config(materialized='table') }}
SELECT
    project_id,
    wbs_id,
    amount,
    currency,
    modified_at
FROM {{ ref('fact_budget') }}
