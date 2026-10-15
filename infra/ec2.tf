data "aws_ssm_parameter" "ubuntu_ami" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

resource "aws_instance" "app" {
  ami                         = data.aws_ssm_parameter.ubuntu_ami.value
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.web.id]
  iam_instance_profile        = aws_iam_instance_profile.instance.name
  associate_public_ip_address = true

  user_data = templatefile("${path.module}/user_data.sh", {
    env_name     = var.env_name
    aws_region   = var.aws_region
    ecr_repo_url = aws_ecr_repository.api.repository_url
    app_domain   = var.app_domain
    api_domain   = var.api_domain
    artifacts    = aws_s3_bucket.artifacts.bucket
  })
  user_data_replace_on_change = false # edits to user_data.sh never recreate the box

  metadata_options {
    http_tokens                 = "required" # IMDSv2
    http_put_response_hop_limit = 2          # containers can still reach the instance role
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  lifecycle {
    ignore_changes = [ami] # AMI pointer moves; don't replace the instance on every apply
  }

  tags = { Name = "${local.name}-app" }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "${local.name}-app" }
}
