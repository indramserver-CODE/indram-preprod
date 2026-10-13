"""
app/services/billing_service.py
--------------------------------
Core billing calculation logic.

Formula reference (per spec):
  E = B ÷ U                          Effective unit rate (incl. taxes)
  bill_excl_taxes        = u × T     Base electricity (excl. taxes)
  electricity_incl_tax   = u × E     Electricity incl. all MSEB taxes
  mseb_taxes             = (u×E) − (u×T)
  indram_charges         = u × I     Where I = society's indram_rate (₹/kWh)
  total_payable          = (u×E) + (u×I)

Billing is per meter per month.
Indram bill is per society per month — aggregated across all meters.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.bill import MonthlyBill, FlatBill, IndramBill
from app.models.flat import Flat
from app.models.charger import Charger
from app.models.meter import Meter
from app.models.society import Society
from app.models.session import ChargingSession

logger = logging.getLogger(__name__)

DEFAULT_INDRAM_RATE = Decimal("1.50")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


async def get_flat_units_for_meter(
    db: AsyncSession,
    meter_id: int,
    billing_month: date,
) -> dict[int, Decimal]:
    year, month = billing_month.year, billing_month.month
    next_month  = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    result = await db.execute(
        select(
            Flat.id.label("flat_id"),
            func.coalesce(func.sum(ChargingSession.units_consumed), 0).label("units"),
        )
        .select_from(Charger)
        .join(Flat, Flat.id == Charger.flat_id)
        .outerjoin(
            ChargingSession,
            (ChargingSession.charger_id == Charger.charger_id)
            & ChargingSession.status.in_([
                "charging_ended", "charging_ended_error", "charging_stopped_by_admin",
            ])
            & (ChargingSession.ended_at >= billing_month)
            & (ChargingSession.ended_at < next_month),
        )
        .where(Charger.meter_id == meter_id)
        .group_by(Flat.id)
    )
    return {row.flat_id: Decimal(str(row.units)) for row in result.all()}


def calculate_flat_bill(units: Decimal, tariff: Decimal, effective_rate: Decimal, indram_rate: Decimal) -> dict:
    u = _round4(units)
    bill_excl_taxes              = _round2(u * tariff)
    electricity_charges_incl_tax = _round2(u * effective_rate)
    mseb_taxes                   = _round2(electricity_charges_incl_tax - bill_excl_taxes)
    indram_charges               = _round2(u * indram_rate)
    total_payable                = _round2(electricity_charges_incl_tax + indram_charges)
    return {
        "units_consumed":               u,
        "bill_excl_taxes":              bill_excl_taxes,
        "electricity_charges_incl_tax": electricity_charges_incl_tax,
        "mseb_taxes":                   mseb_taxes,
        "indram_charges":               indram_charges,
        "total_payable":                total_payable,
    }


async def upsert_indram_bill(
    db: AsyncSession,
    society_id: int,
    billing_month: date,
    due_date: date,
) -> IndramBill | None:
    """
    Recalculate the Indram bill for a society+month by summing all flat_bills.indram_charges
    across all meters in that society for the given month.

    - If total = 0 (e.g. all monthly bills deleted): delete the IndramBill if it exists → return None
    - If IndramBill doesn't exist: create it
    - If IndramBill exists: update amounts + due_date + updated_at

    Called after every flat bill generate or delete operation.
    Does NOT commit — caller handles commit.
    """
    # Aggregate indram_charges and units across all meters in this society for the month
    year, month = billing_month.year, billing_month.month
    next_month  = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    result = await db.execute(
        select(
            func.coalesce(func.sum(FlatBill.indram_charges), 0).label("total_indram"),
            func.coalesce(func.sum(FlatBill.units_consumed),  0).label("total_units"),
        )
        .join(MonthlyBill, MonthlyBill.id == FlatBill.monthly_bill_id)
        .join(Meter, Meter.id == MonthlyBill.meter_id)
        .where(
            Meter.society_id == society_id,
            MonthlyBill.billing_month >= billing_month,
            MonthlyBill.billing_month < next_month,
        )
    )
    row          = result.one()
    total_indram = Decimal(str(row.total_indram))
    total_units  = Decimal(str(row.total_units))

    # Fetch existing IndramBill
    existing = await db.execute(
        select(IndramBill).where(
            IndramBill.society_id    == society_id,
            IndramBill.billing_month == billing_month,
        )
    )
    indram_bill = existing.scalar_one_or_none()

    # If nothing to bill, delete any existing record and return
    if total_indram <= 0:
        if indram_bill:
            await db.delete(indram_bill)
            logger.info("IndramBill deleted (no remaining charges) | society=%s month=%s",
                        society_id, billing_month)
        return None

    if indram_bill:
        # Update existing
        indram_bill.total_indram_amount = total_indram
        indram_bill.total_units         = total_units
        indram_bill.due_date            = due_date
        indram_bill.updated_at          = datetime.now(timezone.utc)
        logger.info("IndramBill updated | society=%s month=%s total=₹%s",
                    society_id, billing_month, total_indram)
    else:
        # Create new
        indram_bill = IndramBill(
            society_id=society_id,
            billing_month=billing_month,
            total_indram_amount=total_indram,
            total_units=total_units,
            due_date=due_date,
            payment_status="unpaid",
            email_status="pending",
        )
        db.add(indram_bill)
        logger.info("IndramBill created | society=%s month=%s total=₹%s",
                    society_id, billing_month, total_indram)

    await db.flush()
    return indram_bill


async def generate_monthly_bills(
    db: AsyncSession,
    meter_id: int,
    billing_month: date,
    tariff: Decimal,
    total_bill_amount: Decimal,
    total_units_consumed: Decimal,
    due_date: date,
    created_by: int,
    bill_photo_s3_key: str | None = None,
) -> MonthlyBill:
    meter = await db.get(Meter, meter_id)
    if not meter:
        raise ValueError(f"Meter {meter_id} not found.")

    society = await db.get(Society, meter.society_id)
    if society and society.indram_rate is not None:
        indram_rate = Decimal(str(society.indram_rate))
        logger.info("Using society indram_rate=₹%s/kWh | meter=%s society=%s",
                    indram_rate, meter_id, society.name)
    else:
        indram_rate = DEFAULT_INDRAM_RATE
        logger.warning("indram_rate not set for society_id=%s — falling back to ₹%s | meter=%s",
                       meter.society_id, DEFAULT_INDRAM_RATE, meter_id)

    existing = await db.execute(
        select(MonthlyBill).where(
            MonthlyBill.meter_id == meter_id,
            MonthlyBill.billing_month == billing_month,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(
            f"Bills already generated for meter '{meter.label}' ({meter.meter_number}) "
            f"for {billing_month.strftime('%B %Y')}. Delete the existing bill first to regenerate."
        )

    if total_units_consumed <= 0:
        raise ValueError("Total units consumed must be greater than zero.")

    effective_rate = _round4(total_bill_amount / total_units_consumed)

    monthly_bill = MonthlyBill(
        meter_id=meter_id,
        billing_month=billing_month,
        tariff=tariff,
        total_bill_amount=total_bill_amount,
        total_units_consumed=total_units_consumed,
        effective_unit_rate=effective_rate,
        due_date=due_date,
        bill_photo_s3_key=bill_photo_s3_key,
        created_by=created_by,
    )
    db.add(monthly_bill)
    await db.flush()

    flat_units = await get_flat_units_for_meter(db, meter_id, billing_month)
    if not flat_units:
        raise ValueError(
            f"No chargers assigned to meter '{meter.label}' ({meter.meter_number}). "
            "Assign chargers before generating bills."
        )

    for flat_id, units in flat_units.items():
        line_items = calculate_flat_bill(units, tariff, effective_rate, indram_rate)
        db.add(FlatBill(monthly_bill_id=monthly_bill.id, flat_id=flat_id,
                        **line_items, email_status="pending"))

    await db.flush()
    await db.refresh(monthly_bill)
    logger.info("Generated bills | meter=%s month=%s flats=%s eff_rate=%s indram_rate=%s",
                meter_id, billing_month, len(flat_units), effective_rate, indram_rate)
    return monthly_bill