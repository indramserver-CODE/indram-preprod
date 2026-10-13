"""
app/services/billing_service.py
--------------------------------
Resident billing workflow (arithmetic lives in billing_calc):

  create_draft  — admin enters the MSEB bill for a meter + From–Till period →
                  draft MonthlyBill with one FlatBill per flat that charged, sessions
                  linked, nothing emailed. Returns the preview.
  send_bill     — draft → sent: bill numbers assigned, Indram GST invoice issued,
                  a reissued bill's predecessor (and its invoice) cancelled.
                  Caller commits, then dispatches PDFs + emails.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.models.bill import MonthlyBill, FlatBill, FlatBillSession, IndramBill, InvoiceCounter
from app.models.flat import Flat
from app.models.charger import Charger
from app.models.meter import Meter
from app.models.notification import Notification
from app.models.society import Society
from app.models.session import ChargingSession
from app.services import billing_calc as bc

logger = logging.getLogger(__name__)

ENDED_STATUSES = ("charging_ended", "charging_ended_error", "charging_stopped_by_admin")


class BillingError(ValueError):
    """A rule the admin broke — shown to them as a 400."""


def indram_rate_for(society: Society) -> Decimal:
    return Decimal(str(society.indram_rate)) if society.indram_rate is not None else bc.DEFAULT_INDRAM_RATE


async def get_sent_period_range(db: AsyncSession, meter_id: int,
                                exclude_monthly_bill_id: int | None = None) -> tuple[date | None, date | None]:
    """(first From, last Till) across the meter's sent bills — (None, None) before the first bill."""
    q = select(func.min(MonthlyBill.period_from), func.max(MonthlyBill.period_till)).where(
        MonthlyBill.meter_id == meter_id, MonthlyBill.status == "sent",
    )
    if exclude_monthly_bill_id is not None:
        q = q.where(MonthlyBill.id != exclude_monthly_bill_id)
    first_from, last_till = (await db.execute(q)).one()
    return first_from, last_till


async def collect_meter_sessions(
    db: AsyncSession,
    meter_id: int,
    period_from: date,
    period_till: date,
    first_sent_from: date | None,
    replacing_monthly_bill_id: int | None = None,
) -> list[dict]:
    """
    One entry per charger on the meter (flats with no usage included), each with the
    sessions this bill should charge for:
      - ended inside the period, and
      - not yet on another live bill — plus "adjustment" sessions that ended in an earlier
        period (after the meter's first bill started) but arrived after it was billed.
    replacing_monthly_bill_id: on a reissue, sessions on the bill being replaced count as unbilled.
    """
    start_utc, end_utc = bc.period_bounds_utc(period_from, period_till)
    floor_utc = bc.period_bounds_utc(first_sent_from, first_sent_from)[0] if first_sent_from else start_utc

    # Sessions already on a draft/sent bill (other than the one being replaced)
    billed = (
        select(FlatBillSession.session_id)
        .join(FlatBill, FlatBill.id == FlatBillSession.flat_bill_id)
        .join(MonthlyBill, MonthlyBill.id == FlatBill.monthly_bill_id)
        .where(MonthlyBill.status != "cancelled")
    )
    if replacing_monthly_bill_id is not None:
        billed = billed.where(MonthlyBill.id != replacing_monthly_bill_id)

    chargers = (await db.execute(
        select(Charger)
        .where(Charger.meter_id == meter_id)
        .options(selectinload(Charger.flat).selectinload(Flat.rfid_cards))
    )).scalars().all()
    if not chargers:
        return []

    sessions = (await db.execute(
        select(ChargingSession.id, ChargingSession.charger_id, ChargingSession.units_consumed,
               ChargingSession.ended_at)
        .where(
            ChargingSession.charger_id.in_([c.charger_id for c in chargers]),
            ChargingSession.status.in_(ENDED_STATUSES),
            ChargingSession.ended_at >= floor_utc,
            ChargingSession.ended_at < end_utc,
            ChargingSession.id.not_in(billed),
        )
        .order_by(ChargingSession.ended_at)
    )).all()

    by_charger: dict[str, list[dict]] = {c.charger_id: [] for c in chargers}
    for s in sessions:
        by_charger[s.charger_id].append({
            "session_id":    s.id,
            "units":         Decimal(str(s.units_consumed or 0)),
            "ended_at":      s.ended_at,
            "is_adjustment": s.ended_at < start_utc,
        })

    out = []
    for c in chargers:
        flat = c.flat
        rows = by_charger[c.charger_id]
        out.append({
            "flat_id":          flat.id,
            "flat_number":      flat.flat_number,
            "owner_name":       flat.owner_name,
            "email":            flat.email,
            "charger_id":       c.charger_id,
            "rfid_uids":        sorted(card.uid for card in flat.rfid_cards if card.is_active),
            "sessions":         rows,
            "units":            sum((r["units"] for r in rows), Decimal("0")),
            "adjustment_units": sum((r["units"] for r in rows if r["is_adjustment"]), Decimal("0")),
        })
    return out


