{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='snapshot_id'
) }}

WITH cdc_events AS (
    SELECT * FROM {{ source('bronze', 'pg_fact_evm_snapshot') }}
    {% if is_incremental() %}
    WHERE modified_at > (SELECT coalesce(MAX(modified_at), '1970-01-01T00:00:00Z') FROM {{ this }})
    {% endif %}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY snapshot_id ORDER BY modified_at DESC) as rn
    FROM cdc_events
)
SELECT
    snapshot_id,
    project_id,
    date_id,
    CAST(planned_value AS DECIMAL(18, 4)) AS planned_value,
    CAST(earned_value AS DECIMAL(18, 4)) AS earned_value,
    CAST(actual_cost AS DECIMAL(18, 4)) AS actual_cost,
    CAST(budget_at_completion AS DECIMAL(18, 4)) AS budget_at_completion,
    CAST(estimate_at_completion AS DECIMAL(18, 4)) AS estimate_at_completion,
    CAST(schedule_variance AS DECIMAL(18, 4)) AS schedule_variance,
    CAST(cost_variance AS DECIMAL(18, 4)) AS cost_variance,
    CAST(spi AS DECIMAL(18, 4)) AS spi,
    CAST(cpi AS DECIMAL(18, 4)) AS cpi,
    CAST(percent_complete AS DECIMAL(18, 4)) AS percent_complete,
    modified_at,
    CAST(row_version AS INTEGER) AS row_version,
    CAST(is_deleted AS BOOLEAN) AS is_deleted
FROM ranked
WHERE rn = 1
