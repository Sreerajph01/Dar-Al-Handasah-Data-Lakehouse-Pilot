import boto3
import urllib.request
import json

s3 = boto3.client(
    "s3",
    endpoint_url="http://seaweedfs-s3:8333",
    aws_access_key_id="admin",
    aws_secret_access_key="admin",
    region_name="us-east-1"
)

print("Buckets:", s3.list_buckets())

s3.put_object(Bucket="bronze-lakehouse", Key="metadata/test", Body=b"hello")
print("Write successful!")
