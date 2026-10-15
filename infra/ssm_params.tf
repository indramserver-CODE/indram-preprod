locals {
  ssm_prefix = "/indram/${var.env_name}"

  # Values derived from other resources, merged over the user map
  derived_parameters = merge(var.app_parameters, {
    CORS_ORIGINS   = "https://${var.app_domain}"
    FRONTEND_URL   = "https://${var.app_domain}"
    S3_BUCKET_NAME = var.bills_bucket_name
  })
}

resource "aws_ssm_parameter" "plain" {
  # SSM rejects empty strings, and an unset key is what the app expects anyway
  for_each = { for k, v in local.derived_parameters : k => v if v != "" }

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "String"
  value = each.value
}

# Placeholders only. Real values are written with `aws ssm put-parameter --overwrite`
# and Terraform ignores them afterwards so secrets never enter the state file.
resource "aws_ssm_parameter" "secret" {
  for_each = toset(var.secret_parameter_names)

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
