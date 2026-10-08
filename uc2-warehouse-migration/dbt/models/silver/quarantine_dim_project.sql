{{ config(
    materialized='incremental',
    incremental_strategy='append'
) }}

SELECT
    project_id,
    project_name,
    client_name,
    project_type,
    country,
    currency,
    status,
    start_date,
    planned_end_date,
    actual_end_date,
    pm_employee_id,
    modified_at,
    is_deleted,
    'Project Name is NULL' AS quarantine_reason
FROM {{ source('bronze', 'pg_dim_project') }}
WHERE project_name IS NULL
{% if is_incremental() %}
  AND modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }})
{% endif %}
