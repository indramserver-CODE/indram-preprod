#!/usr/bin/env bash
# Cloud-init for the Indram app host. Installs Docker, AWS CLI, psql and the SSM
# agent, and writes /etc/indram.conf which deploy/deploy.sh sources.
# Everything else (compose, Caddy, scripts) ships in each release bundle.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

# ── Base packages ─────────────────────────────────────────────────────────
apt-get update
apt-get install -y ca-certificates curl gnupg unzip jq postgresql-client

# ── Docker CE + compose plugin ────────────────────────────────────────────
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker

# ── AWS CLI v2 ────────────────────────────────────────────────────────────
cd /tmp
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip && ./aws/install && rm -rf aws awscliv2.zip

# ── SSM agent (preinstalled as a snap on Ubuntu AMIs; make sure it runs) ──
snap start amazon-ssm-agent || true

# ── App layout + host config ──────────────────────────────────────────────
mkdir -p /opt/indram/release /opt/indram/www
cat > /etc/indram.conf <<CONF
ENV_NAME=${env_name}
AWS_REGION=${aws_region}
ECR_REPO_URL=${ecr_repo_url}
APP_DOMAIN=${app_domain}
API_DOMAIN=${api_domain}
ARTIFACTS_BUCKET=${artifacts}
CONF
chmod 0644 /etc/indram.conf

# Placeholder page so Caddy has something to serve before the first deploy
mkdir -p /opt/indram/www/bootstrap
echo '<h1>indram ${env_name}: waiting for first deploy</h1>' > /opt/indram/www/bootstrap/index.html
ln -sfn bootstrap /opt/indram/www/current

echo "user_data complete"
