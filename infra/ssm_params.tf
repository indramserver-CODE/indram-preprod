locals {
  ssm_prefix = "/indram/${var.env_name}"

  # Values derived from other resources, merged over the user map
  derived_parameters = merge(var.app_parameters, {
    CORS_ORIGINS   = "https://${var.app_domain}"
    FRONTEND_URL   = "https://${var.app_domain}"
    S3_BUCKET_NAME = var.bills_bucket_name
  })
}

# Non-secret settings only. Plain String type: safe in state and plan output.
resource "aws_ssm_parameter" "plain" {
  # SSM rejects empty strings, and an unset key is what the app expects anyway
  for_each = { for k, v in local.derived_parameters : k => v if v != "" }

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "String"
  value = each.value
}

# Secrets are deliberately NOT Terraform resources.
#
# The AWS provider reads every SSM parameter back with WithDecryption=true and
# stores the value in state, and `ignore_changes` does not prevent that. Any
# SecureString managed here would end up in the state bucket and in every saved
# plan file. Instead, secrets are written straight to Parameter Store with
# infra/push-secrets.sh and only ever read by the EC2 host at deploy time.
#
# The block below forgets the placeholder parameters an earlier version of this
# file created, without deleting them from AWS. It is a no-op once applied.
removed {
  from = aws_ssm_parameter.secret

  lifecycle {
    destroy = false
  }
}
