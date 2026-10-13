"""
app/routers/indram_bills.py
----------------------------
Indram's GST tax invoices to societies — one per sent meter bill.

Society admin:
  GET  /api/sa/indram-bills                 — own society's invoices
  GET  /api/sa/indram-bills/{id}            — detail
  GET  /api/sa/indram-bills/{id}/pdf        — download invoice
  GET  /api/sa/indram-bills/{id}/receipt    — download receipt (paid invoices)

Super admin:
  GET  /api/indram-bills                    — all invoices, filter by society / month / payment status
  GET  /api/indram-bills/revenue-summary    — KPI totals
  GET  /api/indram-bills/{id}               — detail
  GET  /api/indram-bills/{id}/pdf           — download invoice
  GET  /api/indram-bills/{id}/receipt       — download receipt
  PUT  /api/indram-bills/{id}/late          — raise late flag (after due date + grace days): late fee
                                              + GST added, invoice re-sent to the society admin
  PUT  /api/indram-bills/{id}/paid          — clear late flag, mark paid, create receipt

Cancelled invoices (replaced by a reissued bill) are hidden unless include_cancelled=true.
"""

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.bill import IndramBill, MonthlyBill
from app.models.meter import Meter
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.schemas.indram_bill import IndramBillOut, IndramBillSummaryOut
from app.dependencies.auth import require_super_admin, require_society_admin
from app.services import billing_calc as bc
from app.services.billing_service import BillingError, raise_invoice_late_flag, mark_invoice_paid
from app.services.bill_dispatch import (
    dispatch_invoice_late, store_invoice_receipt, invoice_pdf, invoice_receipt_pdf,
)

logger = logging.getLogger(__name__)

super_router   = APIRouter()
society_router = APIRouter()

_background: set[asyncio.Task] = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


# ── Helpers ───────────────────────────────────────────────────────────

async def _get_admin_society_id(user: User, db: AsyncSession) -> int:
    society_id = await db.scalar(select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id))
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned")
    return society_id


def _list_query(include_cancelled: bool):
    q = (
        select(IndramBill, Society.name, Meter)
        .join(Society, Society.id == IndramBill.society_id)
        .join(MonthlyBill, MonthlyBill.id == IndramBill.monthly_bill_id)
        .join(Meter, Meter.id == MonthlyBill.meter_id)
        .order_by(IndramBill.created_at.desc())
    )
    if not include_cancelled:
        q = q.where(IndramBill.status == "issued")
    return q


def _summary_fields(inv: IndramBill, society_name: str | None, meter: Meter | None) -> dict:
    return dict(
        id=inv.id, invoice_number=inv.invoice_number, society_id=inv.society_id, society_name=society_name,
        meter_id=meter.id if meter else None, meter_label=meter.label if meter else None,
        billing_month=inv.billing_month, period_from=inv.period_from, period_till=inv.period_till,
        total_units=inv.total_units, total_indram_amount=inv.total_indram_amount,
        late_flag=inv.late_flag, late_fee=inv.late_fee, cgst=inv.cgst, sgst=inv.sgst,
        total_payable=inv.total_payable, due_date=inv.due_date, status=inv.status,
        payment_status=inv.payment_status, paid_at=inv.paid_at, email_status=inv.email_status,
        has_receipt=inv.payment_status == "paid", created_at=inv.created_at,
    )


async def _detail(db: AsyncSession, inv: IndramBill) -> IndramBillOut:
    society = await db.get(Society, inv.society_id)
    mb      = await db.get(MonthlyBill, inv.monthly_bill_id)
    meter   = await db.get(Meter, mb.meter_id) if mb else None
    replaces = await db.scalar(select(IndramBill.invoice_number).where(IndramBill.id == inv.replaces_id)) \
        if inv.replaces_id else None
    replaced_by = await db.scalar(select(IndramBill.invoice_number).where(IndramBill.replaces_id == inv.id))
    return IndramBillOut(
        **_summary_fields(inv, society.name if society else None, meter),
        meter_number=meter.meter_number if meter else None,
        indram_rate=inv.indram_rate, late_fee_pct=inv.late_fee_pct, society_gstin=inv.society_gstin,
        monthly_bill_id=inv.monthly_bill_id, replaces_number=replaces, replaced_by_number=replaced_by,
        late_flag_allowed_from=bc.late_fee_allowed_from(inv.due_date, society.indram_late_fee_grace_days)
            if society else None,
        email_sent_at=inv.email_sent_at, updated_at=inv.updated_at,
    )


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


async def _download(db: AsyncSession, inv: IndramBill, receipt: bool) -> Response:
    safe = inv.invoice_number.replace("/", "-")
    if receipt:
        if inv.payment_status != "paid":
            raise HTTPException(status_code=400, detail="A receipt is available once the invoice is paid.")
        return _pdf_response(await invoice_receipt_pdf(db, inv), f"Indram_Receipt_{safe}.pdf")
    return _pdf_response(await invoice_pdf(db, inv), f"Indram_Invoice_{safe}.pdf")


# ── Society admin ─────────────────────────────────────────────────────

