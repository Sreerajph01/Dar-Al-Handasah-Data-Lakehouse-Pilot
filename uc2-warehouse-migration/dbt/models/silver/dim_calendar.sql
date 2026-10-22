{{ config(materialized='table') }}

SELECT
    date_id,
    CAST(year AS INTEGER) AS year,
    CAST(quarter AS INTEGER) AS quarter,
    CAST(month AS INTEGER) AS month,
    month_name,
    CAST(day AS INTEGER) AS day,
    CAST(day_of_week AS INTEGER) AS day_of_week,
    day_name,
    CAST(week_of_year AS INTEGER) AS week_of_year,
    CAST(is_weekend AS BOOLEAN) AS is_weekend,
    CAST(is_holiday AS BOOLEAN) AS is_holiday,
    CAST(fiscal_year AS INTEGER) AS fiscal_year,
    CAST(fiscal_quarter AS INTEGER) AS fiscal_quarter
FROM {{ source('bronze', 'pg_dim_calendar') }}
