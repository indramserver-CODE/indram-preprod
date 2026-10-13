"""
app/routers/sessions.py
-----------------------
Society admin only.

GET /api/sessions/active      — all active sessions with live charger status
GET /api/sessions/completed   — completed sessions, filter by month (YYYY-MM)
"""

from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, outerjoin
from pydantic import BaseModel

from app.database import get_db
from app.models.session import ChargingSession
from app.models.charger import Charger
from app.models.flat import Flat
from app.models.user import SocietyAdmin, User
from app.schemas.session import SessionOut
from app.dependencies.auth import require_society_admin

router = APIRouter()


class ActiveSessionOut(BaseModel):
    # Session fields
    session_id:     int
    charger_id:     str
    flat_number:    str | None
    rfid_uid:       str | None
    start_kwhr:     Decimal | None
    status:         str
    started_at:     str
    # Live charger status fields
    charger_status: str | None
    voltage:        Decimal | None
    current:        Decimal | None
    energy_kwh:     Decimal | None
    duration_min:   int | None
    temperature_c:  Decimal | None
    fault_code:     str | None

    model_config = {"from_attributes": True}


async def _get_society_id(user: User, db: AsyncSession) -> int:
    result = await db.execute(
        select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id)
    )
    society_id = result.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned to this admin")
    return society_id


@router.get("/active", response_model=list[ActiveSessionOut])
async def get_active_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    from app.models.session import ChargerStatus
    society_id = await _get_society_id(current_user, db)

    result = await db.execute(
        select(
            ChargingSession.session_id,
            ChargingSession.charger_id,
            Flat.flat_number,
            ChargingSession.rfid_uid,
            ChargingSession.start_kwhr,
            ChargingSession.status,
            ChargingSession.started_at,
            ChargerStatus.charger_status,
            ChargerStatus.voltage,
            ChargerStatus.current,
            ChargerStatus.energy_kwh,
            ChargerStatus.duration_min,
            ChargerStatus.temperature_c,
            ChargerStatus.fault_code,
        )
        .join(Charger, ChargingSession.charger_id == Charger.charger_id)
        .join(Flat, Charger.flat_id == Flat.id)
        .outerjoin(ChargerStatus, ChargingSession.charger_id == ChargerStatus.charger_id)
        .where(
            Flat.society_id == society_id,
            ChargingSession.status == "active",
        )
        .order_by(ChargingSession.started_at.desc())
    )
    rows = result.all()
    return [
        ActiveSessionOut(
            session_id=r.session_id,
            charger_id=r.charger_id,
            flat_number=r.flat_number,
            rfid_uid=r.rfid_uid,
            start_kwhr=r.start_kwhr,
            status=r.status,
            started_at=r.started_at.isoformat() if r.started_at else None,
            charger_status=r.charger_status,
            voltage=r.voltage,
            current=r.current,
            energy_kwh=r.energy_kwh,
            duration_min=r.duration_min,
            temperature_c=r.temperature_c,
            fault_code=r.fault_code,
        )
        for r in rows
    ]


@router.get("/completed", response_model=list[SessionOut])
async def get_completed_sessions(
    month: str = Query(default=None, description="Month in YYYY-MM format, defaults to current month"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    society_id = await _get_society_id(current_user, db)

    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"

    try:
        year, mon = map(int, month.split("-"))
        start = date(year, mon, 1)
        end   = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    result = await db.execute(
        select(ChargingSession)
        .join(Charger, ChargingSession.charger_id == Charger.charger_id)
        .join(Flat, Charger.flat_id == Flat.id)
        .where(
            Flat.society_id == society_id,
            ChargingSession.status.in_([
                "charging_ended",
                "charging_ended_error",
                "charging_stopped_by_admin",
            ]),
            ChargingSession.ended_at >= start,
            ChargingSession.ended_at < end,
        )
        .order_by(ChargingSession.ended_at.desc())
    )
    return result.scalars().all()