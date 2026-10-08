import os

gold_dir = "uc2-warehouse-migration/dbt/models/gold"
os.makedirs(gold_dir, exist_ok=True)

models = {
    "fact_evm": """{{ config(materialized='table') }}
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
""",
    "fact_financials": """{{ config(materialized='table') }}
SELECT
    wbs_id,
    CAST(amount AS double) AS amount,
    currency,
    modified_at
FROM {{ ref('fact_budget') }}
""",
    "reconciliation": """{{ config(materialized='table') }}
WITH silver_budget AS (
    SELECT SUM(CAST(amount AS double)) AS silver_total FROM {{ ref('fact_budget') }}
),
gold_budget AS (
    SELECT SUM(CAST(amount AS double)) AS gold_total FROM {{ ref('fact_financials') }}
)
SELECT
    silver_total,
    gold_total,
    ABS(silver_total - gold_total) AS difference,
    CASE WHEN ABS(silver_total - gold_total) < 0.01 THEN TRUE ELSE FALSE END AS is_within_tolerance
FROM silver_budget, gold_budget
"""
}

for name, content in models.items():
    with open(os.path.join(gold_dir, f"{name}.sql"), "w") as f:
        f.write(content)
