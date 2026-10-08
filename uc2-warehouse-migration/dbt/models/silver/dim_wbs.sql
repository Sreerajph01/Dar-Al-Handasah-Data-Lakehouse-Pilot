{{ config(materialized='incremental', incremental_strategy='merge', unique_key=['wbs_id', 'valid_from']) }}
WITH cdc_events AS (
    SELECT wbs_id, project_id, parent_wbs_id, wbs_code, wbs_name, wbs_level, discipline, is_summary, sort_order, modified_at, is_deleted
    FROM {{ source('bronze', 'pg_dim_wbs') }}
    -- Filter out orphan WBS (where project_id does not exist in dim_project)
    WHERE project_id IN (SELECT project_id FROM {{ source('bronze', 'pg_dim_project') }})
    {% if is_incremental() %}
      AND modified_at > (SELECT coalesce(MAX(valid_from), '1970-01-01T00:00:00Z') FROM {{ this }})
    {% endif %}
),
{% if is_incremental() %}
affected AS ( SELECT DISTINCT wbs_id FROM cdc_events ),
existing AS ( SELECT wbs_id, project_id, parent_wbs_id, wbs_code, wbs_name, wbs_level, discipline, is_summary, sort_order, valid_from AS modified_at, is_deleted FROM {{ this }} WHERE wbs_id IN (SELECT wbs_id FROM affected) AND is_current = TRUE ),
combined AS ( SELECT * FROM existing UNION ALL SELECT * FROM cdc_events )
{% else %}
combined AS ( SELECT * FROM cdc_events )
{% endif %},
scd2 AS (
    SELECT *, modified_at AS valid_from, LEAD(modified_at) OVER (PARTITION BY wbs_id ORDER BY modified_at) AS valid_to,
    CASE WHEN LEAD(modified_at) OVER (PARTITION BY wbs_id ORDER BY modified_at) IS NULL THEN TRUE ELSE FALSE END AS is_current
    FROM combined
)
SELECT * FROM scd2
