data "aws_vpc" "this" {
  default = var.vpc_id == "" ? true : null
  id      = var.vpc_id == "" ? null : var.vpc_id
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.this.id]
  }
  filter {
    name   = "default-for-az"
    values = [var.vpc_id == "" ? "true" : "false"]
  }
}

locals {
  subnet_id = var.subnet_id != "" ? var.subnet_id : sort(data.aws_subnets.public.ids)[0]
  name      = "indram-${var.env_name}"
}

resource "aws_security_group" "web" {
  name        = "${local.name}-web"
  description = "HTTP/HTTPS in, everything out. No SSH: access is via SSM Session Manager."
  vpc_id      = data.aws_vpc.this.id

  ingress {
    description      = "HTTP (ACME challenge + redirect)"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "HTTPS"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "HTTP/3"
    from_port        = 443
    to_port          = 443
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = { Name = "${local.name}-web" }
}