# ── Draft + preview ───────────────────────────────────────────────────

async def create_draft(
    db: AsyncSession,
    meter: Meter,
    society: Society,
    period_from: date | None,
    period_till: date | None,
    due_date: date,
    tariff: Decimal,
    mseb_amount: Decimal,
    mseb_units: Decimal,
    created_by: int,
    bill_photo_s3_key: str | None = None,
    replacing: MonthlyBill | None = None,
) -> MonthlyBill:
    """
    Build a draft bill for the meter, replacing any earlier draft. With `replacing`
    (a wrong bill being reissued) the period is copied from that bill and its
    sessions are billed again; it is only cancelled when the new draft is sent.
    Does NOT commit.
    """
    # Serialise billing per meter — period and session checks below must not race
    await db.execute(select(Meter.id).where(Meter.id == meter.id).with_for_update())

    if tariff <= 0 or mseb_amount <= 0 or mseb_units <= 0:
        raise BillingError("MSEB amount, units and rate must all be greater than zero.")

    if replacing is not None:
        if replacing.meter_id != meter.id or replacing.status != "sent":
            raise BillingError("Only a sent bill of this meter can be reissued.")
        marked = await db.scalar(
            select(func.count(FlatBill.id)).where(
                FlatBill.monthly_bill_id == replacing.id, FlatBill.payment_status != "pending",
            )
        )
        if marked:
            raise BillingError("This bill already has flats marked Paid or Unpaid, so it can't be reissued.")
        period_from, period_till = replacing.period_from, replacing.period_till
        first_from, _ = await get_sent_period_range(db, meter.id)
    else:
        if period_from is None or period_till is None:
            raise BillingError("From and Till dates are required.")
        first_from, last_till = await get_sent_period_range(db, meter.id)
        error = bc.validate_period(period_from, period_till, last_till, bc.today_ist())
        if error:
            raise BillingError(error)

    if due_date <= period_till:
        raise BillingError("Due date must be after the Till date.")

    # One draft per meter — a new Generate replaces the previous preview
    old_drafts = (await db.execute(
        select(MonthlyBill).where(MonthlyBill.meter_id == meter.id, MonthlyBill.status == "draft")
    )).scalars().all()
    for d in old_drafts:
        await db.delete(d)
    await db.flush()

    eff_rate    = bc.effective_rate(mseb_amount, mseb_units)
    indram_rate = indram_rate_for(society)

    mb = MonthlyBill(
        meter_id=meter.id,
        period_from=period_from,
        period_till=period_till,
        billing_month=bc.billing_month_for(period_till),
        tariff=tariff,
        total_bill_amount=mseb_amount,
        total_units_consumed=mseb_units,
        effective_unit_rate=eff_rate,
        due_date=due_date,
        bill_photo_s3_key=bill_photo_s3_key or (replacing.bill_photo_s3_key if replacing else None),
        status="draft",
        replaces_id=replacing.id if replacing else None,
        created_by=created_by,
    )
    db.add(mb)
    await db.flush()

    flats = await collect_meter_sessions(
        db, meter.id, period_from, period_till, first_from,
        replacing_monthly_bill_id=replacing.id if replacing else None,
    )
    for f in flats:
        if f["units"] <= 0:
            continue   # no charging this period — no bill
        fb = FlatBill(
            monthly_bill_id=mb.id,
            flat_id=f["flat_id"],
            flat_number=f["flat_number"],
            owner_name=f["owner_name"],
            email=f["email"],
            charger_id=f["charger_id"],
            rfid_uids=f["rfid_uids"],
            adjustment_units=bc.round4(f["adjustment_units"]),
            email_status="pending",
            **bc.calculate_flat_bill(f["units"], tariff, eff_rate, indram_rate),
        )
        fb.sessions = [
            FlatBillSession(session_id=s["session_id"], is_adjustment=s["is_adjustment"])
            for s in f["sessions"]
        ]
        db.add(fb)

    await db.flush()
    logger.info("Draft bill created | meter=%s period=%s..%s replaces=%s",
                meter.id, period_from, period_till, mb.replaces_id)
    return mb


