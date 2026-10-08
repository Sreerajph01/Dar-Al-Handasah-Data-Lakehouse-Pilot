{{ config(materialized='incremental', incremental_strategy='merge', unique_key='budget_id') }}
WITH cdc_events AS (
    SELECT * FROM {{ source('bronze', 'pg_fact_budget') }}
    {% if is_incremental() %} WHERE modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }}) {% endif %}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY budget_id ORDER BY modified_at DESC) as rn
    FROM cdc_events
),
latest_events AS (
    SELECT * FROM ranked WHERE rn = 1
)
SELECT 
    b.budget_id, 
    b.wbs_id, 
    CAST(b.budget_amount AS double) * CAST(fx.rate_to_usd AS double) AS amount, 
    'USD' AS currency, 
    b.modified_at, 
    b.is_deleted
FROM latest_events b
JOIN {{ ref('fx_rates') }} fx ON b.currency = fx.currency
