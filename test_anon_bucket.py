import boto3
from botocore import UNSIGNED
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url="http://seaweedfs-s3:8333",
    config=Config(signature_version=UNSIGNED),
    region_name="us-east-1"
)

try:
    s3.create_bucket(Bucket="bronze-lakehouse")
    print("Bucket created anonymously")
except Exception as e:
    print("Failed to create bucket anonymously:", e)

try:
    s3.put_object(Bucket="bronze-lakehouse", Key="test", Body=b"hello")
    print("Anonymous put success")
except Exception as e:
    print("Anonymous put failed:", e)
