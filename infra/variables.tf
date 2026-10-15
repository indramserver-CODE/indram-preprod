variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "env_name" {
  description = "Environment name; used in resource names and the SSM parameter prefix /indram/<env>/"
  type        = string
  default     = "preprod"
}

variable "github_repo" {
  description = "GitHub repository allowed to deploy, as owner/name"
  type        = string
  default     = "indramserver-CODE/indram-preprod"
}

variable "create_github_oidc_provider" {
  description = "false if the account already has the token.actions.githubusercontent.com OIDC provider"
  type        = bool
  default     = true
}

variable "app_domain" {
  description = "Hostname that serves the React frontend, e.g. app.preprod.indram.in"
  type        = string
}

variable "api_domain" {
  description = "Hostname that serves the FastAPI backend, e.g. api.preprod.indram.in"
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone to create A records in. Leave empty to manage DNS elsewhere."
  type        = string
  default     = ""
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "root_volume_gb" {
  type    = number
  default = 20
}

variable "vpc_id" {
  description = "VPC to launch into. Empty = account default VPC."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Public subnet for the instance. Empty = first subnet of the chosen VPC."
  type        = string
  default     = ""
}

variable "bills_bucket_name" {
  description = "Optional S3 bucket for bill PDFs (S3_BUCKET_NAME). Empty = not created."
  type        = string
  default     = ""
}

variable "app_parameters" {
  description = <<-EOT
    Non-secret app settings written to /indram/<env>/<KEY>. Secrets are NOT set here —
    they are created as empty placeholders and filled with `aws ssm put-parameter`
    (see README). Anything the app reads from the environment can go in this map.
  EOT
  type        = map(string)
  default = {
    ENABLE_MQTT                   = "false"
    ENABLE_SCHEDULER              = "false"
    MQTT_PORT                     = "8883"
    MQTT_USE_TLS                  = "true"
    MQTT_CLIENT_ID                = "evc-server-preprod"
    ALGORITHM                     = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES   = "480"
    PASSWORD_RESET_EXPIRE_MINUTES = "30"
    BILLING_DAY_OF_MONTH          = "1"
    AWS_REGION                    = "ap-south-1"
    RUN_MIGRATIONS                = "false"
  }
}

variable "secret_parameter_names" {
  description = "SecureString parameters created as placeholders; values are set out of band and ignored by Terraform."
  type        = list(string)
  default = [
    "DATABASE_URL",
    "SECRET_KEY",
    "MQTT_HOST",
    "MQTT_USERNAME",
    "MQTT_PASSWORD",
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "CMD_AUTH_TOKEN",
    "SUPER_ADMIN_EMAIL",
    "SUPER_ADMIN_PASSWORD",
  ]
}
