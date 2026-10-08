{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['project_id', 'valid_from']
) }}

WITH cdc_events AS (
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
        is_deleted
    FROM {{ source('bronze', 'pg_dim_project') }}
    WHERE project_name IS NOT NULL
    {% if is_incremental() %}
      AND modified_at > (SELECT coalesce(MAX(valid_from), '1970-01-01T00:00:00Z') FROM {{ this }})
    {% endif %}
),
{% if is_incremental() %}
affected_projects AS (
    SELECT DISTINCT project_id FROM cdc_events
),
existing_active_rows AS (
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
        valid_from AS modified_at,
        is_deleted
    FROM {{ this }}
    WHERE project_id IN (SELECT project_id FROM affected_projects)
      AND is_current = TRUE
),
combined_events AS (
    SELECT * FROM existing_active_rows
    UNION ALL
    SELECT * FROM cdc_events
)
{% else %}
combined_events AS (
    SELECT * FROM cdc_events
)
{% endif %}
,
scd2 AS (
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
        modified_at AS valid_from,
        LEAD(modified_at) OVER (PARTITION BY project_id ORDER BY modified_at) AS valid_to,
        CASE WHEN LEAD(modified_at) OVER (PARTITION BY project_id ORDER BY modified_at) IS NULL THEN TRUE ELSE FALSE END AS is_current,
        is_deleted
    FROM combined_events
)
SELECT * FROM scd2
