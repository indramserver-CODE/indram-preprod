# Copy these into the GitHub environment variables (Settings → Environments → preprod → Variables)
output "github_variables" {
  description = "Values for the GitHub Actions environment"
  value = {
    AWS_REGION          = var.aws_region
    AWS_PLAN_ROLE_ARN   = aws_iam_role.github_plan.arn
    AWS_DEPLOY_ROLE_ARN = aws_iam_role.github_deploy.arn
    AWS_INFRA_ROLE_ARN  = aws_iam_role.github_infra.arn
    EC2_INSTANCE_ID     = aws_instance.app.id
    ECR_REPOSITORY      = aws_ecr_repository.api.name
    ARTIFACTS_BUCKET    = aws_s3_bucket.artifacts.bucket
    APP_DOMAIN          = var.app_domain
    API_DOMAIN          = var.api_domain
    DOCKER_PLATFORM     = local.docker_platform
  }
}

output "estimated_monthly_usd" {
  description = "Rough always-on cost in ap-south-1 for the chosen size (compute + disk + public IPv4). Excludes free-tier credits."
  value = format("%.1f",
    (var.instance_type == "t4g.micro" ? 4.1 : var.instance_type == "t3.micro" ? 8.2 : var.instance_type == "t4g.small" ? 8.2 : var.instance_type == "t3.small" ? 16.4 : 0)
    + var.root_volume_gb * 0.0912
    + 3.65
  )
}

output "public_ip" {
  description = "Point app_domain and api_domain A records here if DNS is managed outside Route53"
  value       = aws_eip.app.public_ip
}

output "ssm_parameter_prefix" {
  value = local.ssm_prefix
}
