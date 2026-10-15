# Copy these into the GitHub environment variables (Settings → Environments → preprod → Variables)
output "github_variables" {
  description = "Values for the GitHub Actions environment"
  value = {
    AWS_REGION          = var.aws_region
    AWS_DEPLOY_ROLE_ARN = aws_iam_role.github_deploy.arn
    AWS_INFRA_ROLE_ARN  = aws_iam_role.github_infra.arn
    EC2_INSTANCE_ID     = aws_instance.app.id
    ECR_REPOSITORY      = aws_ecr_repository.api.name
    ARTIFACTS_BUCKET    = aws_s3_bucket.artifacts.bucket
    APP_DOMAIN          = var.app_domain
    API_DOMAIN          = var.api_domain
  }
}

output "public_ip" {
  description = "Point app_domain and api_domain A records here if DNS is managed outside Route53"
  value       = aws_eip.app.public_ip
}

output "ssm_parameter_prefix" {
  value = local.ssm_prefix
}
