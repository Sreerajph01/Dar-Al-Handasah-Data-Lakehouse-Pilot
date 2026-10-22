import boto3
import uuid

s3_endpoint = "http://seaweedfs-s3:8333"

def test_versioning():
    bucket_name = f"test-versioning-{uuid.uuid4()}"
    client = boto3.client('s3', endpoint_url=s3_endpoint, aws_access_key_id='admin', aws_secret_access_key='admin', region_name='us-east-1')

    print(f"Creating bucket {bucket_name}...")
    client.create_bucket(Bucket=bucket_name)

    try:
        print("Enabling versioning...")
        client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        print("PASS: Versioning enabled successfully!")
    except Exception as e:
        print(f"FAIL: Error enabling versioning: {e}")

if __name__ == "__main__":
    test_versioning()
