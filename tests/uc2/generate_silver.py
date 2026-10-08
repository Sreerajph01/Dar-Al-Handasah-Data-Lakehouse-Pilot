import os

silver_dir = "uc2-warehouse-migration/dbt/models/silver"
os.makedirs(silver_dir, exist_ok=True)

models = {
    "dim_wbs": """{{ config(materialized='incremental', incremental_strategy='merge', unique_key=['wbs_id', 'valid_from']) }}
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
""",
    "quarantine_dim_wbs": """{{ config(materialized='incremental', incremental_strategy='append') }}
SELECT *, 'Orphan WBS' AS quarantine_reason FROM {{ source('bronze', 'pg_dim_wbs') }}
WHERE project_id NOT IN (SELECT project_id FROM {{ source('bronze', 'pg_dim_project') }})
{% if is_incremental() %} AND modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
""",
    "fact_budget": """{{ config(materialized='incremental', incremental_strategy='merge', unique_key='budget_id') }}
WITH cdc_events AS (
    SELECT * FROM {{ source('bronze', 'pg_fact_budget') }}
    WHERE currency = 'USD'
    {% if is_incremental() %} AND modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY budget_id ORDER BY modified_at DESC) as rn
    FROM cdc_events
)
SELECT budget_id, wbs_id, budget_amount AS amount, currency, modified_at, is_deleted
FROM ranked WHERE rn = 1
""",
    "quarantine_fact_budget": """{{ config(materialized='incremental', incremental_strategy='append') }}
SELECT *, 'Non-USD Currency' AS quarantine_reason FROM {{ source('bronze', 'pg_fact_budget') }}
WHERE currency != 'USD'
{% if is_incremental() %} AND modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
""",
    "fact_timesheet": """{{ config(materialized='incremental', incremental_strategy='merge', unique_key='timesheet_id') }}
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
""",
    "quarantine_fact_timesheet": """{{ config(materialized='incremental', incremental_strategy='append') }}
WITH duplicate_keys AS (
    SELECT timesheet_id FROM {{ source('bronze', 'pg_fact_timesheet') }}
    GROUP BY timesheet_id HAVING COUNT(*) > 1
)
SELECT a.*, 'Duplicate / CDC History' AS quarantine_reason
FROM {{ source('bronze', 'pg_fact_timesheet') }} a
JOIN duplicate_keys b ON a.timesheet_id = b.timesheet_id
{% if is_incremental() %} WHERE a.modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
"""
}

for name, content in models.items():
    with open(os.path.join(silver_dir, f"{name}.sql"), "w") as f:
        f.write(content)
