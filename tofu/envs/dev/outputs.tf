output "bucket_names" {
  description = "Created S3 bucket names"
  value       = [for b in aws_s3_bucket.lakehouse_buckets : b.id]
}

output "bronze_bucket" {
  value = aws_s3_bucket.lakehouse_buckets[var.bucket_bronze].id
}

output "silver_bucket" {
  value = aws_s3_bucket.lakehouse_buckets[var.bucket_silver].id
}

output "gold_bucket" {
  value = aws_s3_bucket.lakehouse_buckets[var.bucket_gold].id
}
