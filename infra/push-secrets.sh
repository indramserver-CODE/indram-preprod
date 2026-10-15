#!/usr/bin/env bash
# Write the application secrets to SSM Parameter Store as SecureStrings.
#
#   infra/push-secrets.sh .env.preprod            # env name defaults to preprod
#   infra/push-secrets.sh .env.preprod preprod
#
# Reads KEY=value lines from the given file for the keys listed below only,
# trims trailing whitespace, and never prints a value. Requires AWS CLI
# credentials with ssm:PutParameter on /indram/<env>/*.
set -euo pipefail

FILE="${1:?usage: push-secrets.sh <env-file> [env-name]}"
ENV_NAME="${2:-preprod}"
PREFIX="/indram/${ENV_NAME}"

SECRET_KEYS=(
  DATABASE_URL
  SECRET_KEY
  MQTT_HOST
  MQTT_USERNAME
  MQTT_PASSWORD
  GMAIL_USER
  GMAIL_APP_PASSWORD
  CMD_AUTH_TOKEN
  SUPER_ADMIN_EMAIL
  SUPER_ADMIN_PASSWORD
)

[[ -r "$FILE" ]] || { echo "cannot read $FILE" >&2; exit 1; }

set_count=0
for key in "${SECRET_KEYS[@]}"; do
  value=$(grep -m1 "^${key}=" "$FILE" | cut -d= -f2- | sed -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' || true)
  if [[ -z "$value" ]]; then
    echo "skip  $key (empty or missing)"
    continue
  fi
  if [[ "$key" == "SECRET_KEY" && "$value" == "replace-with-a-long-random-secret" ]]; then
    echo "ERROR $key is still the placeholder; generate one with:" >&2
    echo "      python3 -c 'import secrets;print(secrets.token_hex(32))'" >&2
    exit 1
  fi
  aws ssm put-parameter --overwrite --type SecureString \
      --name "${PREFIX}/${key}" --value "$value" >/dev/null
  echo "set   $key"
  set_count=$((set_count + 1))
done

echo "done: ${set_count} parameters written under ${PREFIX}/"