@society_router.get("", response_model=list[IndramBillSummaryOut])
async def list_my_indram_bills(
    include_cancelled: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    society_id = await _get_admin_society_id(current_user, db)
    rows = (await db.execute(_list_query(include_cancelled).where(IndramBill.society_id == society_id))).all()
    return [IndramBillSummaryOut(**_summary_fields(inv, name, meter)) for inv, name, meter in rows]


async def _my_invoice(bill_id: int, user: User, db: AsyncSession) -> IndramBill:
    society_id = await _get_admin_society_id(user, db)
    inv = await db.get(IndramBill, bill_id)
    if not inv or inv.society_id != society_id:
        raise HTTPException(status_code=404, detail="Indram bill not found")
    return inv


@society_router.get("/{bill_id}", response_model=IndramBillOut)
async def get_my_indram_bill(bill_id: int, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_society_admin)):
    return await _detail(db, await _my_invoice(bill_id, current_user, db))


@society_router.get("/{bill_id}/pdf")
async def download_my_invoice(bill_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_society_admin)):
    return await _download(db, await _my_invoice(bill_id, current_user, db), receipt=False)


@society_router.get("/{bill_id}/receipt")
async def download_my_receipt(bill_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_society_admin)):
    return await _download(db, await _my_invoice(bill_id, current_user, db), receipt=True)


# ── Super admin ───────────────────────────────────────────────────────

@super_router.get("/revenue-summary")
async def indram_revenue_summary(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    """Amounts before GST (charges + late fees); cancelled invoices excluded."""
    this_month = bc.today_ist().replace(day=1)
    revenue = IndramBill.total_indram_amount + IndramBill.late_fee
    row = (await db.execute(
        select(
            func.coalesce(func.sum(revenue), 0).label("total_all_time"),
            func.coalesce(func.sum(revenue).filter(IndramBill.payment_status == "paid"), 0).label("total_paid"),
            func.coalesce(func.sum(revenue).filter(IndramBill.payment_status == "unpaid"), 0).label("total_unpaid"),
            func.coalesce(func.sum(revenue).filter(IndramBill.billing_month == this_month), 0).label("this_month"),
            func.count(IndramBill.id).label("total_invoices"),
            func.count(IndramBill.id).filter(IndramBill.payment_status == "unpaid").label("unpaid_count"),
            func.count(IndramBill.id).filter(IndramBill.late_flag.is_(True)).label("late_count"),
        ).where(IndramBill.status == "issued")
    )).one()
    return {
        "total_all_time": float(row.total_all_time),
        "total_paid":     float(row.total_paid),
        "total_unpaid":   float(row.total_unpaid),
        "this_month":     float(row.this_month),
        "total_invoices": row.total_invoices,
        "unpaid_count":   row.unpaid_count,
        "late_count":     row.late_count,
    }


@super_router.get("", response_model=list[IndramBillSummaryOut])
async def list_indram_bills(
    society_id:        int | None = None,
    month:             str | None = Query(None, description="YYYY-MM — month of the Till date"),
    payment_status:    str | None = Query(None, description="unpaid | paid"),
    include_cancelled: bool = False,
    db:                AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    q = _list_query(include_cancelled)
    if society_id:
        q = q.where(IndramBill.society_id == society_id)
    if payment_status:
        q = q.where(IndramBill.payment_status == payment_status)
    if month:
        try:
            year, m = map(int, month.split("-"))
            q = q.where(IndramBill.billing_month == date(year, m, 1))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    return [IndramBillSummaryOut(**_summary_fields(inv, name, meter)) for inv, name, meter in (await db.execute(q)).all()]


async def _invoice(bill_id: int, db: AsyncSession) -> IndramBill:
    inv = await db.get(IndramBill, bill_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Indram bill not found")
    return inv


@super_router.get("/{bill_id}", response_model=IndramBillOut)
async def get_indram_bill(bill_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    return await _detail(db, await _invoice(bill_id, db))


@super_router.get("/{bill_id}/pdf")
async def download_invoice(bill_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    return await _download(db, await _invoice(bill_id, db), receipt=False)


@super_router.get("/{bill_id}/receipt")
async def download_receipt(bill_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    return await _download(db, await _invoice(bill_id, db), receipt=True)


@super_router.put("/{bill_id}/late", response_model=IndramBillOut)
async def flag_late(bill_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    try:
        inv = await raise_invoice_late_flag(db, bill_id)
        await db.commit()
    except BillingError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    await db.refresh(inv)   # updated_at is set by the database
    logger.info("Indram invoice flagged late | %s late_fee=%s", inv.invoice_number, inv.late_fee)
    _spawn(dispatch_invoice_late(inv.id))
    return await _detail(db, inv)


@super_router.put("/{bill_id}/paid", response_model=IndramBillOut)
async def flag_paid(bill_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    try:
        inv = await mark_invoice_paid(db, bill_id)
        await db.commit()
    except BillingError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    await db.refresh(inv)
    logger.info("Indram invoice paid | %s", inv.invoice_number)
    _spawn(store_invoice_receipt(inv.id))
    return await _detail(db, inv)
