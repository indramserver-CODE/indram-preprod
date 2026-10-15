# Preprod deployment: EC2 + Terraform + GitHub Actions

This document describes how the preprod environment is provisioned and how every
merge to `main` is rolled out. Everything referenced here lives in this repository:

| Path | What it is |
|---|---|
| `infra/` | Terraform for all AWS resources (one EC2 host, ECR, S3, IAM, SSM parameters, DNS) |
| `infra/bootstrap/` | One-time Terraform state bucket |
| `deploy/` | Files that run **on the EC2 host**: `compose.yml`, `Caddyfile`, `deploy.sh`, `migrate.sh` |
| `.github/workflows/deploy.yml` | Build → push → roll out on every push to `main` |
| `.github/workflows/infra.yml` | Terraform plan on PRs, apply on `main` behind an approval |
| `infra/push-secrets.sh` | Writes the application secrets to SSM Parameter Store; the only way secrets enter AWS |

---

## 1. Architecture

```mermaid
flowchart LR
    subgraph GitHub
        GH[GitHub Actions<br/>deploy.yml]
    end

    subgraph AWS["AWS ap-south-1"]
        OIDC[IAM OIDC role<br/>indram-preprod-github-deploy]
        ECR[(ECR<br/>indram-preprod-api)]
        S3[(S3<br/>indram-preprod-artifacts)]
        SSMP[(SSM Parameter Store<br/>/indram/preprod/*)]
        SSM[SSM Run Command]

        subgraph EC2["EC2 t4g.micro Graviton (Ubuntu 24.04 arm64, Elastic IP)"]
            direction TB
            Caddy[Caddy :80/:443<br/>auto TLS]
            API[indram-api container<br/>uvicorn :8000<br/>1 worker]
            WWW[/opt/indram/www/current<br/>React build/]
            Caddy -->|api.preprod.*| API
            Caddy -->|app.preprod.*| WWW
        end
    end

    subgraph External
        Neon[(Neon PostgreSQL)]
        HiveMQ[HiveMQ Cloud MQTT]
        Gmail[Gmail SMTP]
    end

    Users((Browsers /<br/>Chargers)) -->|HTTPS| Caddy

    GH -->|assume role via OIDC| OIDC
    GH -->|docker push :sha| ECR
    GH -->|release-sha.tgz| S3
    GH -->|send-command deploy.sh sha| SSM
    SSM -->|runs as root| EC2
    EC2 -->|pull image| ECR
    EC2 -->|fetch bundle| S3
    EC2 -->|render .env| SSMP
    API --> Neon
    API --> HiveMQ
    API --> Gmail
```

**Why Graviton (arm64).** `t4g.micro` is the cheapest always-on instance AWS sells in
Mumbai. The CI builds the image for arm64 through QEMU; every pinned Python dependency
ships an arm64 wheel, so nothing is compiled during the build. Switching back to x86 is
one variable (`instance_type = "t3.micro"`); the AMI and the Docker platform follow it.

**Why one EC2 host.** The API runs the MQTT subscriber and the billing scheduler in
process, and both must run on exactly one instance (`ENABLE_MQTT`, `ENABLE_SCHEDULER`,
and a single MQTT client id). A single box with a stop-then-start rollout matches that
constraint without any ECS/ALB machinery.

**No SSH, no static keys.** Port 22 is closed. GitHub reaches the host through SSM Run
Command, and authenticates to AWS with an OIDC-federated role scoped to this repository.
Humans use SSM Session Manager (`aws ssm start-session --target <instance-id>`).

**Secrets never touch GitHub or Terraform.** All runtime config lives in SSM Parameter
Store under `/indram/preprod/`. Non-secret settings are Terraform-managed `String`
parameters. Secrets are `SecureString` parameters written only by `infra/push-secrets.sh`
and are deliberately *not* Terraform resources: the AWS provider reads every managed
parameter back decrypted into state, so managing them would put every secret into the
state bucket and into any saved plan file. `deploy.sh` renders the whole prefix into
`/opt/indram/.env` on the host at deploy time. GitHub only holds non-secret *variables*
(role ARNs, instance id, bucket names, domains).

**Three GitHub roles, three trust policies.** The approval gates are enforced by AWS, not
just by the workflow file:

| Role | Trusted OIDC subjects | Permissions |
|---|---|---|
| `indram-preprod-github-plan` | any PR, pushes to `main` | `ReadOnlyAccess` + write the state lock file |
| `indram-preprod-github-deploy` | pushes to `main`, the `preprod` environment | push to ECR, upload bundle, `ssm:SendCommand` on the one instance |
| `indram-preprod-github-infra` | the `preprod-infra` environment only | `PowerUserAccess` + IAM limited to `indram-preprod-*` resources |

