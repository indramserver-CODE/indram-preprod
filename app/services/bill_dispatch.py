"""
app/services/bill_dispatch.py
-----------------------------
Background work after a bill is sent: build PDFs, store them in S3, send emails.
Runs in its own DB session (asyncio.create_task) so the API responds immediately.

  dispatch_sent_bill(monthly_bill_id)
    - each resident: bill PDF on the society letterhead → email (with "use this new
      bill, ignore the old one" when the bill was reissued)
    - society admins: society total / MSEB / Indram + GST summaries
    - society admins: Indram GST tax invoice for this send

  dispatch_unpaid(flat_bill_id)   — bill with late fee → resident ("service being disabled")
  dispatch_receipts(flat_bill_ids) — receipt on the letterhead → resident
  dispatch_invoice_late(invoice_id) — invoice with late fee → society admins
  store_invoice_receipt(invoice_id) — receipt PDF for a paid invoice → S3 (downloaded from Indram Bills)

  invoice_pdf / invoice_receipt_pdf — bytes for download: S3 copy, else rebuilt from the saved figures
  build_flat_bill_pdf / build_flat_receipt_pdf / build_society_bill_pdf — rebuild resident documents
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.models.bill import MonthlyBill, FlatBill, FlatBillSession, IndramBill
from app.models.meter import Meter
from app.models.session import ChargingSession
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.services import storage
from app.services.billing_calc import IST
from app.services.email_service import (
    send_bill_email, send_society_bills_email, send_indram_bill_email, send_unpaid_email, send_receipt_email,
    send_invoice_late_email,
)
from app.services.pdf_service import (
    generate_resident_bill_pdf, generate_society_bill_pdf, generate_indram_invoice_pdf,
    generate_resident_receipt_pdf, generate_indram_receipt_pdf,
)

logger = logging.getLogger(__name__)


# ── Context builders (shared with later payment / receipt PDFs) ───────

def society_ctx(society: Society) -> dict:
    return {k: getattr(society, k) for k in (
        "name", "address", "gstin", "payee_name", "bank_name", "bank_account_no",
        "bank_ifsc", "upi_id", "payment_note",
    )}


def bill_ctx(mb: MonthlyBill, meter: Meter) -> dict:
    return {
        "period_from":    mb.period_from,
        "period_till":    mb.period_till,
        "due_date":       mb.due_date,
        "tariff":         mb.tariff,
        "effective_rate": mb.effective_unit_rate,
        "mseb_amount":    mb.total_bill_amount,
        "mseb_units":     mb.total_units_consumed,
        "meter_label":    f"{meter.label} ({meter.meter_number})",
    }


def flat_ctx(fb: FlatBill) -> dict:
    return {c.key: getattr(fb, c.key) for c in FlatBill.__table__.columns}


def indram_ctx() -> dict:
    return {"legal_name": settings.INDRAM_LEGAL_NAME, "address": settings.INDRAM_ADDRESS,
            "gstin": settings.INDRAM_GSTIN}


async def flat_sessions(db, flat_bill_id: int) -> list[dict]:
    rows = (await db.execute(
        select(ChargingSession.started_at, ChargingSession.ended_at, ChargingSession.units_consumed,
               FlatBillSession.is_adjustment)
        .join(FlatBillSession, FlatBillSession.session_id == ChargingSession.id)
        .where(FlatBillSession.flat_bill_id == flat_bill_id)
        .order_by(ChargingSession.ended_at)
    )).all()
    return [{
        "started_at":    r.started_at.astimezone(IST) if r.started_at else None,
        "ended_at":      r.ended_at.astimezone(IST),
        "units":         Decimal(str(r.units_consumed or 0)),
        "is_adjustment": r.is_adjustment,
    } for r in rows]


async def society_admin_emails(db, society_id: int) -> list[str]:
    return list((await db.execute(
        select(User.email).join(SocietyAdmin, SocietyAdmin.user_id == User.id)
        .where(SocietyAdmin.society_id == society_id, User.email.is_not(None))
    )).scalars().all())


def invoice_ctx(inv: IndramBill, meter: Meter, replaces_number: str | None = None) -> dict:
    return {
        "invoice_number":      inv.invoice_number,
        "issued_on":           inv.created_at.astimezone(IST).date(),
        "period_from":         inv.period_from,
        "period_till":         inv.period_till,
        "due_date":            inv.due_date,
        "meter_label":         f"{meter.label} ({meter.meter_number})",
        "total_units":         inv.total_units,
        "indram_rate":         inv.indram_rate,
        "total_indram_amount": inv.total_indram_amount,
        "late_fee":            inv.late_fee,
        "late_fee_pct":        inv.late_fee_pct,
        "cgst":                inv.cgst,
        "sgst":                inv.sgst,
        "total_payable":       inv.total_payable,
        "replaces_number":     replaces_number,
    }


# ── After Send ────────────────────────────────────────────────────────

async def dispatch_sent_bill(monthly_bill_id: int):
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        mb = await db.get(MonthlyBill, monthly_bill_id)
        if not mb or mb.status != "sent":
            return
        meter   = await db.get(Meter, mb.meter_id)
        society = await db.get(Society, meter.society_id)
        soc, bill = society_ctx(society), bill_ctx(mb, meter)
        letterhead = storage.download(society.letterhead_s3_key)
        folder = f"bills/{society.id}/meter-{meter.id}/{mb.period_from}_{mb.period_till}"

        flat_bills = (await db.execute(
            select(FlatBill).where(FlatBill.monthly_bill_id == mb.id).order_by(FlatBill.flat_number)
        )).scalars().all()

        # Reissue: tell each resident which earlier bill number to ignore
        old_numbers: dict[int, str] = {}
        if mb.replaces_id:
            old_numbers = dict((await db.execute(
                select(FlatBill.flat_id, FlatBill.bill_number).where(FlatBill.monthly_bill_id == mb.replaces_id)
            )).all())

        for fb in flat_bills:
            try:
                pdf = generate_resident_bill_pdf(soc, bill, flat_ctx(fb), await flat_sessions(db, fb.id), letterhead)
                fb.pdf_s3_key = storage.upload(pdf, f"{folder}/{fb.bill_number}.pdf") or fb.pdf_s3_key
                if not fb.email:
                    logger.warning("No email for flat %s — bill %s not emailed", fb.flat_number, fb.bill_number)
                    fb.email_status = "failed"
                    continue
                ok = await send_bill_email(
                    to_email=fb.email, owner_name=fb.owner_name, flat_number=fb.flat_number,
                    society_name=society.name, period_from=mb.period_from, period_till=mb.period_till,
                    total_payable=Decimal(str(fb.total_payable)), due_date=mb.due_date,
                    pdf_bytes=pdf, bill_number=fb.bill_number,
                    replaces_bill_number=old_numbers.get(fb.flat_id),
                )
                fb.email_status  = "sent" if ok else "failed"
                fb.email_sent_at = datetime.now(timezone.utc) if ok else None
            except Exception as e:
                logger.exception("Flat bill dispatch error | bill=%s error=%s", fb.bill_number, e)
                fb.email_status = "failed"
            await db.commit()   # keep per-flat progress even if a later one fails

        admins = await society_admin_emails(db, society.id)
        flats  = [flat_ctx(fb) for fb in flat_bills]
        if flats and admins:
            label = f"{meter.label}_{mb.period_from}_{mb.period_till}"
            attachments = [
                (f"Society_Total_{label}.pdf", generate_society_bill_pdf("society", soc, bill, flats, letterhead)),
                (f"MSEB_Total_{label}.pdf",    generate_society_bill_pdf("mseb", soc, bill, flats)),
                (f"Indram_Total_{label}.pdf",  generate_society_bill_pdf("indram", soc, bill, flats)),
            ]
            total = sum((Decimal(str(f["total_payable"])) for f in flats), Decimal("0"))
            for to in admins:
                await send_society_bills_email(
                    to_email=to, society_name=society.name, meter_label=meter.label,
                    period_from=mb.period_from, period_till=mb.period_till, total_flats=len(flats),
                    society_total=total, attachments=attachments, replaced=bool(mb.replaces_id),
                )
        elif not admins:
            logger.warning("No society admin email for society=%s — summaries not sent", society.id)

        invoice = await db.scalar(
            select(IndramBill).where(IndramBill.monthly_bill_id == mb.id, IndramBill.status == "issued")
        )
        if invoice:
            await dispatch_invoice(db, invoice, meter, society, admins)

        logger.info("Bill dispatch complete | monthly_bill=%s flats=%s", mb.id, len(flat_bills))


async def dispatch_invoice(db, invoice: IndramBill, meter: Meter, society: Society, admins: list[str]):
    """(Re)build the invoice PDF, store it and email it to the society admins."""
    replaces_number = None
    if invoice.replaces_id:
        replaces_number = await db.scalar(select(IndramBill.invoice_number).where(IndramBill.id == invoice.replaces_id))
    pdf = generate_indram_invoice_pdf(indram_ctx(), society_ctx(society), invoice_ctx(invoice, meter, replaces_number))
    key = f"indram_invoices/{society.id}/{invoice.invoice_number.replace('/', '-')}.pdf"
    invoice.pdf_s3_key = storage.upload(pdf, key) or invoice.pdf_s3_key

    sent = False
    for to in admins:
        sent = await send_indram_bill_email(
            to_email=to, society_name=society.name, period_from=invoice.period_from,
            period_till=invoice.period_till, total_payable=Decimal(str(invoice.total_payable)),
            due_date=invoice.due_date, invoice_number=invoice.invoice_number, pdf_bytes=pdf,
            replaces_invoice_number=replaces_number,
        ) or sent
    invoice.email_status  = "sent" if sent else "failed"
    invoice.email_sent_at = datetime.now(timezone.utc) if sent else None
    await db.commit()


# ── After a payment status change ─────────────────────────────────────

async def _load_flat_bill(db, flat_bill_id: int):
    fb = await db.get(FlatBill, flat_bill_id)
    if not fb:
        return None
    mb      = await db.get(MonthlyBill, fb.monthly_bill_id)
    meter   = await db.get(Meter, mb.meter_id)
    society = await db.get(Society, meter.society_id)
    return fb, mb, meter, society


async def build_flat_bill_pdf(db, fb: FlatBill, mb: MonthlyBill, meter: Meter, society: Society,
                              with_late_fee: bool = False, letterhead: bytes | None = None) -> bytes:
    if letterhead is None:
        letterhead = storage.download(society.letterhead_s3_key)
    late = dict(late_fee=Decimal(str(fb.late_fee)), late_fee_pct=fb.late_fee_pct) if with_late_fee else {}
    return generate_resident_bill_pdf(society_ctx(society), bill_ctx(mb, meter), flat_ctx(fb),
                                      await flat_sessions(db, fb.id), letterhead, **late)


def build_flat_receipt_pdf(fb: FlatBill, mb: MonthlyBill, meter: Meter, society: Society,
                           letterhead: bytes | None = None) -> bytes:
    if letterhead is None:
        letterhead = storage.download(society.letterhead_s3_key)
    return generate_resident_receipt_pdf(society_ctx(society), bill_ctx(mb, meter), flat_ctx(fb), letterhead)


async def build_society_bill_pdf(db, kind: str, mb: MonthlyBill, meter: Meter, society: Society) -> bytes:
    flat_bills = (await db.execute(
        select(FlatBill).where(FlatBill.monthly_bill_id == mb.id).order_by(FlatBill.flat_number)
    )).scalars().all()
    letterhead = storage.download(society.letterhead_s3_key) if kind == "society" else None
    return generate_society_bill_pdf(kind, society_ctx(society), bill_ctx(mb, meter),
                                     [flat_ctx(fb) for fb in flat_bills], letterhead)


async def dispatch_unpaid(flat_bill_id: int):
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        loaded = await _load_flat_bill(db, flat_bill_id)
        if not loaded:
            return
        fb, mb, meter, society = loaded
        try:
            pdf = await build_flat_bill_pdf(db, fb, mb, meter, society, with_late_fee=True)
            key = f"bills/{society.id}/meter-{meter.id}/{mb.period_from}_{mb.period_till}/{fb.bill_number}_late.pdf"
            fb.late_pdf_s3_key = storage.upload(pdf, key) or fb.late_pdf_s3_key
            if fb.email:
                await send_unpaid_email(
                    to_email=fb.email, owner_name=fb.owner_name, flat_number=fb.flat_number,
                    society_name=society.name, bill_number=fb.bill_number,
                    total_with_late_fee=Decimal(str(fb.total_payable)) + Decimal(str(fb.late_fee)),
                    late_fee=Decimal(str(fb.late_fee)), pdf_bytes=pdf,
                )
            else:
                logger.warning("No email for flat %s — unpaid notice for %s not sent", fb.flat_number, fb.bill_number)
        except Exception as e:
            logger.exception("Unpaid dispatch error | bill=%s error=%s", fb.bill_number, e)
        await db.commit()


async def dispatch_receipts(flat_bill_ids: list[int]):
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        letterheads: dict[int, bytes | None] = {}
        for flat_bill_id in flat_bill_ids:
            loaded = await _load_flat_bill(db, flat_bill_id)
            if not loaded:
                continue
            fb, mb, meter, society = loaded
            if society.id not in letterheads:
                letterheads[society.id] = storage.download(society.letterhead_s3_key)
            try:
                pdf = build_flat_receipt_pdf(fb, mb, meter, society, letterheads[society.id])
                key = f"receipts/{society.id}/R-{fb.bill_number}.pdf"
                fb.receipt_pdf_s3_key = storage.upload(pdf, key) or fb.receipt_pdf_s3_key
                if fb.email:
                    await send_receipt_email(
                        to_email=fb.email, owner_name=fb.owner_name, flat_number=fb.flat_number,
                        society_name=society.name, bill_number=fb.bill_number,
                        amount=Decimal(str(fb.total_payable)) + Decimal(str(fb.late_fee)), pdf_bytes=pdf,
                    )
            except Exception as e:
                logger.exception("Receipt dispatch error | bill=%s error=%s", fb.bill_number, e)
            await db.commit()


# ── Indram invoice: late flag / paid / downloads ──────────────────────

async def _invoice_parts(db, invoice: IndramBill):
    mb      = await db.get(MonthlyBill, invoice.monthly_bill_id)
    meter   = await db.get(Meter, mb.meter_id)
    society = await db.get(Society, invoice.society_id)
    replaces_number = None
    if invoice.replaces_id:
        replaces_number = await db.scalar(select(IndramBill.invoice_number).where(IndramBill.id == invoice.replaces_id))
    return meter, society, invoice_ctx(invoice, meter, replaces_number)


async def build_invoice_pdf(db, invoice: IndramBill) -> bytes:
    _, society, ctx = await _invoice_parts(db, invoice)
    return generate_indram_invoice_pdf(indram_ctx(), society_ctx(society), ctx)


async def build_invoice_receipt_pdf(db, invoice: IndramBill) -> bytes:
    _, society, ctx = await _invoice_parts(db, invoice)
    paid_on = (invoice.paid_at or datetime.now(timezone.utc)).astimezone(IST).date()
    return generate_indram_receipt_pdf(indram_ctx(), society_ctx(society), ctx, paid_on)


async def invoice_pdf(db, invoice: IndramBill) -> bytes:
    return storage.download(invoice.pdf_s3_key) or await build_invoice_pdf(db, invoice)


async def invoice_receipt_pdf(db, invoice: IndramBill) -> bytes:
    return storage.download(invoice.receipt_pdf_s3_key) or await build_invoice_receipt_pdf(db, invoice)


def _invoice_key(invoice: IndramBill, suffix: str = "") -> str:
    return f"indram_invoices/{invoice.society_id}/{invoice.invoice_number.replace('/', '-')}{suffix}.pdf"


async def dispatch_invoice_late(invoice_id: int):
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        inv = await db.get(IndramBill, invoice_id)
        if not inv:
            return
        try:
            pdf = await build_invoice_pdf(db, inv)
            inv.pdf_s3_key = storage.upload(pdf, _invoice_key(inv, "_late")) or inv.pdf_s3_key
            fee_with_gst = (Decimal(str(inv.late_fee)) * Decimal("1.18")).quantize(Decimal("0.01"))
            for to in await society_admin_emails(db, inv.society_id):
                await send_invoice_late_email(
                    to_email=to, society_name=(await db.get(Society, inv.society_id)).name,
                    invoice_number=inv.invoice_number, late_fee=fee_with_gst,
                    total_payable=Decimal(str(inv.total_payable)), pdf_bytes=pdf,
                )
        except Exception as e:
            logger.exception("Invoice late dispatch error | invoice=%s error=%s", inv.invoice_number, e)
        await db.commit()


async def store_invoice_receipt(invoice_id: int):
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        inv = await db.get(IndramBill, invoice_id)
        if not inv:
            return
        try:
            pdf = await build_invoice_receipt_pdf(db, inv)
            inv.receipt_pdf_s3_key = storage.upload(pdf, _invoice_key(inv, "_receipt")) or inv.receipt_pdf_s3_key
        except Exception as e:
            logger.exception("Invoice receipt error | invoice=%s error=%s", inv.invoice_number, e)
        await db.commit()
