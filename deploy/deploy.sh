#!/usr/bin/env bash
# Rolls out one release on the EC2 host. Invoked by GitHub Actions through
# SSM Run Command as:   /opt/indram/release/<sha>/deploy/deploy.sh <sha>
#
# Layout on the host:
#   /opt/indram/.env                 rendered from SSM Parameter Store on every deploy
#   /opt/indram/release/<sha>/       unpacked release bundle (deploy/, migrations/, www/)
#   /opt/indram/release/current  ->  symlink to the live release
#   /opt/indram/www/<sha>/           frontend build for that release
#   /opt/indram/www/current      ->  symlink served by Caddy
#   /opt/indram/previous_tag         last known-good image tag, used for rollback
set -euo pipefail

SHA="${1:?usage: deploy.sh <image_tag>}"
[[ "$SHA" =~ ^[0-9a-f]{7,40}$ ]] || { echo "deploy.sh: image tag must be a git SHA, got '$SHA'" >&2; exit 2; }
BASE=/opt/indram
RELEASE="$BASE/release/$SHA"
ENV_FILE="$BASE/.env"
PREV_FILE="$BASE/previous_tag"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

# These are written to /etc/indram.conf by Terraform user_data.
# shellcheck disable=SC1091
source /etc/indram.conf   # ENV_NAME, AWS_REGION, ECR_REPO_URL, APP_DOMAIN, API_DOMAIN

[[ -d "$RELEASE" ]] || { log "release dir $RELEASE missing"; exit 1; }

# ── 1. Render .env from SSM Parameter Store ──────────────────────────────
log "rendering $ENV_FILE from /indram/$ENV_NAME/"
umask 077
aws ssm get-parameters-by-path \
    --region "$AWS_REGION" --path "/indram/$ENV_NAME/" --with-decryption \
    --query 'Parameters[].[Name,Value]' --output text \
  | awk -F'\t' '{ n=$1; sub(/.*\//,"",n); v=$2; print n "=" v }' > "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
# Values may contain spaces (Gmail app passwords do), so never `source` the file.
envget() { grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2- || true; }
RUN_MIGRATIONS=$(envget RUN_MIGRATIONS)
export DATABASE_URL="$(envget DATABASE_URL)"

# Values compose.yml needs that are not app settings
export API_IMAGE="$ECR_REPO_URL:$SHA" APP_DOMAIN API_DOMAIN

# ── 2. Pull the new image ─────────────────────────────────────────────────
log "logging in to ECR"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ECR_REPO_URL%%/*}" >/dev/null
log "pulling $API_IMAGE"
docker pull --quiet "$API_IMAGE"

CURRENT_TAG=$(docker inspect --format '{{.Config.Image}}' indram-api 2>/dev/null | sed 's/.*://' || true)
[[ -n "$CURRENT_TAG" ]] && echo "$CURRENT_TAG" > "$PREV_FILE"

# ── 3. Migrations (opt-in via SSM param RUN_MIGRATIONS=true) ─────────────
if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
  log "running migrations"
  "$RELEASE/deploy/migrate.sh" apply
else
  log "RUN_MIGRATIONS != true, skipping migrations"
fi

# ── 4. Stage frontend (not live yet) ──────────────────────────────────────
mkdir -p "$BASE/www"
rm -rf "$BASE/www/$SHA"
cp -r "$RELEASE/www" "$BASE/www/$SHA"

# ── 5. Swap API container (stop-then-start: single MQTT client id) ───────
ln -sfn "$RELEASE" "$BASE/release/current"
cd "$BASE/release/current/deploy"
log "starting api $SHA"
docker compose up -d --remove-orphans api caddy

# ── 6. Health gate ────────────────────────────────────────────────────────
log "waiting for api health (timeout ${HEALTH_TIMEOUT}s)"
ok=0
for ((i=0; i<HEALTH_TIMEOUT; i+=3)); do
  if docker exec indram-api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)" 2>/dev/null; then
    ok=1; break
  fi
  sleep 3
done

if [[ $ok -ne 1 ]]; then
  log "HEALTH CHECK FAILED for $SHA"
  docker logs --tail 100 indram-api || true
  if [[ -s "$PREV_FILE" ]]; then
    PREV=$(cat "$PREV_FILE")
    log "rolling back api to $PREV"
    export API_IMAGE="$ECR_REPO_URL:$PREV"
    docker compose up -d api
  fi
  exit 1
fi

# ── 7. Frontend goes live only after the API is healthy ──────────────────
ln -sfn "$SHA" "$BASE/www/current"
log "frontend switched to $SHA"

# ── 8. Housekeeping: keep last 3 releases ────────────────────────────────
ls -1dt "$BASE/release"/*/ 2>/dev/null | tail -n +4 | xargs -r rm -rf
ls -1dt "$BASE/www"/*/     2>/dev/null | tail -n +4 | xargs -r rm -rf
docker image prune -af --filter "until=72h" >/dev/null || true

log "deploy of $SHA complete"
