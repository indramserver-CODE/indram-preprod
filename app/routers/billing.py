"""
app/routers/billing.py
----------------------
Society admin only.

GET    /api/billing/next-period?meter_id=   — suggested From/Till for the meter's next bill
POST   /api/billing/generate                — create a draft from the MSEB bill → preview (nothing emailed)
GET    /api/billing/{id}/preview            — preview totals of a draft (or any bill)
POST   /api/billing/{id}/send               — send a draft: bill numbers, emails, Indram invoice
POST   /api/billing/{id}/reissue            — wrong bill: draft with corrected MSEB figures that
                                              replaces it when sent
DELETE /api/billing/{id}                    — discard a draft (sent bills are never deleted)
GET    /api/billing                         — list bills for the admin's society
GET    /api/billing/{id}                    — bill detail with all flat bills

GET    /api/billing/{id}/flat-bills?q=&payment_status=  — find flats (search by flat no. / owner)
PUT    /api/billing/flat-bills/{flat_bill_id}/payment   — mark Paid / Unpaid
POST   /api/billing/{id}/mark-all-paid                  — every still-pending flat → Paid

History downloads (any bill, including drafts and cancelled ones):
GET    /api/billing/flat-bills/{flat_bill_id}/pdf       — resident bill
GET    /api/billing/flat-bills/{flat_bill_id}/late-pdf  — bill with late fee (marked Unpaid)
GET    /api/billing/flat-bills/{flat_bill_id}/receipt   — receipt (Paid)
GET    /api/billing/{id}/summary/{kind}                 — admin summary: society | mseb | indram
GET    /api/billing/{id}/mseb-photo                     — uploaded MSEB bill photo
"""

import asyncio
import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from sqlalchemy import select, or_, func as sa_func

from app.database import get_db
from app.models.bill import MonthlyBill, FlatBill
from app.models.meter import Meter
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.schemas.billing import (
    NextPeriodOut, BillPreviewOut, MonthlyBillOut, MonthlyBillSummaryOut, FlatBillOut,
)
from app.dependencies.auth import require_society_admin
from app.services import billing_calc as bc, storage
from app.services.billing_service import (
    BillingError, create_draft, bill_preview, send_bill, get_sent_period_range,
    mark_flat_paid, mark_flat_unpaid, mark_all_pending_paid,
)
from app.services.bill_dispatch import (
    dispatch_sent_bill, dispatch_unpaid, dispatch_receipts,
    build_flat_bill_pdf, build_flat_receipt_pdf, build_society_bill_pdf,
)
from app.services.pdf_service import SOCIETY_BILL_TITLES

logger = logging.getLogger(__name__)
router = APIRouter()

_background: set[asyncio.Task] = set()   # keep dispatch tasks referenced until they finish


def _spawn(coro):
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


# ── Helpers ───────────────────────────────────────────────────────────

async def _get_society_for_admin(user: User, db: AsyncSession) -> Society:
    society_id = await db.scalar(select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id))
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned")
    society = await db.get(Society, society_id)
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


async def _get_meter_for_admin(meter_id: int, society_id: int, db: AsyncSession) -> Meter:
    meter = await db.get(Meter, meter_id)
    if not meter:
        raise HTTPException(status_code=404, detail="Meter not found")
    if meter.society_id != society_id:
        raise HTTPException(status_code=403, detail="Meter does not belong to your society")
    return meter


async def _get_bill_for_admin(monthly_bill_id: int, society_id: int, db: AsyncSession) -> tuple[MonthlyBill, Meter]:
    mb = await db.get(MonthlyBill, monthly_bill_id)
    if not mb:
        raise HTTPException(status_code=404, detail="Bill not found")
    meter = await db.get(Meter, mb.meter_id)
    if not meter or meter.society_id != society_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return mb, meter


