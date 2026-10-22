{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='employee_id'
) }}

WITH cdc_events AS (
    SELECT * FROM {{ source('bronze', 'pg_dim_employee') }}
    {% if is_incremental() %}
    WHERE modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }})
    {% endif %}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY employee_id ORDER BY modified_at DESC) as rn
    FROM cdc_events
)
SELECT
    employee_id,
    employee_name,
    email,
    role,
    grade,
    department,
    office_country,
    CAST(hourly_rate_usd AS DECIMAL(18, 4)) AS hourly_rate_usd,
    hire_date,
    modified_at,
    CAST(row_version AS INTEGER) AS row_version,
    CAST(is_deleted AS BOOLEAN) AS is_deleted
FROM ranked
WHERE rn = 1
