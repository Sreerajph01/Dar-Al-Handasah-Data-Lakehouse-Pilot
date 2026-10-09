{{ config(materialized='table') }}
SELECT
    w.wbs_id,
    w.wbs_code,
    w.wbs_name,
    w.project_id,
    w.discipline
FROM {{ ref('dim_wbs') }} w
WHERE w.is_current = TRUE
