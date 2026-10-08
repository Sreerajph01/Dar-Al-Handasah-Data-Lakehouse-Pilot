{{ config(materialized='incremental', incremental_strategy='append') }}
SELECT *, 'Non-USD Currency' AS quarantine_reason FROM {{ source('bronze', 'pg_fact_budget') }}
WHERE currency != 'USD'
{% if is_incremental() %} AND modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
