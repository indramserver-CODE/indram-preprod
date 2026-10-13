"""
app/routers/indram_bills.py
----------------------------
Society admin:
  GET  /api/sa/indram-bills           — list own society's indram bills
  GET  /api/sa/indram-bills/{id}      — detail with meter breakdown

Super admin:
  GET  /api/indram-bills              — list all, filter by society_id / month
  GET  /api/indram-bills/revenue-summary — KPI totals
  GET  /api/indram-bills/{id}         — detail
  PUT  /api/indram-bills/{id}/payment — mark paid / unpaid
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.bill import IndramBill, FlatBill, MonthlyBill
from app.models.meter import Meter
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.schemas.indram_bill import IndramBillOut, IndramBillSummaryOut, MeterBreakdownItem
from app.dependencies.auth import require_super_admin, require_society_admin

logger = logging.getLogger(__name__)

super_router   = APIRouter()
society_router = APIRouter()


async def _get_admin_society_id(user: User, db: AsyncSession) -> int:
    result = await db.execute(select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id))
    society_id = result.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned")
    return society_id


async def _build_meter_breakdown(db: AsyncSession, society_id: int, billing_month: date) -> list[MeterBreakdownItem]:
    year, month = billing_month.year, billing_month.month
    next_month  = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    result = await db.execute(
        select(
            Meter.id.label("meter_id"), Meter.meter_number,
            Meter.label.label("meter_label"),
            func.coalesce(func.sum(FlatBill.units_consumed), 0).label("units_billed"),
            func.coalesce(func.sum(FlatBill.indram_charges), 0).label("indram_amount"),
        )
        .join(MonthlyBill, MonthlyBill.meter_id == Meter.id)
        .join(FlatBill, FlatBill.monthly_bill_id == MonthlyBill.id)
        .where(Meter.society_id == society_id,
               MonthlyBill.billing_month >= billing_month,
               MonthlyBill.billing_month < next_month)
        .group_by(Meter.id, Meter.meter_number, Meter.label)
        .order_by(Meter.meter_number)
    )
    return [MeterBreakdownItem(
        meter_id=r.meter_id, meter_number=r.meter_number, meter_label=r.meter_label,
        units_billed=Decimal(str(r.units_billed)), indram_amount=Decimal(str(r.indram_amount)),
    ) for r in result.all()]


def _to_summary(bill: IndramBill, society_name: str | None = None) -> IndramBillSummaryOut:
    return IndramBillSummaryOut(
        id=bill.id, society_id=bill.society_id, society_name=society_name,
        billing_month=bill.billing_month,
        total_indram_amount=Decimal(str(bill.total_indram_amount)),
        total_units=Decimal(str(bill.total_units)),
        due_date=bill.due_date, payment_status=bill.payment_status, paid_at=bill.paid_at,
        email_status=bill.email_status, created_at=bill.created_at, updated_at=bill.updated_at,
    )


async def _to_detail(bill: IndramBill, db: AsyncSession, society: Society | None) -> IndramBillOut:
    breakdown = await _build_meter_breakdown(db, bill.society_id, bill.billing_month)
    return IndramBillOut(
        id=bill.id, society_id=bill.society_id,
        society_name=society.name if society else None,
        billing_month=bill.billing_month,
        total_indram_amount=Decimal(str(bill.total_indram_amount)),
        total_units=Decimal(str(bill.total_units)),
        due_date=bill.due_date, payment_status=bill.payment_status, paid_at=bill.paid_at,
        pdf_s3_key=bill.pdf_s3_key, email_status=bill.email_status,
        email_sent_at=bill.email_sent_at, created_at=bill.created_at,
        updated_at=bill.updated_at, meter_breakdown=breakdown,
    )


# ── Society admin ─────────────────────────────────────────────────────

@society_router.get("", response_model=list[IndramBillSummaryOut])
async def list_my_indram_bills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    society_id = await _get_admin_society_id(current_user, db)
    result = await db.execute(
        select(IndramBill).where(IndramBill.society_id == society_id)
        .order_by(IndramBill.billing_month.desc())
    )
    bills = result.scalars().all()
    society = await db.get(Society, society_id)
    return [_to_summary(b, society.name if society else None) for b in bills]


@society_router.get("/{bill_id}", response_model=IndramBillOut)
async def get_my_indram_bill(
    bill_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    society_id = await _get_admin_society_id(current_user, db)
    bill = await db.get(IndramBill, bill_id)
    if not bill or bill.society_id != society_id:
        raise HTTPException(status_code=404, detail="Indram bill not found")
    society = await db.get(Society, society_id)
    return await _to_detail(bill, db, society)


# ── Super admin ───────────────────────────────────────────────────────

@super_router.get("/revenue-summary")
async def indram_revenue_summary(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    today      = date.today()
    this_month = date(today.year, today.month, 1)
    result = await db.execute(
        select(
            func.coalesce(func.sum(IndramBill.total_indram_amount), 0).label("total_all_time"),
            func.coalesce(func.sum(IndramBill.total_indram_amount).filter(IndramBill.payment_status == "paid"),   0).label("total_paid"),
            func.coalesce(func.sum(IndramBill.total_indram_amount).filter(IndramBill.payment_status == "unpaid"), 0).label("total_unpaid"),
            func.coalesce(func.sum(IndramBill.total_indram_amount).filter(IndramBill.billing_month == this_month), 0).label("this_month"),
            func.count(IndramBill.id).label("total_invoices"),
            func.count(IndramBill.id).filter(IndramBill.payment_status == "unpaid").label("unpaid_count"),
        )
    )
    row = result.one()
    return {
        "total_all_time": float(row.total_all_time),
        "total_paid":     float(row.total_paid),
        "total_unpaid":   float(row.total_unpaid),
        "this_month":     float(row.this_month),
        "total_invoices": row.total_invoices,
        "unpaid_count":   row.unpaid_count,
    }


@super_router.get("", response_model=list[IndramBillSummaryOut])
async def list_indram_bills(
    society_id: int | None = None,
    month:      str | None = None,
    db:         AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    q = select(IndramBill).order_by(IndramBill.billing_month.desc(), IndramBill.society_id)
    if society_id:
        q = q.where(IndramBill.society_id == society_id)
    if month:
        try:
            year, m = map(int, month.split("-"))
            q = q.where(IndramBill.billing_month == date(year, m, 1))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    result  = await db.execute(q)
    bills   = result.scalars().all()
    soc_ids = list({b.society_id for b in bills})
    soc_res = await db.execute(select(Society).where(Society.id.in_(soc_ids)))
    soc_map = {s.id: s.name for s in soc_res.scalars().all()}
    return [_to_summary(b, soc_map.get(b.society_id)) for b in bills]


@super_router.get("/{bill_id}", response_model=IndramBillOut)
async def get_indram_bill(
    bill_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    bill = await db.get(IndramBill, bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Indram bill not found")
    society = await db.get(Society, bill.society_id)
    return await _to_detail(bill, db, society)


class PaymentStatusUpdate(BaseModel):
    payment_status: str   # paid | unpaid


@super_router.put("/{bill_id}/payment")
async def update_payment_status(
    bill_id: int,
    body:    PaymentStatusUpdate,
    db:      AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    if body.payment_status not in ("paid", "unpaid"):
        raise HTTPException(status_code=400, detail="payment_status must be 'paid' or 'unpaid'")
    bill = await db.get(IndramBill, bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Indram bill not found")
    bill.payment_status = body.payment_status
    bill.paid_at        = datetime.now(timezone.utc) if body.payment_status == "paid" else None
    await db.commit()
    logger.info("IndramBill payment_status=%s | id=%s", body.payment_status, bill_id)
    return {
        "detail": f"Bill marked as {body.payment_status}",
        "id": bill.id, "payment_status": bill.payment_status,
        "paid_at": bill.paid_at.isoformat() if bill.paid_at else None,
    }