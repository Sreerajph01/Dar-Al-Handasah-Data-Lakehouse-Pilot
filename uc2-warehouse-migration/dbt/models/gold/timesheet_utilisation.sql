{{ config(materialized='table') }}
SELECT
    t.employee_id,
    t.wbs_id,
    SUM(CAST(t.hours AS double)) AS total_hours
FROM {{ ref('fact_timesheet') }} t
GROUP BY t.employee_id, t.wbs_id
