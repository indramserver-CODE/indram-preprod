"""
app/routers/billing.py
----------------------
Society admin only.

POST   /api/billing/generate           — generate flat bills for a meter for a month
GET    /api/billing                    — list monthly bills for admin's society
GET    /api/billing/{monthly_bill_id}  — detail with all flat bills
DELETE /api/billing/{monthly_bill_id}  — delete + recalculate indram bill
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import selectinload

import boto3

from app.database import get_db
from app.models.bill import MonthlyBill, FlatBill, IndramBill
from app.models.meter import Meter
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.schemas.billing import MonthlyBillOut, MonthlyBillSummaryOut, FlatBillOut
from app.dependencies.auth import require_society_admin
from app.services.billing_service import generate_monthly_bills, upsert_indram_bill
from app.services.pdf_service import generate_bill_pdf, generate_indram_invoice_pdf
from app.services.email_service import send_bill_email, send_indram_bill_email
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────

async def _get_society_for_admin(user: User, db: AsyncSession) -> Society:
    sa = await db.execute(select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id))
    society_id = sa.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned")
    soc = await db.execute(select(Society).where(Society.id == society_id))
    society = soc.scalar_one_or_none()
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


def _upload_to_s3(file_bytes: bytes, s3_key: str) -> str | None:
    if not settings.S3_BUCKET_NAME:
        return None
    try:
        client = boto3.client("s3", region_name=settings.AWS_REGION,
                               aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                               aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)
        client.put_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key,
                           Body=file_bytes, ContentType="application/pdf")
        return s3_key
    except Exception as e:
        logger.error("S3 upload failed | key=%s error=%s", s3_key, e)
        return None


# ── Background task — flat bill PDF + email dispatch ─────────────────

async def _dispatch_bills(
    monthly_bill_id: int,
    society_name:    str,
    meter_label:     str,
    society_id:      int,
    meter_id:        int,
):
    from app.database import AsyncSessionLocal
    from app.models.bill import DEFAULT_INDRAM_RATE  # fallback not needed here — already in flat_bills

    async with AsyncSessionLocal() as db:
        fb_result = await db.execute(
            select(FlatBill).where(FlatBill.monthly_bill_id == monthly_bill_id)
            .options(selectinload(FlatBill.flat))
        )
        flat_bills = fb_result.scalars().all()

        mb = await db.get(MonthlyBill, monthly_bill_id)
        if not mb:
            return

        for fb in flat_bills:
            flat = fb.flat
            if not flat or not flat.email:
                logger.warning("No email for flat_id=%s — skipping", fb.flat_id)
                continue
            try:
                bill_number = f"BILL-{mb.id}-{fb.flat_id}"
                units       = Decimal(str(fb.units_consumed))
                pdf_bytes   = generate_bill_pdf(
                    society_name=society_name, flat_number=flat.flat_number,
                    owner_name=flat.owner_name, billing_month=mb.billing_month,
                    due_date=mb.due_date, bill_number=bill_number,
                    prev_reading=Decimal("0"), curr_reading=units,
                    units_consumed=units,
                    effective_unit_rate=Decimal(str(mb.effective_unit_rate)),
                    tariff=Decimal(str(mb.tariff)),
                    bill_excl_taxes=Decimal(str(fb.bill_excl_taxes)),
                    mseb_taxes=Decimal(str(fb.mseb_taxes)),
                    electricity_charges_incl_tax=Decimal(str(fb.electricity_charges_incl_tax)),
                    indram_charges=Decimal(str(fb.indram_charges)),
                    total_payable=Decimal(str(fb.total_payable)),
                    payment_instructions="Pay via bank transfer or UPI as per society instructions.",
                    contact_info="Contact your society admin for queries.",
                )
                s3_key     = f"bills/{society_id}/meter-{meter_id}/{mb.billing_month}/{bill_number}.pdf"
                uploaded   = _upload_to_s3(pdf_bytes, s3_key)
                if uploaded:
                    fb.pdf_s3_key = uploaded

                success = await send_bill_email(
                    to_email=flat.email, owner_name=flat.owner_name,
                    flat_number=flat.flat_number, society_name=society_name,
                    billing_month=mb.billing_month, total_payable=Decimal(str(fb.total_payable)),
                    due_date=mb.due_date, pdf_bytes=pdf_bytes, bill_number=bill_number,
                )
                fb.email_status  = "sent" if success else "failed"
                fb.email_sent_at = datetime.now(timezone.utc) if success else None
            except Exception as e:
                logger.exception("Flat bill dispatch error | flat=%s error=%s", fb.flat_id, e)
                fb.email_status = "failed"

        await db.commit()
        logger.info("Flat bill dispatch complete | monthly_bill_id=%s", monthly_bill_id)


# ── Background task — Indram invoice generate + email ────────────────

async def _dispatch_indram_bill(
    society_id:    int,
    billing_month: date,
    due_date:      date,
):
    """
    Called after flat bills are generated or deleted.
    Recalculates the IndramBill for the society+month,
    generates a new invoice PDF, uploads to S3, and emails the society admin.
    """
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        # Recalculate
        indram_bill = await upsert_indram_bill(db, society_id, billing_month, due_date)
        await db.commit()

        if not indram_bill:
            logger.info("No indram charges remain for society=%s month=%s — no invoice sent",
                        society_id, billing_month)
            return

        # Re-fetch with society
        await db.refresh(indram_bill)
        society = await db.get(Society, society_id)
        if not society:
            return

        # Build meter breakdown
        from app.models.meter import Meter
        breakdown_result = await db.execute(
            select(
                Meter.id.label("meter_id"),
                Meter.meter_number,
                Meter.label.label("meter_label"),
                sa_func.coalesce(sa_func.sum(FlatBill.units_consumed),  0).label("units_billed"),
                sa_func.coalesce(sa_func.sum(FlatBill.indram_charges),  0).label("indram_amount"),
            )
            .join(MonthlyBill, MonthlyBill.meter_id == Meter.id)
            .join(FlatBill,    FlatBill.monthly_bill_id == MonthlyBill.id)
            .where(
                Meter.society_id == society_id,
                MonthlyBill.billing_month == billing_month,
            )
            .group_by(Meter.id, Meter.meter_number, Meter.label)
            .order_by(Meter.meter_number)
        )
        meter_breakdown = [
            {
                "meter_number":  r.meter_number,
                "meter_label":   r.meter_label,
                "units_billed":  Decimal(str(r.units_billed)),
                "indram_amount": Decimal(str(r.indram_amount)),
            }
            for r in breakdown_result.all()
        ]

        # Resolve indram rate (use society rate or default)
        from app.services.billing_service import DEFAULT_INDRAM_RATE
        indram_rate = (Decimal(str(society.indram_rate))
                       if society.indram_rate is not None else DEFAULT_INDRAM_RATE)

        invoice_number = f"INV-{society_id}-{billing_month.strftime('%Y%m')}"

        # Generate PDF
        try:
            pdf_bytes = generate_indram_invoice_pdf(
                society_name=society.name,
                society_address=society.address,
                billing_month=billing_month,
                due_date=due_date,
                invoice_number=invoice_number,
                total_indram_amount=Decimal(str(indram_bill.total_indram_amount)),
                total_units=Decimal(str(indram_bill.total_units)),
                meter_breakdown=meter_breakdown,
                indram_rate=indram_rate,
            )
        except Exception as e:
            logger.exception("Indram invoice PDF generation failed | society=%s error=%s", society_id, e)
            return

        # Upload to S3
        s3_key   = f"indram_invoices/{society_id}/{billing_month.strftime('%Y-%m')}/{invoice_number}.pdf"
        uploaded = _upload_to_s3(pdf_bytes, s3_key)
        if uploaded:
            indram_bill.pdf_s3_key = uploaded

        # Get society admin email
        admin_result = await db.execute(
            select(User.email)
            .join(SocietyAdmin, SocietyAdmin.user_id == User.id)
            .where(SocietyAdmin.society_id == society_id)
            .limit(1)
        )
        admin_email = admin_result.scalar_one_or_none()

        if not admin_email:
            logger.warning("No society admin email found for society_id=%s — indram bill email skipped", society_id)
            indram_bill.email_status = "failed"
        else:
            success = await send_indram_bill_email(
                to_email=admin_email,
                society_name=society.name,
                billing_month=billing_month,
                total_indram_amount=Decimal(str(indram_bill.total_indram_amount)),
                due_date=due_date,
                invoice_number=invoice_number,
                pdf_bytes=pdf_bytes,
            )
            indram_bill.email_status  = "sent" if success else "failed"
            indram_bill.email_sent_at = datetime.now(timezone.utc) if success else None

        await db.commit()
        logger.info("Indram invoice dispatched | society=%s month=%s amount=₹%s email=%s",
                    society_id, billing_month, indram_bill.total_indram_amount, indram_bill.email_status)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_bills(
    meter_id:             int          = Form(...),
    billing_month:        str          = Form(...),
    tariff:               Decimal      = Form(...),
    total_bill_amount:    Decimal      = Form(...),
    total_units_consumed: Decimal      = Form(...),
    due_date:             date         = Form(...),
    bill_photo:           UploadFile   = File(None),
    db:                   AsyncSession = Depends(get_db),
    current_user:         User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)
    meter   = await _get_meter_for_admin(meter_id, society.id, db)

    try:
        year, month = map(int, billing_month.split("-"))
        billing_month_date = date(year, month, 1)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid billing_month format. Use YYYY-MM")

    if total_units_consumed <= 0:
        raise HTTPException(status_code=400, detail="Total units consumed must be greater than zero")
    if total_bill_amount <= 0:
        raise HTTPException(status_code=400, detail="Total bill amount must be greater than zero")
    if tariff <= 0:
        raise HTTPException(status_code=400, detail="Tariff must be greater than zero")

    bill_photo_s3_key = None
    if bill_photo and bill_photo.filename:
        photo_bytes = await bill_photo.read()
        s3_key = f"mseb_bills/{society.id}/meter-{meter.id}/{billing_month}/{bill_photo.filename}"
        bill_photo_s3_key = _upload_to_s3(photo_bytes, s3_key)

    try:
        monthly_bill = await generate_monthly_bills(
            db=db, meter_id=meter.id, billing_month=billing_month_date,
            tariff=tariff, total_bill_amount=total_bill_amount,
            total_units_consumed=total_units_consumed, due_date=due_date,
            created_by=current_user.id, bill_photo_s3_key=bill_photo_s3_key,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    count_result = await db.execute(
        select(sa_func.count(FlatBill.id)).where(FlatBill.monthly_bill_id == monthly_bill.id)
    )
    total_flats = count_result.scalar()

    # Fire flat bill dispatch
    asyncio.create_task(_dispatch_bills(
        monthly_bill_id=monthly_bill.id,
        society_name=society.name,
        meter_label=meter.label,
        society_id=society.id,
        meter_id=meter.id,
    ))

    # Fire Indram invoice dispatch (recalculate + PDF + email)
    asyncio.create_task(_dispatch_indram_bill(
        society_id=society.id,
        billing_month=billing_month_date,
        due_date=due_date,
    ))

    return {
        "detail":          "Bills generated. PDFs and emails are being dispatched.",
        "monthly_bill_id": monthly_bill.id,
        "meter_id":        meter.id,
        "meter_label":     meter.label,
        "meter_number":    meter.meter_number,
        "total_flats":     total_flats,
        "effective_rate":  float(monthly_bill.effective_unit_rate),
    }


@router.get("", response_model=list[MonthlyBillSummaryOut])
async def list_monthly_bills(
    meter_id:     int | None  = None,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)

    meters_result = await db.execute(select(Meter).where(Meter.society_id == society.id))
    society_meters = {m.id: m for m in meters_result.scalars().all()}
    if not society_meters:
        return []

    meter_ids = list(society_meters.keys())
    q = (
        select(MonthlyBill)
        .where(MonthlyBill.meter_id.in_(meter_ids))
        .order_by(MonthlyBill.billing_month.desc())
    )
    if meter_id is not None:
        if meter_id not in society_meters:
            raise HTTPException(status_code=403, detail="Meter does not belong to your society")
        q = q.where(MonthlyBill.meter_id == meter_id)

    mb_result     = await db.execute(q)
    monthly_bills = mb_result.scalars().all()

    summaries = []
    for mb in monthly_bills:
        fb_result = await db.execute(
            select(FlatBill.email_status).where(FlatBill.monthly_bill_id == mb.id)
        )
        statuses = [r[0] for r in fb_result.all()]
        meter    = society_meters.get(mb.meter_id)
        summaries.append(MonthlyBillSummaryOut(
            id=mb.id, meter_id=mb.meter_id,
            meter_number=meter.meter_number if meter else None,
            meter_label=meter.label if meter else None,
            billing_month=mb.billing_month,
            total_bill_amount=mb.total_bill_amount,
            total_units_consumed=mb.total_units_consumed,
            effective_unit_rate=mb.effective_unit_rate,
            due_date=mb.due_date, created_at=mb.created_at,
            total_flats=len(statuses),
            emails_sent=statuses.count("sent"),
            emails_failed=statuses.count("failed"),
            emails_pending=statuses.count("pending"),
        ))
    return summaries


@router.get("/{monthly_bill_id}")
async def get_monthly_bill(
    monthly_bill_id: int,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)

    result = await db.execute(
        select(MonthlyBill).where(MonthlyBill.id == monthly_bill_id)
        .options(selectinload(MonthlyBill.flat_bills).selectinload(FlatBill.flat))
    )
    mb = result.scalar_one_or_none()
    if not mb:
        raise HTTPException(status_code=404, detail="Monthly bill not found")

    meter = await db.get(Meter, mb.meter_id)
    if not meter or meter.society_id != society.id:
        raise HTTPException(status_code=403, detail="Access denied")

    flat_bills_out = [
        FlatBillOut(
            id=fb.id, flat_id=fb.flat_id,
            flat_number=fb.flat.flat_number if fb.flat else None,
            owner_name=fb.flat.owner_name if fb.flat else None,
            email=fb.flat.email if fb.flat else None,
            units_consumed=fb.units_consumed,
            bill_excl_taxes=fb.bill_excl_taxes,
            mseb_taxes=fb.mseb_taxes,
            electricity_charges_incl_tax=fb.electricity_charges_incl_tax,
            indram_charges=fb.indram_charges,
            total_payable=fb.total_payable,
            pdf_s3_key=fb.pdf_s3_key,
            email_status=fb.email_status,
            email_sent_at=fb.email_sent_at,
            created_at=fb.created_at,
        )
        for fb in mb.flat_bills
    ]
    return {
        "id": mb.id, "meter_id": mb.meter_id,
        "meter_number": meter.meter_number, "meter_label": meter.label,
        "billing_month": mb.billing_month, "tariff": mb.tariff,
        "total_bill_amount": mb.total_bill_amount,
        "total_units_consumed": mb.total_units_consumed,
        "effective_unit_rate": mb.effective_unit_rate,
        "due_date": mb.due_date, "created_at": mb.created_at,
        "flat_bills": flat_bills_out,
    }


@router.delete("/{monthly_bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monthly_bill(
    monthly_bill_id: int,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_society_admin),
):
    society = await _get_society_for_admin(current_user, db)

    mb = await db.get(MonthlyBill, monthly_bill_id)
    if not mb:
        raise HTTPException(status_code=404, detail="Monthly bill not found")

    meter = await db.get(Meter, mb.meter_id)
    if not meter or meter.society_id != society.id:
        raise HTTPException(status_code=403, detail="Access denied")

    billing_month = mb.billing_month
    due_date      = mb.due_date

    await db.delete(mb)
    await db.commit()

    # Recalculate Indram bill after deletion (may reduce or delete it)
    asyncio.create_task(_dispatch_indram_bill(
        society_id=society.id,
        billing_month=billing_month,
        due_date=due_date,
    ))