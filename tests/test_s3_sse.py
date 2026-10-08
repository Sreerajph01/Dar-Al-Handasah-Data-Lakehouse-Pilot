import boto3
import uuid

s3_endpoint = "http://seaweedfs-s3:8333"

def test_sse():
    bucket_name = f"test-sse-{uuid.uuid4()}"
    client = boto3.client('s3', endpoint_url=s3_endpoint, aws_access_key_id='admin', aws_secret_access_key='admin', region_name='us-east-1')
    
    print(f"Creating bucket {bucket_name}...")
    client.create_bucket(Bucket=bucket_name)
    
    try:
        print("Uploading object with AES256 SSE...")
        resp = client.put_object(
            Bucket=bucket_name,
            Key='test.txt',
            Body=b'hello world',
            ServerSideEncryption='AES256'
        )
        print("Upload response:", resp)
        print("Checking object metadata...")
        meta = client.head_object(Bucket=bucket_name, Key='test.txt')
        print("Metadata:", meta)
        
        if meta.get('ServerSideEncryption') == 'AES256':
            print("PASS: SSE AES256 is supported and returned.")
        else:
            print(f"FAIL: SSE not returned in head_object! Got: {meta.get('ServerSideEncryption')}")
            
    except Exception as e:
        print(f"FAIL: Error during SSE test: {e}")

if __name__ == "__main__":
    test_sse()
