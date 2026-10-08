{{ config(materialized='incremental', incremental_strategy='append') }}
WITH duplicate_keys AS (
    SELECT timesheet_id FROM {{ source('bronze', 'pg_fact_timesheet') }}
    GROUP BY timesheet_id HAVING COUNT(*) > 1
)
SELECT a.*, 'Duplicate / CDC History' AS quarantine_reason
FROM {{ source('bronze', 'pg_fact_timesheet') }} a
JOIN duplicate_keys b ON a.timesheet_id = b.timesheet_id
{% if is_incremental() %} WHERE a.modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
