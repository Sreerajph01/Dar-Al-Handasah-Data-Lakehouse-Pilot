{{ config(materialized='table') }}
SELECT
    project_id,
    wbs_id,
    date_id,
    earned_value,
    planned_value,
    actual_cost,
    -- EVM calculations with zero-denominator handling
    earned_value / NULLIF(planned_value, 0) AS spi,
    earned_value / NULLIF(actual_cost, 0) AS cpi
FROM {{ source('bronze', 'pg_fact_evm_snapshot') }}
