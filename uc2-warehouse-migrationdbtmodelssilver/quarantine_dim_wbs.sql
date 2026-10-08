{{ config(materialized='incremental', incremental_strategy='append') }}
SELECT *, 'Orphan WBS' AS quarantine_reason FROM {{ source('bronze', 'pg_dim_wbs') }}
WHERE project_id NOT IN (SELECT project_id FROM {{ source('bronze', 'pg_dim_project') }})
{% if is_incremental() %} AND modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
