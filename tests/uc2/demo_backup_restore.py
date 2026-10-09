import os
import subprocess

# We'll use docker exec or AWS CLI against the SeaweedFS S3 gateway.
# A simpler way is to use the AWS CLI via docker.
def run_aws(cmd):
    full_cmd = f"docker run --rm --network dar-lakehouse_default amazon/aws-cli --endpoint-url http://dar-seaweedfs-s3:8333 {cmd}"
    # set aws access keys for the container
    env = " -e AWS_ACCESS_KEY_ID=admin -e AWS_SECRET_ACCESS_KEY=password "
    full_cmd = full_cmd.replace("amazon/aws-cli", env + "amazon/aws-cli")
    print(f"Running: {full_cmd}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error:", result.stderr)
    return result.stdout

print("--- Backup/Restore Demo ---")
print("1. Creating a backup bucket 'lakehouse-backup'...")
run_aws("s3 mb s3://lakehouse-backup")

print("2. Backing up the 'silver' schema directory (dim_project) to backup bucket...")
# Iceberg tables are stored in s3://lakehouse/silver/
run_aws("s3 sync s3://lakehouse/silver/dim_project s3://lakehouse-backup/silver/dim_project")

print("3. Verifying backup exists...")
res = run_aws("s3 ls s3://lakehouse-backup/silver/dim_project/")
print(res)

print("4. Restoring data (sync back)...")
run_aws("s3 sync s3://lakehouse-backup/silver/dim_project s3://lakehouse/silver/dim_project")
print("Backup/Restore demo completed successfully.")