async def bill_preview(db: AsyncSession, mb: MonthlyBill) -> dict:
    """Totals the admin checks before clicking Send."""
    row = (await db.execute(
        select(
            func.count(FlatBill.id),
            func.coalesce(func.sum(FlatBill.units_consumed), 0),
            func.coalesce(func.sum(FlatBill.electricity_charges_incl_tax), 0),
            func.coalesce(func.sum(FlatBill.indram_total), 0),
            func.coalesce(func.sum(FlatBill.total_payable), 0),
            func.count(FlatBill.id).filter(FlatBill.adjustment_units > 0),
            func.count(FlatBill.id).filter(FlatBill.email.is_(None)),
        ).where(FlatBill.monthly_bill_id == mb.id)
    )).one()
    return {
        "monthly_bill_id":    mb.id,
        "status":             mb.status,
        "period_from":        mb.period_from,
        "period_till":        mb.period_till,
        "due_date":           mb.due_date,
        "effective_rate":     mb.effective_unit_rate,
        "replaces_id":        mb.replaces_id,
        "total_flats":        row[0],
        "total_units":        Decimal(str(row[1])),
        "total_electricity":  Decimal(str(row[2])),
        "total_indram":       Decimal(str(row[3])),
        "total_amount":       Decimal(str(row[4])),
        "flats_with_adjustments": row[5],
        "flats_without_email":    row[6],
    }


# ── Send ──────────────────────────────────────────────────────────────

async def next_invoice_number(db: AsyncSession, issued_on: date) -> str:
    """Atomically take the next IND/<FY>/<n> number — concurrent sends never share one."""
    fy = bc.financial_year(issued_on)
    n = (await db.execute(
        pg_insert(InvoiceCounter)
        .values(financial_year=fy, last_no=1)
        .on_conflict_do_update(index_elements=[InvoiceCounter.financial_year],
                               set_={"last_no": InvoiceCounter.last_no + 1})
        .returning(InvoiceCounter.last_no)
    )).scalar_one()
    return bc.format_invoice_number(fy, n)


async def _take_bill_numbers(db: AsyncSession, society_id: int, count: int) -> list[str]:
    last = (await db.execute(
        update(Society).where(Society.id == society_id)
        .values(bill_counter=Society.bill_counter + count)
        .returning(Society.bill_counter)
    )).scalar_one()
    return [bc.format_bill_number(society_id, n) for n in range(last - count + 1, last + 1)]


