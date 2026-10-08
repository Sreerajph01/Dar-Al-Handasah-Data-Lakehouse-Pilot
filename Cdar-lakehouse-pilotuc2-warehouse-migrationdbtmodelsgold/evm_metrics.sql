{{ config(materialized='table') }}
SELECT
    project_id,
    date_id,
    CAST(earned_value AS double) AS ev,
    CAST(planned_value AS double) AS pv,
    CAST(actual_cost AS double) AS ac,
    CAST(budget_at_completion AS double) AS bac,
    -- EVM formulas
    CAST(earned_value AS double) - CAST(planned_value AS double) AS sv,
    CAST(earned_value AS double) - CAST(actual_cost AS double) AS cv,
    CAST(earned_value AS double) / NULLIF(CAST(planned_value AS double), 0) AS spi,
    CAST(earned_value AS double) / NULLIF(CAST(actual_cost AS double), 0) AS cpi,
    CAST(budget_at_completion AS double) / NULLIF(CAST(earned_value AS double) / NULLIF(CAST(actual_cost AS double), 0), 0) AS eac,
    (CAST(budget_at_completion AS double) / NULLIF(CAST(earned_value AS double) / NULLIF(CAST(actual_cost AS double), 0), 0)) - CAST(actual_cost AS double) AS etc,
    CAST(budget_at_completion AS double) - (CAST(budget_at_completion AS double) / NULLIF(CAST(earned_value AS double) / NULLIF(CAST(actual_cost AS double), 0), 0)) AS vac,
    (CAST(budget_at_completion AS double) - CAST(earned_value AS double)) / NULLIF(CAST(budget_at_completion AS double) - CAST(actual_cost AS double), 0) AS tcpi
FROM {{ source('bronze', 'pg_fact_evm_snapshot') }}