A PR job can only ever obtain the plan role. The infra role is unreachable without a
`preprod-infra` approval, because no other subject is in its trust policy.

**Permissions boundary.** Every role in this stack carries `indram-preprod-boundary`.
The infra role may only attach policies to roles that have the boundary, and the boundary
itself denies editing the boundary or removing it from a role. So even if a policy like
`AdministratorAccess` were attached to a CI role, its effective permissions stay capped at
"PowerUser plus IAM on this stack's own resources". Changing the boundary requires a human
with admin credentials running Terraform locally.

---

## 2. Deployment flow (every push to `main`)

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant GH as GitHub Actions
    participant ECR as ECR
    participant S3 as S3 artifacts
    participant SSM as SSM Run Command
    participant EC2 as EC2 host (deploy.sh)
    participant PS as SSM Parameter Store

    Dev->>GH: git push main
    GH->>GH: test — pytest tests/
    par build-backend
        GH->>ECR: docker build + push :<sha>, :preprod-latest
    and build-release-bundle
        GH->>GH: npm ci && vite build (VITE_API_BASE=https://api.preprod…)
        GH->>S3: release-<sha>.tgz = deploy/ + migrations/ + www/
    end
    GH->>SSM: send-command "fetch bundle; deploy.sh <sha>"
    SSM->>EC2: run as root
    EC2->>PS: get-parameters-by-path /indram/preprod/ --with-decryption
    EC2->>EC2: write /opt/indram/.env
    EC2->>ECR: docker pull <sha>
    EC2->>EC2: record previous image tag
    opt RUN_MIGRATIONS=true
        EC2->>EC2: migrate.sh apply (pending NNN_*.sql)
    end
    EC2->>EC2: docker compose up -d api caddy (stop old → start new)
    EC2->>EC2: poll /health up to 90 s
    alt healthy
        EC2->>EC2: www/current → <sha> (frontend goes live)
        EC2->>EC2: prune releases older than last 3
        EC2-->>SSM: exit 0
    else unhealthy
        EC2->>EC2: docker compose up -d api with previous tag (rollback)
        EC2-->>SSM: exit 1
    end
    SSM-->>GH: command status + stdout
    GH->>GH: smoke — curl api /health and app /
```

Pipeline jobs and their gates:

| Job | Runs when | Fails the deploy if |
|---|---|---|
| `test` | always | `pytest` fails |
| `build-backend` | not a redeploy | image build/push fails |
| `build-release-bundle` | always | frontend build or upload fails |
| `deploy` | both builds green; `preprod` environment | `deploy.sh` exits non-zero (health gate) |
| `smoke` | after deploy | public API/health or app URL not reachable |

### What happens on the host, step by step

`deploy/deploy.sh <sha>` is idempotent and is the only thing SSM runs:

1. Render `/opt/indram/.env` from Parameter Store (mode 600).
2. Log in to ECR and pull `indram-preprod-api:<sha>`. Save the currently running tag to `/opt/indram/previous_tag`.
3. If the parameter `RUN_MIGRATIONS` is `true`, apply pending files from `migrations/NNN_*.sql` in order, each in its own transaction, tracked in table `schema_migrations`.
4. Copy the frontend build to `/opt/indram/www/<sha>` (not live yet).
5. `docker compose up -d` with the new image. Compose stops the old API container and starts the new one. Caddy keeps running, so TLS and the old frontend stay up during the 5 to 10 seconds the API restarts.
6. Poll `/health` inside the container for up to 90 seconds.
7. **Healthy:** flip the `www/current` symlink so the new frontend goes live together with the new API. **Unhealthy:** dump the last 100 log lines, restart the previous image, and exit 1 so the GitHub job goes red.
8. Keep the last 3 releases on disk, prune dangling images.

Directory layout on the host:

```
/etc/indram.conf                 ENV_NAME, AWS_REGION, ECR_REPO_URL, APP_DOMAIN, API_DOMAIN (from user_data)
/opt/indram/.env                 rendered secrets, rewritten on every deploy
/opt/indram/release/<sha>/       unpacked bundle: deploy/, migrations/, www/
/opt/indram/release/current  ->  live release (compose project runs from here)
/opt/indram/www/<sha>/           frontend build
/opt/indram/www/current      ->  what Caddy serves
/opt/indram/previous_tag         last known-good image tag
```

### Rollback

- **Fast:** Actions → *Deploy preprod* → *Run workflow* on `main` → set `image_tag` to a previous commit SHA. The image build is skipped and the old API image is redeployed; the bundle (frontend + scripts) is rebuilt from `main`. The tag must be a plain git SHA; anything else is rejected before any job runs. Dispatching from a branch other than `main` is refused by the deploy role's trust policy.
- **Clean:** `git revert` and push to `main`. Normal pipeline.
- **Automatic:** a failed health gate restarts the previous image on its own, as shown in the diagram.

---

## 3. One-time setup

### 3.1 Bootstrap the state bucket (local, once)

```bash
cd infra/bootstrap
terraform init && terraform apply          # creates s3://indram-terraform-state
```

### 3.2 First `terraform apply` (local, once)

The GitHub roles are created by Terraform, so the first apply has to run with your own
AWS credentials.

```bash
cd infra
cp backend.hcl.example backend.hcl         # edit if you changed the bucket name
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars                   # domains, optional route53_zone_id
terraform init -backend-config=backend.hcl
terraform apply
terraform output github_variables
```

If the AWS account already has the `token.actions.githubusercontent.com` OIDC provider
(for example because another repo uses it), set `create_github_oidc_provider = false`.

### 3.3 Fill in the secrets

Secrets are not Terraform resources. Put the ten values in a local file, for example
`.env.preprod` (ignored by git), one `KEY=value` per line, then:

```bash
infra/push-secrets.sh .env.preprod
```

The script writes exactly these keys as `SecureString` under `/indram/preprod/`, trims
trailing whitespace, never prints a value, and refuses the placeholder `SECRET_KEY`:

```
DATABASE_URL  SECRET_KEY  MQTT_HOST  MQTT_USERNAME  MQTT_PASSWORD
GMAIL_USER  GMAIL_APP_PASSWORD  CMD_AUTH_TOKEN  SUPER_ADMIN_EMAIL  SUPER_ADMIN_PASSWORD
```

Generate `SECRET_KEY` with `python3 -c 'import secrets;print(secrets.token_hex(32))'`.
Re-run the script any time to rotate a value, then redeploy so `.env` is re-rendered.

Non-secret settings (`ENABLE_MQTT`, `ENABLE_SCHEDULER`, `MQTT_CLIENT_ID`, `RUN_MIGRATIONS`,
…) are in the `app_parameters` map in `infra/variables.tf`; change them there and apply.
Any key in that map or in the secret list becomes an environment variable in the container.

> **MQTT client id.** preprod and prod share the HiveMQ cluster. The app now reads
> `MQTT_CLIENT_ID` (default `evc-server-prod`); preprod is set to `evc-server-preprod`.
> Two connections with the same id kick each other off the broker (the "Code 7" issue).

### 3.4 Baseline the migration tracker (only for an existing database)

`migrations/001_*.sql` truncates tables. On a database that was already set up by hand,
mark every file as applied without running it, once:

```bash
aws ssm start-session --target <instance-id>
sudo -i
export DATABASE_URL="$(grep ^DATABASE_URL= /opt/indram/.env | cut -d= -f2-)"
/opt/indram/release/current/deploy/migrate.sh baseline
```

Then set the parameter `RUN_MIGRATIONS` to `true` so future deploys apply new files.

### 3.5 GitHub configuration

Create two environments under **Settings → Environments**:

| Environment | Purpose | Protection |
|---|---|---|
| `preprod` | the `deploy` job | set *Deployment branches* to `main` only; required reviewer optional |
| `preprod-infra` | the Terraform `apply` job | **required reviewer** (this is the gate the infra role's trust policy relies on); deployment branches `main` only |

Add these **variables** (not secrets) at repository or environment level, taken from
`terraform output github_variables` plus the state bucket:

```
AWS_REGION            ap-south-1
AWS_PLAN_ROLE_ARN     arn:aws:iam::…:role/indram-preprod-github-plan
AWS_DEPLOY_ROLE_ARN   arn:aws:iam::…:role/indram-preprod-github-deploy
AWS_INFRA_ROLE_ARN    arn:aws:iam::…:role/indram-preprod-github-infra
EC2_INSTANCE_ID       i-…
ECR_REPOSITORY        indram-preprod-api
ARTIFACTS_BUCKET      indram-preprod-artifacts
APP_DOMAIN            app.preprod.indram.in
API_DOMAIN            api.preprod.indram.in
TF_STATE_BUCKET       indram-terraform-state
ROUTE53_ZONE_ID       (empty if DNS is managed elsewhere)
```

### 3.6 DNS and TLS

Point `APP_DOMAIN` and `API_DOMAIN` at `terraform output public_ip` (or set
`route53_zone_id` and let Terraform do it). Caddy obtains Let's Encrypt certificates
automatically on first request once DNS resolves; nothing else to configure.

### 3.7 First deploy

Push to `main` (or run *Deploy preprod* manually). Watch the `deploy` job log: it prints
the full `deploy.sh` output from the host.

---

## 4. Cost

Everything here is pay-as-you-go. Approximate always-on monthly cost in ap-south-1:

| Item | USD / month | Notes |
|---|---|---|
| EC2 `t4g.micro` (2 vCPU, 1 GB) | ~4.1 | `cpu_credits = "standard"` so it never bills burst surcharges |
| EBS 16 GB gp3 | ~1.5 | |
| Public IPv4 (Elastic IP) | ~3.65 | Charged by AWS for every public IPv4 since Feb 2024, attached or not. Unavoidable for a public HTTPS host. |
| ECR (last 5 images) + S3 (7-day bundles, state) | < 0.5 | Same-region pulls are free |
| SSM Parameter Store, Run Command, Session Manager, OIDC, KMS default key | 0 | Standard tier, no charge |
| Route53 | 0.50 per hosted zone | Only if you create a *new* zone. Using an existing zone or external DNS costs nothing. |
| CloudWatch | 0 | No log shipping or alarms are configured |
| **Total** | **~10** | `terraform output estimated_monthly_usd` prints this for your chosen size |

GitHub Actions: free for public repos; private repos get 2 000 minutes/month on the free
plan. A deploy takes roughly 6 to 8 minutes (the arm64 build under QEMU is the slow part,
cached between runs), so about 250 deploys/month fit in the free allowance.

Neon and HiveMQ Cloud stay on their free tiers as today.

### Ways to go lower

| Option | Saves | Trade-off |
|---|---|---|
| **Office-hours schedule** (`office_hours.enabled = true` in tfvars) | ~2.7 / month (compute off ~65% of the week) | Preprod is down nights and Sundays. Do not enable if chargers must reach preprod overnight. EBS and the IP are still billed while stopped. |
| **AWS Free Tier** | up to all of it for 6 months | Accounts created after 15 July 2025 get USD 100 to 200 in credits for six months. Older accounts get 750 h/month of `t3.micro` (x86, ~8/month) and 750 h of public IPv4 for the first 12 months. Check Billing → Free Tier in the console. |
| **1-year Compute Savings Plan**, no upfront | ~30% of compute | Commitment for 12 months |
| Spot instance | ~70% of compute | Can be reclaimed with 2 minutes notice; not recommended for something that should "just work" |

### If 1 GB RAM turns out to be tight

The host runs Docker, the API (one uvicorn worker), Caddy and the SSM agent in about
600 MB, with a 1 GB swap file as headroom. If `docker stats` shows the API near its
limit during PDF/Excel generation, set `instance_type = "t4g.small"` (2 GB, ~8/month).
The change is a brief stop/start, no rebuild.

---

## 5. Day-2 operations

| Task | How |
|---|---|
| Shell on the box | `aws ssm start-session --target <instance-id>` |
| API logs | `docker logs -f indram-api` |
| Caddy logs | `docker logs -f indram-caddy` |
| Change a non-secret setting | edit `app_parameters` in `infra/variables.tf`, open a PR (plan is commented), merge, approve apply, then redeploy so `.env` is re-rendered |
| Rotate a secret | update `.env.preprod`, run `infra/push-secrets.sh .env.preprod`, then redeploy |
| Change the permissions boundary or a role's boundary | local `terraform apply` with admin credentials; CI is denied this on purpose |
| Migration status | `migrate.sh status` on the host |
| Resize the instance | change `instance_type`, apply (brief stop/start) |
| Rebuild the host from scratch | `terraform taint aws_instance.app && terraform apply`, then redeploy. The Elastic IP is kept. |

---

## 6. Changes made to the application for this

- `frontend-WebsiteTheme/src/api/client.js` reads `VITE_API_BASE` at build time; falls back to the old hostname logic.
- `app/config.py` gains `CORS_ORIGINS` and `MQTT_CLIENT_ID`; `app/main.py` and `app/mqtt_subscriber.py` read them from settings.
- `Dockerfile` has a `HEALTHCHECK`; `.dockerignore` excludes the frontend, infra and deploy folders from the build context.
- `env.example` documents every variable for local development.
- The previous ECS/S3 workflow was replaced; it synced a `./frontend/` directory that does not exist and never ran a frontend build.
