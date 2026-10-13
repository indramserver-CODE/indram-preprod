# INDRAM — EV Charging Management Platform

A full-stack platform for managing EV charger deployments in multi-tenant residential societies. Handles charger provisioning, real-time MQTT telemetry, RFID access control, session tracking, and meter-wise billing.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy (async), asyncpg |
| Database | PostgreSQL via [Neon](https://neon.tech) |
| MQTT Broker | HiveMQ Cloud (TLS, port 8883) |
| Frontend | React 19, React Router 7, Vite 8, Chart.js |
| Email | Gmail SMTP |
| File Storage | AWS S3 (optional — for bill PDFs) |

---

## Project Structure

```
indramev/
├── app/                        # FastAPI backend
│   ├── models/                 # SQLAlchemy ORM models
│   ├── routers/                # API route handlers
│   ├── schemas/                # Pydantic request/response schemas
│   ├── services/               # Business logic (billing, email, PDF)
│   ├── dependencies/           # Auth guards
│   ├── config.py               # All env-var config via pydantic-settings
│   ├── database.py             # SQLAlchemy async engine + session
│   ├── db.py                   # asyncpg raw connection pool
│   ├── main.py                 # App entry point, lifespan, router registration
│   ├── mqtt_subscriber.py      # Inbound MQTT event handler
│   ├── mqtt_commands.py        # Outbound MQTT command publisher
│   └── ack_waiters.py          # In-memory MQTT ack registry
├── frontend-WebsiteTheme/      # React frontend (Vite)
│   ├── src/
│   │   ├── api/                # Authenticated fetch client
│   │   ├── components/         # Shared UI components (Modal, Topbar, etc.)
│   │   ├── context/            # React context (Auth, Toast)
│   │   ├── pages/
│   │   │   ├── superadmin/     # Super admin pages
│   │   │   └── admin/          # Society admin pages
│   │   └── styles/             # CSS modules + global theme
│   ├── package.json
│   └── vite.config.js
├── requirements.txt
├── env.example
└── Dockerfile
```

---

## Prerequisites

Before running locally, make sure you have the following installed:

- **Python 3.12 or 3.13** — [python.org/downloads](https://www.python.org/downloads/)
  - Windows: check "Add Python to PATH" during installation
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **Git** — [git-scm.com](https://git-scm.com/)
- A **Neon PostgreSQL** database — [neon.tech](https://neon.tech) (free tier works)
- A **HiveMQ Cloud** MQTT broker — [hivemq.com/cloud](https://www.hivemq.com/cloud/) (free tier works)

---

## First-Time Setup

### 1. Clone the repository

```bash
git clone https://github.com/indramserver-CODE/indramev.git
cd indramev
```

---

### 2. Backend — Python virtual environment

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> **Python 3.13 on Windows?** If you see an `asyncpg` build error, run:
> ```bash
> pip install asyncpg==0.30.0
> pip install -r requirements.txt
> ```

---

### 3. Environment variables

Copy the example file and fill in your values:

**macOS / Linux:**
```bash
cp env.example .env
```

**Windows:**
```bash
copy env.example .env
```

Open `.env` in any text editor and set the following:

```env
# ── Database ──────────────────────────────────────────────────────────────
# Your Neon connection string. Copy it from Neon dashboard → Connection Details.
# Make sure to include ?sslmode=require at the end.
DATABASE_URL=postgresql+asyncpg://user:password@ep-xxx.neon.tech/neondb?ssl=require

# ── MQTT (HiveMQ Cloud) ───────────────────────────────────────────────────
# From HiveMQ Cloud → Cluster → Connection Settings
ENABLE_MQTT=false                          # Set to true only if you have charger hardware
MQTT_HOST=your-cluster.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=your-hivemq-username
MQTT_PASSWORD=your-hivemq-password
MQTT_USE_TLS=True

# ── JWT Auth ──────────────────────────────────────────────────────────────
# Generate a strong random string: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-a-long-random-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480            # 8 hours

# ── Password reset ────────────────────────────────────────────────────────
PASSWORD_RESET_EXPIRE_MINUTES=30
FRONTEND_URL=http://localhost:5173         # Vite dev server URL

# ── AWS S3 (optional — bill PDFs) ─────────────────────────────────────────
# Leave blank to skip S3 upload. Bills will still be generated but not stored.
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET_NAME=

# ── Email (Gmail SMTP) ────────────────────────────────────────────────────
# Use an App Password, not your main Gmail password.
# Gmail → Account → Security → 2-Step Verification → App Passwords
GMAIL_USER=yourgmail@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# ── MQTT command auth ─────────────────────────────────────────────────────
# Must match CMD_AUTH_TOKEN hardcoded in the charger firmware
CMD_AUTH_TOKEN=

# ── Billing ───────────────────────────────────────────────────────────────
BILLING_DAY_OF_MONTH=1

# ── Super Admin Seed ──────────────────────────────────────────────────────
# On first startup, if no super_admin exists in the DB, one is created.
SUPER_ADMIN_EMAIL=admin@yourdomain.com
SUPER_ADMIN_PASSWORD=YourStrongPassword123
```

> **`DATABASE_URL` format for asyncpg:**
> Neon gives you a URL starting with `postgresql://`. Change it to `postgresql+asyncpg://` — the `+asyncpg` driver prefix is required.

---

### 4. Frontend — Node dependencies

```bash
cd frontend-WebsiteTheme
npm install
cd ..
```

---

## Running Locally

You need **two terminal windows** open simultaneously every time.

### Terminal 1 — Backend (FastAPI)

```bash
# From the repo root
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

uvicorn app.main:app --reload --port 8000
```

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO      app.main: Database pool created
INFO      app.main: Super admin seeded: admin@yourdomain.com   ← first run only
INFO:     Application startup complete.
```

> The backend automatically creates all database tables on first startup via `Base.metadata.create_all`. No migration commands needed.

---

### Terminal 2 — Frontend (Vite dev server)

```bash
cd frontend-WebsiteTheme
npm run dev
```

You should see:

```
  VITE v8.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
```

---

### Open the app

Go to **[http://localhost:5173](http://localhost:5173)** in your browser.

Log in with the `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASSWORD` from your `.env`.

---

## First Steps After Login

Once you're in as super admin, follow this order to set up a society end-to-end:

1. **Societies** → Create a society (set the INDRAM rate ₹/kWh)
2. **Flats** → Upload a CSV of flats for that society
   - Required columns: `flat_number`, `owner_name` (optional), `email` (optional)
3. **Meters** → Add the MSEB electricity meters for that society
   - Fields: Meter Number, Label (e.g. "Block A"), Sanctioned Load, Location
4. **Chargers** → Upload a CSV assigning chargers to flats and meters
   - Required columns: `flat_number`, `charger_id`, `meter_number`
5. **RFID** → Upload a CSV of RFID cards per flat
   - Required columns: `flat_number`, `uid` | Optional: `label`
6. **Admins** → Create a society admin account for that society

Then log out and log back in as the society admin to test the admin portal.

---

## API Documentation

The backend auto-generates interactive API docs. With the backend running:

- **Swagger UI** → [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc** → [http://localhost:8000/redoc](http://localhost:8000/redoc)

Use the "Authorize" button in Swagger and paste a JWT from the login response to test authenticated endpoints.

---

## Domain Model

```
Society
  └── Meters (1:many)          ← MSEB electricity meter
        └── Chargers (1:many)  ← EV charging device
              └── Flat (1:1)   ← residential unit
  └── Flats (1:many)
        └── RFID Cards (max 3)
  └── MonthlyBills             ← one per meter per month
        └── FlatBills          ← one per flat per billing cycle
```

**Two user roles:**
- `super_admin` — manages societies, meters, flats, chargers, RFID, society admins
- `society_admin` — manages RFID activation, generates monthly bills, views sessions and usage

---

## Billing Formula

For each billing cycle (one meter, one month):

| Variable | Description |
|---|---|
| `B` | Total MSEB bill amount ₹ entered by society admin |
| `U` | Total units consumed (kWh) on that meter |
| `E = B ÷ U` | Effective unit rate including all MSEB taxes |
| `T` | Base tariff ₹/unit entered by society admin |
| `u` | Individual flat's units consumed |
| `I` | INDRAM rate ₹/kWh (set per society by super admin, default ₹1.50) |

**Per flat:**
```
bill_excl_taxes        = u × T
electricity_incl_tax   = u × E
mseb_taxes             = (u×E) − (u×T)
indram_charges         = u × I
total_payable          = (u×E) + (u×I)
```

---

## MQTT Topics

| Direction | Topic | Description |
|---|---|---|
| Charger → Server | `indram/charger/{id}/charging_started` | Session started |
| Charger → Server | `indram/charger/{id}/charging_ended` | Session ended normally |
| Charger → Server | `indram/charger/{id}/charging_ended_error` | Session ended with fault |
| Charger → Server | `indram/charger/{id}/charging_stopped_by_admin` | Admin deactivated charger |
| Charger → Server | `indram/charger/{id}/heartbeat` | 30s alive ping during session |
| Charger → Server | `indram/charger/{id}/status` | Retained telemetry every 30s |
| Server → Charger | `indram/charger/{id}/command` | DEACTIVATE / ACTIVE / ADDUID |

> Set `ENABLE_MQTT=false` in `.env` when developing without charger hardware. The app runs fully without an MQTT connection — only the subscriber background task is skipped.

---

## Stopping the App

Press `Ctrl+C` in both terminals.

```bash
deactivate    # exit the Python virtual environment
```

---

## Common Issues

**`[object Object]` appears in error toasts**
A FastAPI validation error returned an array in `detail`. This is a known frontend issue — check the browser console for the full error.

**`ModuleNotFoundError`**
Virtual environment not activated. Run `source venv/bin/activate` (macOS/Linux) or `venv\Scripts\activate` (Windows) first.

**`asyncpg` build error on Python 3.13 (Windows)**
```bash
pip install asyncpg==0.30.0
pip install -r requirements.txt
```

**`relation "users" does not exist`**
`create_all` ran before the models were imported. Make sure you're using the latest `main.py` where model imports happen before `create_all`.

**`there is no unique constraint matching given keys for referenced table "charging_sessions"`**
The `session_id` column on `ChargingSession` is missing `unique=True`. Add it to the model and drop/recreate the schema.

**Blank white screen in the browser**
An unhandled JavaScript error crashed the React app. Open browser DevTools → Console tab to see the error.

**`MQTT connection lost: getaddrinfo failed`**
Running on ECS? The Fargate task is in a private subnet or has no public IP assigned. See deployment notes.

**`MQTT connection lost: Code 7`**
Two instances of the app are running with the same MQTT client ID, or the keepalive timeout was missed. Make sure `--workers 1` in the Dockerfile and `keepalive=30` in the MQTT client constructor.

**Login works but pages show 401 / "Not authenticated"**
Token expired or `SECRET_KEY` changed between restarts. Log out and log back in.

**Bills generate but emails aren't sent**
Check `GMAIL_USER` and `GMAIL_APP_PASSWORD` in `.env`. The password must be a Gmail App Password (16 characters, spaces allowed), not your regular Gmail password. Ensure 2-Step Verification is enabled on the Gmail account.

**S3 upload silently fails**
S3 credentials are optional — if `S3_BUCKET_NAME` is empty, uploads are skipped without error. Bills still generate and emails still send with the PDF attached directly.

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | asyncpg connection string to Neon PostgreSQL |
| `ENABLE_MQTT` | | `false` | Set `true` to start the MQTT subscriber |
| `MQTT_HOST` | if MQTT | — | HiveMQ Cloud hostname |
| `MQTT_PORT` | if MQTT | `1883` | Use `8883` for TLS |
| `MQTT_USERNAME` | if MQTT | — | HiveMQ credentials |
| `MQTT_PASSWORD` | if MQTT | — | HiveMQ credentials |
| `MQTT_USE_TLS` | if MQTT | `false` | Set `true` for HiveMQ Cloud |
| `SECRET_KEY` | ✅ | — | JWT signing secret — use a long random string |
| `ALGORITHM` | | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | | `480` | Token lifetime (8 hours) |
| `PASSWORD_RESET_EXPIRE_MINUTES` | | `30` | Reset link lifetime |
| `FRONTEND_URL` | | `http://localhost:5173` | Used in password reset email links |
| `GMAIL_USER` | for email | — | Gmail address for sending bills |
| `GMAIL_APP_PASSWORD` | for email | — | Gmail App Password (not account password) |
| `AWS_REGION` | for S3 | `ap-south-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | for S3 | — | IAM credentials |
| `AWS_SECRET_ACCESS_KEY` | for S3 | — | IAM credentials |
| `S3_BUCKET_NAME` | for S3 | — | Bucket for bill PDF storage |
| `CMD_AUTH_TOKEN` | for MQTT cmds | — | Must match firmware `CMD_AUTH_TOKEN` |
| `BILLING_DAY_OF_MONTH` | | `1` | Day auto-billing triggers (scheduler WIP) |
| `SUPER_ADMIN_EMAIL` | first run | — | Seeded on startup if no super_admin exists |
| `SUPER_ADMIN_PASSWORD` | first run | — | Seeded on startup if no super_admin exists |
| `CORS_ORIGINS` | production | `*` | Comma-separated allowed origins |