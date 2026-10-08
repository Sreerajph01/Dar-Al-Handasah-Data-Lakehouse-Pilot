variable "s3_endpoint" {
  description = "SeaweedFS S3 gateway endpoint URL"
  type        = string
  default     = "http://seaweedfs-s3:8333"
}

variable "s3_access_key" {
  description = "S3 access key"
  type        = string
  sensitive   = true
}

variable "s3_secret_key" {
  description = "S3 secret key"
  type        = string
  sensitive   = true
}

variable "s3_region" {
  description = "S3 region (SeaweedFS ignores this but SDK requires it)"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev | uat | prod)"
  type        = string
  default     = "dev"
}

variable "bucket_bronze" {
  description = "Bronze lakehouse bucket name"
  type        = string
  default     = "bronze-lakehouse"
}

variable "bucket_silver" {
  description = "Silver lakehouse bucket name"
  type        = string
  default     = "silver-lakehouse"
}

variable "bucket_gold" {
  description = "Gold lakehouse bucket name"
  type        = string
  default     = "gold-lakehouse"
}

variable "bucket_raw_files" {
  description = "Raw unstructured files bucket"
  type        = string
  default     = "raw-files"
}

variable "bucket_audit" {
  description = "Audit logs bucket"
  type        = string
  default     = "audit-logs"
}