async def send_bill(db: AsyncSession, mb: MonthlyBill, society: Society) -> IndramBill | None:
    """
    draft → sent. Assigns bill numbers, cancels the bill being reissued (and its
    invoice), and issues the Indram GST invoice for this send. Does NOT commit.
    Returns the new invoice (None when there is nothing to invoice).
    """
    await db.execute(select(Meter.id).where(Meter.id == mb.meter_id).with_for_update())
    await db.refresh(mb)
    if mb.status != "draft":
        raise BillingError("Only a draft bill can be sent.")

    now = datetime.now(timezone.utc)
    old_invoice = None
    if mb.replaces_id:
        old = await db.get(MonthlyBill, mb.replaces_id)
        if old is None or old.status != "sent":
            raise BillingError("The bill being reissued is no longer active — generate it again.")
        old.status, old.cancelled_at = "cancelled", now
        old_invoice = await db.scalar(
            select(IndramBill).where(IndramBill.monthly_bill_id == old.id, IndramBill.status == "issued")
        )
        if old_invoice:
            old_invoice.status = "cancelled"
        await db.flush()   # free the (meter, period_from) slot before this bill takes it

    flat_bills = (await db.execute(
        select(FlatBill).where(FlatBill.monthly_bill_id == mb.id).order_by(FlatBill.flat_number)
    )).scalars().all()
    if flat_bills:
        for fb, number in zip(flat_bills, await _take_bill_numbers(db, society.id, len(flat_bills))):
            fb.bill_number = number

    mb.status, mb.sent_at = "sent", now
    await db.flush()

    charges = sum((Decimal(str(fb.indram_charges)) for fb in flat_bills), Decimal("0"))
    if charges <= 0:
        logger.info("Bill sent with no Indram charges — no invoice | monthly_bill=%s", mb.id)
        return None

    units   = sum((Decimal(str(fb.units_consumed)) for fb in flat_bills), Decimal("0"))
    invoice = IndramBill(
        society_id=society.id,
        monthly_bill_id=mb.id,
        invoice_number=await next_invoice_number(db, bc.today_ist()),
        billing_month=mb.billing_month,
        period_from=mb.period_from,
        period_till=mb.period_till,
        total_units=units,
        indram_rate=indram_rate_for(society),
        society_gstin=society.gstin,
        due_date=mb.due_date,
        replaces_id=old_invoice.id if old_invoice else None,
        email_status="pending",
        **bc.calculate_indram_invoice(charges),
    )
    db.add(invoice)
    await db.flush()
    logger.info("Bill sent | monthly_bill=%s flats=%s invoice=%s", mb.id, len(flat_bills), invoice.invoice_number)
    return invoice


# ── Payments ──────────────────────────────────────────────────────────
# pending → paid                    receipt
# pending → unpaid (after due date + grace days)   late fee added, bill re-sent,
#                                   super admin notified to switch the charger off
# unpaid  → paid                    late fee closed, receipt, super admin notified
#                                   to switch the charger back on

async def _notify(db: AsyncSession, kind: str, society: Society, fb: FlatBill, message: str):
    db.add(Notification(type=kind, society_id=society.id, flat_id=fb.flat_id, flat_bill_id=fb.id,
                        charger_id=fb.charger_id, message=message))


def _charger(fb: FlatBill) -> str:
    return f"charger {fb.charger_id}" if fb.charger_id else "the charger"


async def _lock_flat_bill(db: AsyncSession, flat_bill_id: int) -> tuple[FlatBill, MonthlyBill]:
    fb = await db.scalar(select(FlatBill).where(FlatBill.id == flat_bill_id).with_for_update())
    if fb is None:
        raise BillingError("Bill not found.")
    mb = await db.get(MonthlyBill, fb.monthly_bill_id)
    if mb.status != "sent":
        raise BillingError("Only sent bills can be marked Paid or Unpaid.")
    return fb, mb


async def mark_flat_paid(db: AsyncSession, flat_bill_id: int, society: Society) -> FlatBill:
    """Does NOT commit. Caller sends the receipt."""
    fb, _ = await _lock_flat_bill(db, flat_bill_id)
    if fb.payment_status == "paid":
        raise BillingError(f"Bill {fb.bill_number} is already marked Paid.")
    was_unpaid = fb.payment_status == "unpaid"
    fb.payment_status, fb.paid_at = "paid", datetime.now(timezone.utc)
    if was_unpaid:
        await _notify(db, "flat_paid", society, fb,
                      f"Flat {fb.flat_number} of {society.name} has paid its unpaid bill "
                      f"({fb.bill_number}). Switch {_charger(fb)} back on.")
    await db.flush()
    return fb


