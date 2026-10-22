import trino
import boto3
import botocore
import os

# 1. Trino DBAPI
conn = trino.dbapi.connect(host="trino", port=8080, user="admin", catalog="iceberg")
cur = conn.cursor()

print("=== ICEBERG TABLES & ROW COUNTS ===")
for schema in ["bronze", "silver", "gold"]:
    print(f"\n--- Layer: iceberg.{schema} ---")
    cur.execute(f"SHOW TABLES IN iceberg.{schema}")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables[:8]:  # show sample per layer
        try:
            cur.execute(f"SELECT COUNT(*) FROM iceberg.{schema}.{t}")
            cnt = cur.fetchone()[0]
            print(f"  iceberg.{schema}.{t:<25}: {cnt:>6} rows")
        except Exception as e:
            print(f"  iceberg.{schema}.{t:<25}: Error ({e})")

# 2. Iceberg Snapshots & Metadata
print("\n=== ICEBERG SNAPSHOT METADATA (iceberg.gold.evm_metrics) ===")
cur.execute('SELECT committed_at, snapshot_id, operation, summary[\'total-records\'] FROM iceberg.gold."evm_metrics$snapshots"')
rows = cur.fetchall()
for r in rows:
    print(f"  Snapshot ID: {r[1]} | Committed: {r[0]} | Op: {r[2]} | Total Records: {r[3]}")

# 3. S3 Files in Object Storage (SeaweedFS)
print("\n=== S3 OBJECT STORAGE (SeaweedFS S3) ===")
s3 = boto3.client(
    "s3",
    endpoint_url="http://seaweedfs-s3:8333",
    aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "DARLAKE328A2EA70167B789"),
    aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "91702b6a6ac27f26eb666f7c37b3f81dfb90ba25"),
    region_name="us-east-1",
    config=botocore.client.Config(s3={"addressing_style": "path"})
)

buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
print(f"Buckets: {buckets}")
for bucket in ["gold-lakehouse", "silver-lakehouse", "bronze-lakehouse"]:
    if bucket in buckets:
        objs = s3.list_objects_v2(Bucket=bucket, MaxKeys=5).get("Contents", [])
        print(f"Sample objects in {bucket} ({len(objs)} objects):")
        for obj in objs[:3]:
            print(f"  • {obj['Key']} ({obj['Size']} bytes)")
