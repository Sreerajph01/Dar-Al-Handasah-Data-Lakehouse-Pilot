import boto3
import uuid
import sys
from botocore.exceptions import ClientError
from botocore.config import Config

s3_endpoint = "http://seaweedfs-s3:8333"

def test_identities():
    bucket_name = f"test-identities-{uuid.uuid4()}"

    # Admin client
    admin_client = boto3.client('s3',
        endpoint_url=s3_endpoint,
        aws_access_key_id='admin',
        aws_secret_access_key='admin',
        region_name='us-east-1',
        config=Config(signature_version='s3v4')
    )

    # Read-only client
    ro_client = boto3.client('s3',
        endpoint_url=s3_endpoint,
        aws_access_key_id='readonly-admin',
        aws_secret_access_key='readonly-admin',
        region_name='us-east-1',
        config=Config(signature_version='s3v4')
    )

    print(f"Creating bucket {bucket_name} as admin...")
    admin_client.create_bucket(Bucket=bucket_name)

    print("Writing object as admin...")
    admin_client.put_object(Bucket=bucket_name, Key='test.txt', Body=b'hello world')

    print("Reading object as admin...")
    resp = admin_client.get_object(Bucket=bucket_name, Key='test.txt')
    print("Admin read:", resp['Body'].read())

    print("Reading object as read-only admin...")
    resp = ro_client.get_object(Bucket=bucket_name, Key='test.txt')
    print("Read-only read:", resp['Body'].read())

    print("Attempting to write object as read-only admin...")
    try:
        ro_client.put_object(Bucket=bucket_name, Key='test2.txt', Body=b'hello world 2')
        print("FAIL: Read-only admin was able to write!")
        sys.exit(1)
    except ClientError as e:
        if e.response['Error']['Code'] == 'AccessDenied':
            print("PASS: Read-only admin got AccessDenied on write.")
        else:
            print("FAIL: Unexpected error:", e)
            sys.exit(1)

    print("All identity tests passed.")

if __name__ == "__main__":
    test_identities()
