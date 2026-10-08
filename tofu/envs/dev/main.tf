terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.68"
    }
  }
}

# ── S3 provider targeting SeaweedFS S3 gateway ────────────────────────────────
provider "aws" {
  region                      = var.s3_region
  access_key                  = var.s3_access_key
  secret_key                  = var.s3_secret_key
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3 = var.s3_endpoint
  }

  s3_use_path_style = true   # required for SeaweedFS
}

# ── S3 buckets ────────────────────────────────────────────────────────────────
locals {
  buckets = [
    var.bucket_bronze,
    var.bucket_silver,
    var.bucket_gold,
    var.bucket_raw_files,
    var.bucket_audit,
  ]
}

resource "aws_s3_bucket" "lakehouse_buckets" {
  for_each = toset(local.buckets)

  bucket        = each.value
  force_destroy = true   # dev/demo: allow destroy even with objects


}

