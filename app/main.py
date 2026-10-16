"""
app/main.py
-----------
FastAPI application entry point.
"""

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Standard imports ───────────────────────────────────────
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from app.routers import tickets

from app.database import AsyncSessionLocal, Base
from app.models.user import User
from app.dependencies.auth import hash_password
from app.config import settings
from app.db import create_pool, close_pool

# ── Logging setup ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Seed Super Admin ───────────────────────────────────────
async def _seed_super_admin():
    email    = getattr(settings, "SUPER_ADMIN_EMAIL", None)
    password = getattr(settings, "SUPER_ADMIN_PASSWORD", None)

    if not email or not password:
        logger.warning("SUPER_ADMIN_EMAIL / SUPER_ADMIN_PASSWORD not set — skipping seed")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.role == "super_admin"))
        if result.scalar_one_or_none():
            return

        admin = User(
            email=email,
            hashed_password=hash_password(password),
            full_name="Super Admin",
            role="super_admin",
        )
        db.add(admin)
        await db.commit()
        logger.info("Super admin seeded: %s", email)


# ── Lifespan (startup + shutdown) ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await _seed_super_admin()

    pool = await create_pool()
    logger.info("Database pool created")

    from app.database import engine, Base
    # Explicitly import all models so SQLAlchemy registers them on Base.metadata
    # before create_all is called. Order matters — Meter must be imported before
    # Charger and MonthlyBill since both have FKs pointing to meters.
    from app.models.society  import Society           # noqa: F401
    from app.models.meter    import Meter             # noqa: F401
    from app.models.flat     import Flat              # noqa: F401
    from app.models.charger  import Charger           # noqa: F401
    from app.models.user     import User, SocietyAdmin  # noqa: F401
    from app.models.rfid     import RFIDCard          # noqa: F401
    from app.models.session  import ChargingSession   # noqa: F401
    from app.models.bill     import MonthlyBill, FlatBill, FlatBillSession, IndramBill, InvoiceCounter  # noqa: F401
    from app.models.ticket   import Ticket, TicketComment  # noqa: F401
    from app.models.command_log     import CommandLog, PendingCommand  # noqa: F401
    from app.models.password_reset  import PasswordResetToken          # noqa: F401
    from app.models.notification    import Notification                # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.ENABLE_SCHEDULER:
        from app.services.scheduler import start_scheduler
        start_scheduler()
    else:
        logger.info("Billing scheduler disabled on this instance (ENABLE_SCHEDULER != true)")

    mqtt_task = sweep_task = None
    if settings.ENABLE_MQTT:
        from app.mqtt_subscriber import run_mqtt_subscriber
        from app.services.charger_state import run_silent_sweeper
        mqtt_task  = asyncio.create_task(run_mqtt_subscriber(pool))
        sweep_task = asyncio.create_task(run_silent_sweeper(pool))   # marks silent chargers offline
        logger.info("MQTT subscriber started")
    else:
        logger.info("MQTT subscriber disabled on this instance (ENABLE_MQTT != true)")

    yield

    # Shutdown
    if settings.ENABLE_SCHEDULER:
        from app.services.scheduler import stop_scheduler
        stop_scheduler()

    for task in (mqtt_task, sweep_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    await close_pool()
    logger.info("Shutdown complete")


# ── App init ──────────────────────────────────────────────
app = FastAPI(
    title="EV Charger Management API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────
# Locally: CORS_ORIGINS is not set → defaults to "*" → open for development
# Production: CORS_ORIGINS comes from SSM Parameter Store → restricted to your domains
_cors_env = settings.CORS_ORIGINS.strip() or "*"

if _cors_env == "*":
    origins = ["*"]
    logger.info("CORS: open (development mode — all origins allowed)")
else:
    origins = [o.strip() for o in _cors_env.split(",")]
    logger.info("CORS: restricted to %s", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],   # lets the frontend read download filenames
)

# ── Routers ───────────────────────────────────────────────
from app.routers import auth, societies, flats, chargers, admin_users, sessions, usage, billing, notifications, society_settings, bulk_delete
from app.routers.meters import super_router as meters_super_router, society_router as meters_society_router
from app.routers.rfid import super_router as rfid_super_router   # RFID is super admin only (no /api/sa/rfid)
from app.routers.analytics import router_society as analytics_society_router, router_admin as analytics_admin_router
from app.routers.indram_bills import super_router as indram_super_router, society_router as indram_society_router

app.include_router(auth.router,              prefix="/api/auth",             tags=["Auth"])
app.include_router(admin_users.router,       prefix="/api/society-admins",   tags=["Admin Users"])
app.include_router(societies.router,         prefix="/api/societies",         tags=["Societies"])
app.include_router(bulk_delete.router,       prefix="/api/societies",         tags=["Delete all"])
app.include_router(flats.router,             prefix="/api/societies",         tags=["Flats"])
app.include_router(meters_super_router,      prefix="/api/meters",            tags=["Meters"])
app.include_router(chargers.router,          prefix="/api/chargers",          tags=["Chargers"])
app.include_router(rfid_super_router,        prefix="/api/rfid",              tags=["RFID"])
app.include_router(flats.router,             prefix="/api/sa",                tags=["SA Flats"])
app.include_router(meters_society_router,    prefix="/api/sa/meters",         tags=["SA Meters"])
app.include_router(sessions.router,          prefix="/api/sessions",          tags=["Sessions"])
app.include_router(usage.router,             prefix="/api/usage",             tags=["Usage"])
app.include_router(billing.router,           prefix="/api/billing",           tags=["Billing"])
app.include_router(indram_super_router,      prefix="/api/indram-bills",       tags=["Indram Bills"])
app.include_router(indram_society_router,    prefix="/api/sa/indram-bills",    tags=["SA Indram Bills"])
app.include_router(society_settings.router,  prefix="/api/sa/society",        tags=["SA Society Settings"])
app.include_router(notifications.router,     prefix="/api/notifications",      tags=["Notifications"])
app.include_router(tickets.router,           prefix="/api/tickets",            tags=["Tickets"])
app.include_router(analytics_society_router, prefix="/api/analytics/society", tags=["Analytics - Society"])
app.include_router(analytics_admin_router,   prefix="/api/analytics/admin",   tags=["Analytics - Admin"])


# ── Health check ──────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}