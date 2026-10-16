terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # Bucket/key/region are supplied via:  terraform init -backend-config=backend.hcl
  # (see backend.hcl.example). S3 native locking replaces DynamoDB (TF >= 1.10).
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "indram"
      Environment = var.env_name
      ManagedBy   = "terraform"
      Repository  = var.github_repo
    }
  }
}
