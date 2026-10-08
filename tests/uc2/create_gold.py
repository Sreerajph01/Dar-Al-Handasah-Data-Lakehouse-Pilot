import os

gold_dir = "C:\\dar-lakehouse-pilot\\uc2-warehouse-migration\\dbt\\models\\gold"
os.makedirs(gold_dir, exist_ok=True)

# Remove old models if they exist
for old_model in ["fact_evm.sql", "fact_financials.sql"]:
    path = os.path.join(gold_dir, old_model)
    if os.path.exists(path):
        os.remove(path)

models = {
    "project_summary": """{{ config(materialized='table') }}
SELECT
    p.project_id,
    p.project_name,
    p.client_name,
    p.project_type,
    p.country,
    p.status
FROM {{ ref('dim_project') }} p
WHERE p.is_current = TRUE
""",
    "budget_vs_actual": """{{ config(materialized='table') }}
SELECT
    b.wbs_id,
    SUM(b.amount) AS total_budget,
    b.currency
FROM {{ ref('fact_budget') }} b
GROUP BY b.wbs_id, b.currency
""",
    "timesheet_utilisation": """{{ config(materialized='table') }}
SELECT
    t.employee_id,
    t.wbs_id,
    SUM(CAST(t.hours AS double)) AS total_hours
FROM {{ ref('fact_timesheet') }} t
GROUP BY t.employee_id, t.wbs_id
""",
    "evm_metrics": """{{ config(materialized='table') }}
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
""",
    "wbs_cost_rollup": """{{ config(materialized='table') }}
SELECT
    w.wbs_id,
    w.wbs_name,
    w.project_id
FROM {{ ref('dim_wbs') }} w
WHERE w.is_current = TRUE
""",
    "reconciliation": """{{ config(materialized='table') }}
WITH source_budget AS (
    SELECT SUM(CAST(amount AS double)) AS source_total FROM postgresql.public.fact_budget
),
gold_budget AS (
    SELECT SUM(total_budget) AS gold_total FROM {{ ref('budget_vs_actual') }}
)
SELECT
    source_total,
    gold_total,
    ABS(source_total - gold_total) AS difference,
    CASE WHEN ABS(source_total - gold_total) < 0.01 THEN TRUE ELSE FALSE END AS is_within_tolerance
FROM source_budget, gold_budget
"""
}

for name, content in models.items():
    with open(os.path.join(gold_dir, f"{name}.sql"), "w") as f:
        f.write(content)
