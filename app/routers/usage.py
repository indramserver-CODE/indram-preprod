"""
app/routers/usage.py
--------------------
Society admin only.

GET /api/usage?month=YYYY-MM  — units per flat for a given month
GET /api/usage/society         — get current admin's society info
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from decimal import Decimal

from app.database import get_db
from app.models.session import ChargingSession
from app.models.charger import Charger
from app.models.flat import Flat
from app.models.bill import FlatBill, MonthlyBill
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.dependencies.auth import require_society_admin

router = APIRouter()


class FlatUsageOut(BaseModel):
    flat_id: int
    flat_number: str
    owner_name: str | None
    total_units: Decimal
    session_count: int
    total_amount: Decimal = Decimal("0")   # billed total_payable for the month (0 if no bill yet)


class SocietyInfoOut(BaseModel):
    id: int
    name: str
    address: str | None
    indram_rate: Decimal | None = None


async def _get_society_id(user: User, db: AsyncSession) -> int:
    result = await db.execute(
        select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id)
    )
    society_id = result.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned to this admin")
    return society_id


@router.get("/society", response_model=SocietyInfoOut)
async def get_my_society(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    society_id = await _get_society_id(current_user, db)
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


@router.get("", response_model=list[FlatUsageOut])
async def get_usage_per_flat(
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
        end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    result = await db.execute(
        select(
            Flat.id.label("flat_id"),
            Flat.flat_number,
            Flat.owner_name,
            func.coalesce(func.sum(ChargingSession.units_consumed), 0).label("total_units"),
            func.count(ChargingSession.id).label("session_count"),
        )
        .select_from(Flat)
        .outerjoin(Charger, Charger.flat_id == Flat.id)
        .outerjoin(
            ChargingSession,
            (ChargingSession.charger_id == Charger.charger_id)
            & (ChargingSession.status.in_([
                "charging_ended",
                "charging_ended_error",
                "charging_stopped_by_admin",
            ]))
            & (ChargingSession.ended_at >= start)
            & (ChargingSession.ended_at < end),
        )
        .where(Flat.society_id == society_id)
        .group_by(Flat.id, Flat.flat_number, Flat.owner_name)
        .order_by(func.coalesce(func.sum(ChargingSession.units_consumed), 0).desc())
    )
    rows = result.all()

    amt_result = await db.execute(
        select(FlatBill.flat_id, func.coalesce(func.sum(FlatBill.total_payable), 0))
        .join(MonthlyBill, MonthlyBill.id == FlatBill.monthly_bill_id)
        .where(MonthlyBill.billing_month >= start, MonthlyBill.billing_month < end)
        .group_by(FlatBill.flat_id)
    )
    amounts = {fid: Decimal(str(amt)) for fid, amt in amt_result.all()}

    return [
        FlatUsageOut(
            flat_id=r.flat_id,
            flat_number=r.flat_number,
            owner_name=r.owner_name,
            total_units=Decimal(str(r.total_units)),
            session_count=r.session_count,
            total_amount=amounts.get(r.flat_id, Decimal("0")),
        )
        for r in rows
    ]