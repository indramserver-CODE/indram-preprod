# Permissions boundary applied to every role this stack creates.
#
# Why: the GitHub infra role needs iam:* on the stack's own roles so Terraform
# can manage them, and role/indram-<env>-* matches the infra role itself. Without
# a boundary it could attach AdministratorAccess to itself. With the boundary,
# whatever policy gets attached, effective permissions never exceed:
#   PowerUser ceiling  +  IAM limited to this stack's resources  -  boundary tampering
# Changing the boundary itself is denied to CI; it must be applied by a human admin.

locals {
  boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${local.name}-boundary"

  stack_iam_resources = [
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.name}-*",
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/${local.name}-*",
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${local.name}-*",
  ]
}

data "aws_iam_policy_document" "boundary" {
  statement {
    sid         = "PowerUserCeiling"
    not_actions = ["iam:*", "organizations:*", "account:*"]
    resources   = ["*"]
  }

  statement {
    sid       = "IamReadOnly"
    actions   = ["iam:Get*", "iam:List*"]
    resources = ["*"]
  }

  statement {
    sid       = "IamScopedToStack"
    actions   = ["iam:*"]
    resources = local.stack_iam_resources
  }

  statement {
    sid    = "NoBoundaryTampering"
    effect = "Deny"
    actions = [
      "iam:DeleteRolePermissionsBoundary",
      "iam:PutRolePermissionsBoundary",
      "iam:DeleteUserPermissionsBoundary",
      "iam:PutUserPermissionsBoundary",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "NoBoundaryPolicyEdits"
    effect = "Deny"
    actions = [
      "iam:CreatePolicyVersion",
      "iam:DeletePolicy",
      "iam:DeletePolicyVersion",
      "iam:SetDefaultPolicyVersion",
    ]
    resources = [local.boundary_arn]
  }
}

resource "aws_iam_policy" "boundary" {
  name        = "${local.name}-boundary"
  description = "Permissions boundary for all indram-${var.env_name} roles; caps CI-managed roles below account admin"
  policy      = data.aws_iam_policy_document.boundary.json
}
