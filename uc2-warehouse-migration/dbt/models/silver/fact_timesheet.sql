{{ config(materialized='incremental', incremental_strategy='merge', unique_key='timesheet_id') }}
WITH cdc_events AS (
    SELECT * FROM {{ source('bronze', 'pg_fact_timesheet') }}
    {% if is_incremental() %} WHERE modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY timesheet_id ORDER BY modified_at DESC) as rn
    FROM cdc_events
)
SELECT timesheet_id, employee_id, wbs_id, date_id, hours, activity_code, is_approved, approved_by, submitted_at, modified_at, is_deleted
FROM ranked WHERE rn = 1
