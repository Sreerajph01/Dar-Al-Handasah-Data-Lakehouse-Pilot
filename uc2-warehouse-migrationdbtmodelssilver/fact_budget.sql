{{ config(materialized='incremental', incremental_strategy='merge', unique_key='budget_id') }}
WITH cdc_events AS (
    SELECT * FROM {{ source('bronze', 'pg_fact_budget') }}
    WHERE currency = 'USD'
    {% if is_incremental() %} AND modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY budget_id ORDER BY modified_at DESC) as rn
    FROM cdc_events
)
SELECT budget_id, project_id, wbs_id, amount, currency, submitted_by, modified_at, is_deleted
FROM ranked WHERE rn = 1
