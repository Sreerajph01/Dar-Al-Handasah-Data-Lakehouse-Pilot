{{ config(materialized='table') }}
SELECT
    p.project_id,
    p.project_name,
    p.client_name,
    p.project_type,
    p.country,
    p.currency,
    p.status,
    p.start_date,
    p.planned_end_date
FROM {{ ref('dim_project') }} p
WHERE p.is_current = TRUE