async def mark_flat_unpaid(db: AsyncSession, flat_bill_id: int, society: Society) -> FlatBill:
    """Adds the society's late fee. Does NOT commit. Caller re-sends the bill with the late fee."""
    fb, mb = await _lock_flat_bill(db, flat_bill_id)
    if fb.payment_status != "pending":
        raise BillingError(f"Bill {fb.bill_number} is already marked {fb.payment_status.capitalize()}.")
    allowed_from = bc.late_fee_allowed_from(mb.due_date, society.resident_late_fee_grace_days)
    if bc.today_ist() < allowed_from:
        raise BillingError(f"Bills can be marked Unpaid from {allowed_from:%d %b %Y} "
                           f"(due date {mb.due_date:%d %b %Y} + {society.resident_late_fee_grace_days} grace days).")
    pct = Decimal(str(society.resident_late_fee_pct))
    fb.payment_status   = "unpaid"
    fb.late_fee_pct     = pct
    fb.late_fee         = bc.late_fee(Decimal(str(fb.total_payable)), pct)
    fb.marked_unpaid_at = datetime.now(timezone.utc)
    await _notify(db, "flat_unpaid", society, fb,
                  f"Flat {fb.flat_number} of {society.name} has been marked Unpaid ({fb.bill_number}). "
                  f"Switch {_charger(fb)} off.")
    await db.flush()
    return fb


async def mark_all_pending_paid(db: AsyncSession, mb: MonthlyBill) -> list[int]:
    """Mark every still-pending flat of a sent bill Paid (flats marked Unpaid are left alone). Does NOT commit."""
    if mb.status != "sent":
        raise BillingError("Only sent bills can be marked Paid.")
    ids = (await db.execute(
        update(FlatBill)
        .where(FlatBill.monthly_bill_id == mb.id, FlatBill.payment_status == "pending")
        .values(payment_status="paid", paid_at=datetime.now(timezone.utc))
        .returning(FlatBill.id)
    )).scalars().all()
    return list(ids)


# ── Indram invoice: late flag + paid (super admin) ────────────────────

async def _lock_invoice(db: AsyncSession, invoice_id: int) -> IndramBill:
    inv = await db.scalar(select(IndramBill).where(IndramBill.id == invoice_id).with_for_update())
    if inv is None:
        raise BillingError("Invoice not found.")
    if inv.status != "issued":
        raise BillingError(f"Invoice {inv.invoice_number} has been cancelled.")
    return inv


async def raise_invoice_late_flag(db: AsyncSession, invoice_id: int) -> IndramBill:
    """Add the society's Indram late fee (GST on charges + fee). Does NOT commit. Caller re-sends the invoice."""
    inv = await _lock_invoice(db, invoice_id)
    if inv.payment_status == "paid":
        raise BillingError(f"Invoice {inv.invoice_number} is already paid.")
    if inv.late_flag:
        raise BillingError(f"Invoice {inv.invoice_number} is already flagged late.")
    society = await db.get(Society, inv.society_id)
    allowed_from = bc.late_fee_allowed_from(inv.due_date, society.indram_late_fee_grace_days)
    if bc.today_ist() < allowed_from:
        raise BillingError(f"Invoice {inv.invoice_number} can be flagged late from {allowed_from:%d %b %Y} "
                           f"(due date {inv.due_date:%d %b %Y} + {society.indram_late_fee_grace_days} grace days).")
    pct = Decimal(str(society.indram_late_fee_pct))
    for field, value in bc.calculate_indram_invoice(Decimal(str(inv.total_indram_amount)), pct).items():
        setattr(inv, field, value)
    inv.late_flag, inv.late_fee_pct = True, pct
    await db.flush()
    return inv


async def mark_invoice_paid(db: AsyncSession, invoice_id: int) -> IndramBill:
    """Clears the late flag (a late fee already added stays on the invoice — it was paid). Does NOT commit."""
    inv = await _lock_invoice(db, invoice_id)
    if inv.payment_status == "paid":
        raise BillingError(f"Invoice {inv.invoice_number} is already paid.")
    inv.payment_status, inv.paid_at, inv.late_flag = "paid", datetime.now(timezone.utc), False
    await db.flush()
    return inv