async def _upload_photo(photo: UploadFile | None, society_id: int, meter_id: int, label: str,
                        required: bool = False) -> str | None:
    if not photo or not photo.filename:
        if required:
            raise HTTPException(status_code=400, detail="Upload a photo or PDF of the MSEB bill.")
        return None
    content_type = photo.content_type or ""
    if not (content_type.startswith("image/") or content_type == "application/pdf"):
        raise HTTPException(status_code=400, detail="The MSEB bill must be a photo (image) or a PDF.")
    data = await photo.read()
    if not data:
        raise HTTPException(status_code=400, detail="The MSEB bill file is empty.")
    key  = f"mseb_bills/{society_id}/meter-{meter_id}/{label}/{photo.filename}"
    return storage.upload(data, key, photo.content_type or "application/octet-stream")


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/next-period", response_model=NextPeriodOut)
async def next_period(
    meter_id:     int,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    meter   = await _get_meter_for_admin(meter_id, society.id, db)
    _, last_till = await get_sent_period_range(db, meter.id)
    suggested_from, suggested_till = bc.suggest_next_period(last_till)
    draft_id = await db.scalar(
        select(MonthlyBill.id).where(MonthlyBill.meter_id == meter.id, MonthlyBill.status == "draft")
    )
    return NextPeriodOut(
        meter_id=meter.id, last_till=last_till,
        suggested_from=suggested_from, suggested_till=suggested_till,
        earliest_generate_date=bc.earliest_generate_date(suggested_till) if suggested_till else None,
        draft_id=draft_id,
    )


@router.post("/generate", response_model=BillPreviewOut, status_code=status.HTTP_201_CREATED)
async def generate_bills(
    meter_id:             int          = Form(...),
    period_from:          date         = Form(...),
    period_till:          date         = Form(...),
    due_date:             date         = Form(...),
    tariff:               Decimal      = Form(..., description="MSEB per-unit rate on the bill"),
    total_bill_amount:    Decimal      = Form(..., description="Total amount on the MSEB bill"),
    total_units_consumed: Decimal      = Form(..., description="Units on the MSEB bill"),
    bill_photo:           UploadFile   = File(..., description="Photo or PDF of the MSEB bill"),
    db:                   AsyncSession = Depends(get_db),
    current_user:         User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    meter   = await _get_meter_for_admin(meter_id, society.id, db)
    photo_key = await _upload_photo(bill_photo, society.id, meter.id, f"{period_from}_{period_till}", required=True)
    try:
        mb = await create_draft(
            db, meter, society, period_from, period_till, due_date,
            tariff, total_bill_amount, total_units_consumed, current_user.id, photo_key,
        )
        preview = await bill_preview(db, mb)
        await db.commit()
    except BillingError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return preview


@router.get("/{monthly_bill_id}/preview", response_model=BillPreviewOut)
async def get_preview(
    monthly_bill_id: int,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    mb, _   = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    return await bill_preview(db, mb)


@router.post("/{monthly_bill_id}/send")
async def send_bills(
    monthly_bill_id: int,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    mb, meter = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    try:
        invoice = await send_bill(db, mb, society)
        await db.commit()
    except BillingError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    _spawn(dispatch_sent_bill(mb.id))
    return {
        "detail":          "Bills sent. PDFs and emails are being dispatched.",
        "monthly_bill_id": mb.id,
        "meter_label":     meter.label,
        "invoice_number":  invoice.invoice_number if invoice else None,
    }


@router.post("/{monthly_bill_id}/reissue", response_model=BillPreviewOut, status_code=status.HTTP_201_CREATED)
async def reissue_bill(
    monthly_bill_id:      int,
    due_date:             date         = Form(...),
    tariff:               Decimal      = Form(...),
    total_bill_amount:    Decimal      = Form(...),
    total_units_consumed: Decimal      = Form(...),
    bill_photo:           UploadFile   = File(None),
    db:                   AsyncSession = Depends(get_db),
    current_user:         User         = Depends(require_society_admin),
):
    """Corrected MSEB figures for a sent bill → draft preview. Send it to cancel and replace the old bill."""
    society   = await _get_society_for_admin(current_user, db)
    old, meter = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    photo_key = await _upload_photo(bill_photo, society.id, meter.id, f"{old.period_from}_{old.period_till}")
    try:
        mb = await create_draft(
            db, meter, society, None, None, due_date,
            tariff, total_bill_amount, total_units_consumed, current_user.id, photo_key, replacing=old,
        )
        preview = await bill_preview(db, mb)
        await db.commit()
    except BillingError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return preview


@router.delete("/{monthly_bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    monthly_bill_id: int,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    mb, _   = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    if mb.status != "draft":
        raise HTTPException(status_code=400, detail="Sent bills can't be deleted — reissue the bill instead.")
    await db.delete(mb)
    await db.commit()


@router.get("", response_model=list[MonthlyBillSummaryOut])
async def list_monthly_bills(
    meter_id:     int | None   = None,
    status_:      str | None   = Query(None, alias="status", description="draft | sent | cancelled"),
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    meters  = {m.id: m for m in (await db.execute(select(Meter).where(Meter.society_id == society.id))).scalars()}
    if not meters:
        return []
    if meter_id is not None and meter_id not in meters:
        raise HTTPException(status_code=403, detail="Meter does not belong to your society")

    fb = (
        select(
            FlatBill.monthly_bill_id.label("mb_id"),
            sa_func.count(FlatBill.id).label("flats"),
            sa_func.coalesce(sa_func.sum(FlatBill.total_payable), 0).label("amount"),
            sa_func.count(FlatBill.id).filter(FlatBill.payment_status == "paid").label("paid"),
            sa_func.count(FlatBill.id).filter(FlatBill.payment_status == "unpaid").label("unpaid"),
            sa_func.count(FlatBill.id).filter(FlatBill.email_status == "sent").label("sent"),
            sa_func.count(FlatBill.id).filter(FlatBill.email_status == "failed").label("failed"),
            sa_func.count(FlatBill.id).filter(FlatBill.email_status == "pending").label("pending"),
        )
        .group_by(FlatBill.monthly_bill_id)
        .subquery()
    )
    q = (
        select(MonthlyBill, fb)
        .outerjoin(fb, fb.c.mb_id == MonthlyBill.id)
        .where(MonthlyBill.meter_id.in_(meter_id and [meter_id] or list(meters)))
        .order_by(MonthlyBill.period_till.desc(), MonthlyBill.created_at.desc())
    )
    if status_:
        q = q.where(MonthlyBill.status == status_)

    out = []
    for row in (await db.execute(q)).all():
        mb, meter = row.MonthlyBill, meters[row.MonthlyBill.meter_id]
        out.append(MonthlyBillSummaryOut(
            id=mb.id, meter_id=mb.meter_id, meter_number=meter.meter_number, meter_label=meter.label,
            period_from=mb.period_from, period_till=mb.period_till, billing_month=mb.billing_month,
            status=mb.status, total_bill_amount=mb.total_bill_amount,
            total_units_consumed=mb.total_units_consumed, effective_unit_rate=mb.effective_unit_rate,
            due_date=mb.due_date, sent_at=mb.sent_at, replaces_id=mb.replaces_id, created_at=mb.created_at,
            total_flats=row.flats or 0, total_amount=Decimal(str(row.amount or 0)),
            flats_paid=row.paid or 0, flats_unpaid=row.unpaid or 0,
            emails_sent=row.sent or 0, emails_failed=row.failed or 0, emails_pending=row.pending or 0,
        ))
    return out


@router.get("/{monthly_bill_id}", response_model=MonthlyBillOut)
async def get_monthly_bill(
    monthly_bill_id: int,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    society   = await _get_society_for_admin(current_user, db)
    mb, meter = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    flat_bills = (await db.execute(
        select(FlatBill).where(FlatBill.monthly_bill_id == mb.id).order_by(FlatBill.flat_number)
    )).scalars().all()
    return MonthlyBillOut(
        id=mb.id, meter_id=mb.meter_id, meter_number=meter.meter_number, meter_label=meter.label,
        period_from=mb.period_from, period_till=mb.period_till, billing_month=mb.billing_month,
        status=mb.status, tariff=mb.tariff, total_bill_amount=mb.total_bill_amount,
        total_units_consumed=mb.total_units_consumed, effective_unit_rate=mb.effective_unit_rate,
        due_date=mb.due_date, sent_at=mb.sent_at, cancelled_at=mb.cancelled_at,
        replaces_id=mb.replaces_id, created_at=mb.created_at,
        flat_bills=[FlatBillOut.model_validate(fb) for fb in flat_bills],
    )


# ── Payments ──────────────────────────────────────────────────────────

class PaymentUpdate(BaseModel):
    payment_status: str   # paid | unpaid


@router.get("/{monthly_bill_id}/flat-bills", response_model=list[FlatBillOut])
async def search_flat_bills(
    monthly_bill_id: int,
    q:               str | None   = Query(None, description="Flat number or owner name"),
    payment_status:  str | None   = Query(None, description="pending | unpaid | paid"),
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    mb, _   = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    query = select(FlatBill).where(FlatBill.monthly_bill_id == mb.id).order_by(FlatBill.flat_number)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(FlatBill.flat_number.ilike(like), FlatBill.owner_name.ilike(like)))
    if payment_status:
        query = query.where(FlatBill.payment_status == payment_status)
    return [FlatBillOut.model_validate(fb) for fb in (await db.execute(query)).scalars()]


@router.put("/flat-bills/{flat_bill_id}/payment", response_model=FlatBillOut)
async def update_flat_payment(
    flat_bill_id: int,
    body:         PaymentUpdate,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_society_admin),
):
    """
    Paid   → receipt emailed (late fee closed if it had been marked Unpaid; super admin notified).
    Unpaid → only after due date + grace days: late fee added, bill re-sent, super admin notified.
    """
    if body.payment_status not in ("paid", "unpaid"):
        raise HTTPException(status_code=400, detail="payment_status must be 'paid' or 'unpaid'")
    society = await _get_society_for_admin(current_user, db)
    fb = await db.get(FlatBill, flat_bill_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Bill not found")
    await _get_bill_for_admin(fb.monthly_bill_id, society.id, db)
    try:
        if body.payment_status == "paid":
            fb = await mark_flat_paid(db, flat_bill_id, society)
        else:
            fb = await mark_flat_unpaid(db, flat_bill_id, society)
        await db.commit()
    except BillingError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    _spawn(dispatch_receipts([fb.id]) if fb.payment_status == "paid" else dispatch_unpaid(fb.id))
    return FlatBillOut.model_validate(fb)


@router.post("/{monthly_bill_id}/mark-all-paid")
async def mark_all_paid(
    monthly_bill_id: int,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    """Mark the unpaid flats first — this marks every flat still pending as Paid and emails receipts."""
    society = await _get_society_for_admin(current_user, db)
    mb, _   = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    try:
        ids = await mark_all_pending_paid(db, mb)
        await db.commit()
    except BillingError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    if ids:
        _spawn(dispatch_receipts(ids))
    return {"detail": f"{len(ids)} flats marked Paid. Receipts are being emailed.", "marked_paid": len(ids)}


# ── History downloads ─────────────────────────────────────────────────

def _file_response(content: bytes, filename: str, media_type: str = "application/pdf") -> Response:
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


async def _flat_bill_for_admin(flat_bill_id: int, user: User, db: AsyncSession):
    society = await _get_society_for_admin(user, db)
    fb = await db.get(FlatBill, flat_bill_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Bill not found")
    mb, meter = await _get_bill_for_admin(fb.monthly_bill_id, society.id, db)
    return fb, mb, meter, society


def _name(fb: FlatBill, kind: str = "bill") -> str:
    number = fb.bill_number or f"DRAFT-{fb.flat_number}"
    return {"bill": f"Bill_{number}.pdf", "late": f"Bill_{number}_with_late_fee.pdf",
            "receipt": f"Receipt_{number}.pdf"}[kind]


@router.get("/flat-bills/{flat_bill_id}/pdf")
async def download_flat_bill(flat_bill_id: int, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_society_admin)):
    fb, mb, meter, society = await _flat_bill_for_admin(flat_bill_id, current_user, db)
    pdf = storage.download(fb.pdf_s3_key) or await build_flat_bill_pdf(db, fb, mb, meter, society)
    return _file_response(pdf, _name(fb))


@router.get("/flat-bills/{flat_bill_id}/late-pdf")
async def download_flat_bill_late(flat_bill_id: int, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(require_society_admin)):
    fb, mb, meter, society = await _flat_bill_for_admin(flat_bill_id, current_user, db)
    if not fb.marked_unpaid_at:
        raise HTTPException(status_code=400, detail="This bill was never marked Unpaid, so it has no late fee.")
    pdf = storage.download(fb.late_pdf_s3_key) or await build_flat_bill_pdf(db, fb, mb, meter, society, with_late_fee=True)
    return _file_response(pdf, _name(fb, "late"))


@router.get("/flat-bills/{flat_bill_id}/receipt")
async def download_flat_receipt(flat_bill_id: int, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_society_admin)):
    fb, mb, meter, society = await _flat_bill_for_admin(flat_bill_id, current_user, db)
    if fb.payment_status != "paid":
        raise HTTPException(status_code=400, detail="A receipt is available once the bill is marked Paid.")
    pdf = storage.download(fb.receipt_pdf_s3_key) or build_flat_receipt_pdf(fb, mb, meter, society)
    return _file_response(pdf, _name(fb, "receipt"))


@router.get("/{monthly_bill_id}/summary/{kind}")
async def download_society_summary(monthly_bill_id: int, kind: str, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_society_admin)):
    if kind not in SOCIETY_BILL_TITLES:
        raise HTTPException(status_code=400, detail="kind must be one of: society, mseb, indram")
    society   = await _get_society_for_admin(current_user, db)
    mb, meter = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    pdf = await build_society_bill_pdf(db, kind, mb, meter, society)
    return _file_response(pdf, f"{kind.capitalize()}_Total_{meter.label}_{mb.period_from}_{mb.period_till}.pdf")


@router.get("/{monthly_bill_id}/mseb-photo")
async def download_mseb_photo(monthly_bill_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_society_admin)):
    society = await _get_society_for_admin(current_user, db)
    mb, _   = await _get_bill_for_admin(monthly_bill_id, society.id, db)
    data = storage.download(mb.bill_photo_s3_key)
    if not data:
        raise HTTPException(status_code=404, detail="No MSEB bill photo stored for this bill.")
    filename = mb.bill_photo_s3_key.rsplit("/", 1)[-1]
    media = "application/pdf" if filename.lower().endswith(".pdf") else \
            "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    return _file_response(data, filename, media)
