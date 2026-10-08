{{ config(materialized='table') }}
SELECT
    project_id,
    date_id,
    CAST(earned_value AS double) AS earned_value,
    CAST(planned_value AS double) AS planned_value,
    CAST(actual_cost AS double) AS actual_cost,
    -- EVM calculations with zero-denominator handling
    CAST(earned_value AS double) / NULLIF(CAST(planned_value AS double), 0) AS spi,
    CAST(earned_value AS double) / NULLIF(CAST(actual_cost AS double), 0) AS cpi
FROM {{ source('bronze', 'pg_fact_evm_snapshot') }}
