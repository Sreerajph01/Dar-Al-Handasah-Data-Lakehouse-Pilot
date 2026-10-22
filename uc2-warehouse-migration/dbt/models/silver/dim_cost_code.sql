{{ config(materialized='table') }}

SELECT
    cost_code,
    description,
    category,
    CAST(is_billable AS BOOLEAN) AS is_billable,
    modified_at,
    CAST(row_version AS INTEGER) AS row_version,
    CAST(is_deleted AS BOOLEAN) AS is_deleted
FROM {{ source('bronze', 'pg_dim_cost_code') }}
WHERE is_deleted = 'false'
