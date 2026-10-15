# Optional cost saver: EventBridge Scheduler stops/starts the instance on a
# cron. Compute is not billed while stopped; EBS and the Elastic IP still are.
# Enabled via var.office_hours.enabled (default false).

locals {
  sched_count = var.office_hours.enabled ? 1 : 0
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  count              = local.sched_count
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  count = local.sched_count
  name  = "${local.name}-scheduler"
  role  = aws_iam_role.scheduler[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:StartInstances", "ec2:StopInstances"]
      Resource = aws_instance.app.arn
    }]
  })
}

resource "aws_scheduler_schedule" "stop" {
  count                        = local.sched_count
  name                         = "${local.name}-stop"
  schedule_expression          = var.office_hours.stop
  schedule_expression_timezone = var.office_hours.timezone

  flexible_time_window { mode = "OFF" }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.scheduler[0].arn
    input    = jsonencode({ InstanceIds = [aws_instance.app.id] })
  }
}

resource "aws_scheduler_schedule" "start" {
  count                        = local.sched_count
  name                         = "${local.name}-start"
  schedule_expression          = var.office_hours.start
  schedule_expression_timezone = var.office_hours.timezone

  flexible_time_window { mode = "OFF" }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.scheduler[0].arn
    input    = jsonencode({ InstanceIds = [aws_instance.app.id] })
  }
}
