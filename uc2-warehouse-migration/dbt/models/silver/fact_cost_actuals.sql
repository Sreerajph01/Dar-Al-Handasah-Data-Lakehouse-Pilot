{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='actual_id'
) }}

WITH cdc_events AS (
    SELECT * FROM {{ source('bronze', 'pg_fact_cost_actuals') }}
    {% if is_incremental() %}
    WHERE modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }})
    {% endif %}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY actual_id ORDER BY modified_at DESC) as rn
    FROM cdc_events
),
latest_events AS (
    SELECT * FROM ranked WHERE rn = 1
)
SELECT
    b.actual_id,
    b.wbs_id,
    b.cost_code,
    b.date_id,
    CAST(b.actual_cost AS DECIMAL(18, 4)) * CAST(fx.rate_to_usd AS DECIMAL(18, 4)) AS amount,
    'USD' AS currency,
    b.currency AS source_currency,
    b.vendor_id,
    b.invoice_ref,
    b.modified_at,
    CAST(b.row_version AS INTEGER) AS row_version,
    CAST(b.is_deleted AS BOOLEAN) AS is_deleted
FROM latest_events b
JOIN {{ ref('fx_rates') }} fx ON b.currency = fx.currency
