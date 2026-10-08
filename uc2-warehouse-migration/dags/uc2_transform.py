from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
}

with DAG('uc2_transform', default_args=default_args, schedule_interval=None, catchup=False) as dag:
    run_silver = BashOperator(
        task_id='run_silver',
        bash_command='cd /opt/airflow/dbt && dbt run --select silver'
    )
    
    test_silver = BashOperator(
        task_id='test_silver',
        bash_command='cd /opt/airflow/dbt && dbt test --select silver'
    )
    
    ge_checkpoint_bronze_silver = BashOperator(
        task_id='ge_checkpoint_bronze_silver',
        bash_command='python /opt/airflow/tests/uc2/run_ge_checkpoints.py'
    )
    
    run_gold = BashOperator(
        task_id='run_gold',
        bash_command='cd /opt/airflow/dbt && dbt run --select gold'
    )
    
    test_gold = BashOperator(
        task_id='test_gold',
        bash_command='cd /opt/airflow/dbt && dbt test --select gold'
    )
    
    publish = BashOperator(
        task_id='publish',
        bash_command='echo "Publishing Gold models..."'
    )

    run_silver >> test_silver >> ge_checkpoint_bronze_silver >> run_gold >> test_gold >> publish
