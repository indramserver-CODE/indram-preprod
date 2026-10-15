# GitHub Actions authenticates with OIDC; no static AWS keys in GitHub.
#
# Three roles with *separate* trust policies so the GitHub environment approval
# gates are enforced at the AWS boundary, not just in the workflow file:
#
#   plan    read-only; trusted by pull_request jobs and pushes to main
#   deploy  push image/bundle + run deploy.sh; trusted by pushes to main and the `preprod` environment
#   infra   terraform apply; trusted ONLY by the `preprod-infra` environment (required reviewer)
#
# Every role carries the permissions boundary from boundary.tf.

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's cert chain itself; the thumbprint is required by the API but not used.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  github_oidc_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn

  github_role_subjects = {
    plan = [
      "repo:${var.github_repo}:pull_request",
      "repo:${var.github_repo}:ref:refs/heads/main",
    ]
    deploy = [
      "repo:${var.github_repo}:ref:refs/heads/main",
      "repo:${var.github_repo}:environment:${var.env_name}",
    ]
    infra = [
      "repo:${var.github_repo}:environment:${var.env_name}-infra",
    ]
  }
}

data "aws_iam_policy_document" "github_assume" {
  for_each = local.github_role_subjects

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = each.value
    }
  }
}

# ── Plan role: read-only + state lock ─────────────────────────────────────
resource "aws_iam_role" "github_plan" {
  name                 = "${local.name}-github-plan"
  assume_role_policy   = data.aws_iam_policy_document.github_assume["plan"].json
  permissions_boundary = aws_iam_policy.boundary.arn
}

resource "aws_iam_role_policy_attachment" "github_plan_readonly" {
  role       = aws_iam_role.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "github_plan" {
  statement {
    sid       = "StateLock"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.tf_state_bucket}/${var.tf_state_key}.tflock"]
  }
}

resource "aws_iam_role_policy" "github_plan" {
  name   = "${local.name}-github-plan"
  role   = aws_iam_role.github_plan.id
  policy = data.aws_iam_policy_document.github_plan.json
}

# ── Deploy role: push image, upload bundle, run deploy.sh via SSM ─────────
resource "aws_iam_role" "github_deploy" {
  name                 = "${local.name}-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_assume["deploy"].json
  permissions_boundary = aws_iam_policy.boundary.arn
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
    ]
    resources = [aws_ecr_repository.api.arn]
  }

  statement {
    sid       = "UploadBundle"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
  }

  statement {
    sid     = "RunDeployScript"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.app.arn,
      "arn:aws:ssm:${var.aws_region}::document/AWS-RunShellScript",
    ]
  }

  statement {
    sid       = "ReadCommandResult"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations", "ssm:ListCommands"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${local.name}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

# ── Infra role: terraform apply, only from the approval-gated environment ─
resource "aws_iam_role" "github_infra" {
  name                 = "${local.name}-github-infra"
  assume_role_policy   = data.aws_iam_policy_document.github_assume["infra"].json
  permissions_boundary = aws_iam_policy.boundary.arn
}

resource "aws_iam_role_policy_attachment" "github_infra_poweruser" {
  role       = aws_iam_role.github_infra.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

# PowerUserAccess excludes IAM. Grant IAM only on this stack's resources, and only
# allow policies to be attached to roles that carry the permissions boundary.
data "aws_iam_policy_document" "github_infra_iam" {
  statement {
    sid = "ManageStackRolesWithBoundary"
    actions = [
      "iam:CreateRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.name}-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [local.boundary_arn]
    }
  }

  statement {
    sid = "ManageStackRoles"
    actions = [
      "iam:GetRole",
      "iam:DeleteRole",
      "iam:UpdateRole",
      "iam:UpdateRoleDescription",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:PassRole",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:GetRolePolicy",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.name}-*"]
  }

  statement {
    sid = "ManageStackInstanceProfiles"
    actions = [
      "iam:CreateInstanceProfile",
      "iam:DeleteInstanceProfile",
      "iam:GetInstanceProfile",
      "iam:AddRoleToInstanceProfile",
      "iam:RemoveRoleFromInstanceProfile",
      "iam:TagInstanceProfile",
      "iam:UntagInstanceProfile",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/${local.name}-*"]
  }

  statement {
    sid = "ManageStackPolicies"
    actions = [
      "iam:CreatePolicy",
      "iam:DeletePolicy",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyVersions",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:TagPolicy",
      "iam:UntagPolicy",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${local.name}-*"]
  }

  statement {
    sid       = "IamReadOnly"
    actions   = ["iam:Get*", "iam:List*"]
    resources = ["*"]
  }

  # Explicit denies win over everything above and over any policy the role attaches to itself.
  statement {
    sid    = "NoBoundaryTampering"
    effect = "Deny"
    actions = [
      "iam:DeleteRolePermissionsBoundary",
      "iam:PutRolePermissionsBoundary",
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

resource "aws_iam_role_policy" "github_infra_iam" {
  name   = "${local.name}-github-infra-iam"
  role   = aws_iam_role.github_infra.id
  policy = data.aws_iam_policy_document.github_infra_iam.json
}
