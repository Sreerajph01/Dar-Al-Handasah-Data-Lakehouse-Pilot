import boto3
import os
import urllib.request

s3 = boto3.client(
    "s3",
    endpoint_url="http://seaweedfs-s3:8333",
    aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "admin"),
    aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "admin"),
    region_name="us-east-1"
)
try:
    s3.create_bucket(Bucket="bronze-lakehouse")
    print("Bucket created")
except Exception as e:
    print(f"Bucket creation error/skip: {e}")

try:
    req = urllib.request.Request(
        "http://lakekeeper:8181/management/v1/bootstrap",
        data=b'{}',
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        print("Lakekeeper bootstrap: ", resp.status)
except Exception as e:
    print(f"Lakekeeper bootstrap error/skip: {e}")
