{{ config(materialized='incremental', incremental_strategy='append') }}
SELECT b.*, 'Unknown Currency' AS quarantine_reason 
FROM {{ source('bronze', 'pg_fact_budget') }} b
LEFT JOIN {{ ref('fx_rates') }} fx ON b.currency = fx.currency
WHERE fx.currency IS NULL
{% if is_incremental() %} AND b.modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
