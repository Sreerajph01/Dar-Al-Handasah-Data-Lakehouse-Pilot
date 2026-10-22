from great_expectations.dataset.sqlalchemy_dataset import SqlAlchemyDataset
from sqlalchemy import create_engine

# Connect to Trino
engine = create_engine('trino://admin@dar-trino:8080/iceberg/silver')

# Validate dim_project
print("Running GE checkpoints on Silver...")
try:
    dataset = SqlAlchemyDataset(table_name='dim_project', engine=engine)

    # Check 1: project_id should not be null (should pass)
    res1 = dataset.expect_column_values_to_not_be_null('project_id')
    print("Project ID not null:", res1.success)

    # Check 2: injected critical failure
    res2 = dataset.expect_column_values_to_be_in_set('project_name', ['Non Existent Project'])
    print("Injected critical failure:", res2.success)

    if not res2.success:
        print("CRITICAL FAILURE: GE checkpoint failed! Blocking Gold publication.")
        exit(1)

except Exception as e:
    print(f"Error running GE: {e}")
    exit(1)
