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
  description = "t4g.* (ARM/Graviton) is the cheapest; the image is built for the matching architecture automatically."
  type        = string
  default     = "t4g.micro" # 2 vCPU / 1 GB, ~USD 4/month in ap-south-1
}

variable "root_volume_gb" {
  type    = number
  default = 16
}

variable "cpu_credits" {
  description = "standard = never pay burst surcharges; unlimited = can exceed baseline CPU for extra cost"
  type        = string
  default     = "standard"
}

variable "office_hours" {
  description = <<-EOT
    Optional: stop the instance outside working hours to cut compute cost by ~65%.
    Only enable this if preprod does NOT need to be on 24x7 (e.g. no overnight charger tests).
    Cron fields are EventBridge Scheduler syntax in the given timezone.
  EOT
  type = object({
    enabled  = bool
    start    = string
    stop     = string
    timezone = string
  })
  default = {
    enabled  = false
    start    = "cron(0 8 ? * MON-SAT *)"  # 08:00 Mon-Sat
    stop     = "cron(0 21 ? * MON-SAT *)" # 21:00 Mon-Sat (stopped all Sunday)
    timezone = "Asia/Kolkata"
  }
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
