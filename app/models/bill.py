"""
Billing models.

MonthlyBill  — one MSEB bill for one meter over a From–Till period (the name is
               kept for the existing tables/analytics; it is a period, not a month).
               draft → sent → cancelled (wrong bill reissued under a new one).
FlatBill     — one resident's bill under a MonthlyBill.
FlatBillSession — which charging sessions a flat bill charged for, so no session
               is ever billed twice; late records land on the next bill as "adjustment".
IndramBill   — Indram's GST tax invoice to the society, one per MonthlyBill send.
InvoiceCounter — running invoice number per financial year (IND/2026-27/0001).
"""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    String, Numeric, Integer, Boolean, ForeignKey, DateTime, Date,
    Index, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MonthlyBill(Base):
    __tablename__ = "monthly_bills"

    id:                   Mapped[int]           = mapped_column(primary_key=True)
    meter_id:             Mapped[int]           = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False, index=True)
    period_from:          Mapped[date]          = mapped_column(Date, nullable=False)
    period_till:          Mapped[date]          = mapped_column(Date, nullable=False)
    billing_month:        Mapped[date]          = mapped_column(Date, nullable=False)   # 1st of period_till's month — for reports
    tariff:               Mapped[Decimal]       = mapped_column(Numeric(10, 4), nullable=False)   # MSEB base rate per unit
    total_bill_amount:    Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False)   # MSEB bill amount
    total_units_consumed: Mapped[Decimal]       = mapped_column(Numeric(12, 4), nullable=False)   # MSEB bill units
    effective_unit_rate:  Mapped[Decimal]       = mapped_column(Numeric(10, 4), nullable=False)   # amount ÷ units
    due_date:             Mapped[date]          = mapped_column(Date, nullable=False)
    bill_photo_s3_key:    Mapped[str|None]      = mapped_column(String(500))
    status:               Mapped[str]           = mapped_column(String(20), nullable=False, default="draft", server_default="draft")  # draft | sent | cancelled
    sent_at:              Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    cancelled_at:         Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    replaces_id:          Mapped[int|None]      = mapped_column(ForeignKey("monthly_bills.id", ondelete="SET NULL"))
    reminder_sent_at:     Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_by:           Mapped[int|None]      = mapped_column(ForeignKey("users.id"))
    created_at:           Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter:      Mapped["Meter"]          = relationship("Meter", back_populates="monthly_bills")
    flat_bills: Mapped[list["FlatBill"]] = relationship("FlatBill", back_populates="monthly_bill", cascade="all, delete-orphan")

    __table_args__ = (
        # One open draft per meter; sent periods never start on the same day.
        # Overlap/gap rules are enforced in billing_service under a meter row lock.
        Index("uq_monthly_bills_meter_draft", "meter_id", unique=True,
              postgresql_where=text("status = 'draft'")),
        Index("uq_monthly_bills_meter_sent_from", "meter_id", "period_from", unique=True,
              postgresql_where=text("status = 'sent'")),
    )


class FlatBill(Base):
    __tablename__ = "flat_bills"

    id:                           Mapped[int]           = mapped_column(primary_key=True)
    monthly_bill_id:              Mapped[int]           = mapped_column(ForeignKey("monthly_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    flat_id:                      Mapped[int]           = mapped_column(ForeignKey("flats.id", ondelete="CASCADE"), nullable=False, index=True)
    bill_number:                  Mapped[str|None]      = mapped_column(String(30), unique=True)   # SOC12-000045, assigned on send

    # Copied at generation — an owner change only affects later bills
    flat_number:                  Mapped[str]           = mapped_column(String(50), nullable=False)
    owner_name:                   Mapped[str|None]      = mapped_column(String(255))
    email:                        Mapped[str|None]      = mapped_column(String(255))
    charger_id:                   Mapped[str|None]      = mapped_column(String(50))
    rfid_uids:                    Mapped[list]          = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    units_consumed:               Mapped[Decimal]       = mapped_column(Numeric(12, 4), nullable=False, default=0)
    adjustment_units:             Mapped[Decimal]       = mapped_column(Numeric(12, 4), nullable=False, default=0)   # part of units_consumed from earlier periods
    bill_excl_taxes:              Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)
    mseb_taxes:                   Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)
    electricity_charges_incl_tax: Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)
    indram_rate:                  Mapped[Decimal]       = mapped_column(Numeric(10, 4), nullable=False)
    indram_charges:               Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)   # before GST
    indram_cgst:                  Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)
    indram_sgst:                  Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)
    indram_total:                 Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)   # after GST
    total_payable:                Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # Payment — pending until the admin marks it; unpaid adds the late fee
    payment_status:               Mapped[str]           = mapped_column(String(20), nullable=False, default="pending", server_default="pending")  # pending | unpaid | paid
    late_fee_pct:                 Mapped[Decimal|None]  = mapped_column(Numeric(5, 2))
    late_fee:                     Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    marked_unpaid_at:             Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    paid_at:                      Mapped[datetime|None] = mapped_column(DateTime(timezone=True))

    pdf_s3_key:                   Mapped[str|None]      = mapped_column(String(500))
    late_pdf_s3_key:              Mapped[str|None]      = mapped_column(String(500))
    receipt_pdf_s3_key:           Mapped[str|None]      = mapped_column(String(500))
    email_status:                 Mapped[str]           = mapped_column(String(20), default="pending")
    email_sent_at:                Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at:             Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_at:                   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    monthly_bill: Mapped["MonthlyBill"]           = relationship("MonthlyBill", back_populates="flat_bills")
    flat:         Mapped["Flat"]                  = relationship("Flat", back_populates="flat_bills")
    sessions:     Mapped[list["FlatBillSession"]] = relationship("FlatBillSession", back_populates="flat_bill", cascade="all, delete-orphan")


class FlatBillSession(Base):
    __tablename__ = "flat_bill_sessions"

    flat_bill_id:  Mapped[int]  = mapped_column(ForeignKey("flat_bills.id", ondelete="CASCADE"), primary_key=True)
    session_id:    Mapped[int]  = mapped_column(ForeignKey("charging_sessions.id", ondelete="CASCADE"), primary_key=True, index=True)
    is_adjustment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    flat_bill: Mapped["FlatBill"] = relationship("FlatBill", back_populates="sessions")


class IndramBill(Base):
    """Indram's GST tax invoice to a society — issued automatically when a meter's bills are sent."""
    __tablename__ = "indram_bills"

    id:                  Mapped[int]           = mapped_column(primary_key=True)
    society_id:          Mapped[int]           = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), nullable=False, index=True)
    monthly_bill_id:     Mapped[int]           = mapped_column(ForeignKey("monthly_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number:      Mapped[str]           = mapped_column(String(30), nullable=False, unique=True)   # IND/2026-27/0001
    billing_month:       Mapped[date]          = mapped_column(Date, nullable=False)   # 1st of period_till's month — for reports
    period_from:         Mapped[date]          = mapped_column(Date, nullable=False)
    period_till:         Mapped[date]          = mapped_column(Date, nullable=False)
    total_units:         Mapped[Decimal]       = mapped_column(Numeric(12, 4), nullable=False)
    indram_rate:         Mapped[Decimal]       = mapped_column(Numeric(10, 4), nullable=False)
    total_indram_amount: Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False)   # charges before late fee and GST
    late_flag:           Mapped[bool]          = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    late_fee_pct:        Mapped[Decimal|None]  = mapped_column(Numeric(5, 2))
    late_fee:            Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    cgst:                Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False)   # 9% of charges + late fee
    sgst:                Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False)
    total_payable:       Mapped[Decimal]       = mapped_column(Numeric(12, 2), nullable=False)
    society_gstin:       Mapped[str|None]      = mapped_column(String(15))
    due_date:            Mapped[date]          = mapped_column(Date, nullable=False)
    status:              Mapped[str]           = mapped_column(String(20), nullable=False, default="issued", server_default="issued")   # issued | cancelled
    payment_status:      Mapped[str]           = mapped_column(String(20), nullable=False, default="unpaid", server_default="unpaid")   # unpaid | paid
    paid_at:             Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    replaces_id:         Mapped[int|None]      = mapped_column(ForeignKey("indram_bills.id", ondelete="SET NULL"))
    pdf_s3_key:          Mapped[str|None]      = mapped_column(String(500))
    receipt_pdf_s3_key:  Mapped[str|None]      = mapped_column(String(500))
    email_status:        Mapped[str]           = mapped_column(String(20), default="pending")  # pending | sent | failed
    email_sent_at:       Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at:    Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_at:          Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:          Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    society:      Mapped["Society"]     = relationship("Society")
    monthly_bill: Mapped["MonthlyBill"] = relationship("MonthlyBill")


class InvoiceCounter(Base):
    """Next Indram invoice number per financial year — taken with SELECT … FOR UPDATE."""
    __tablename__ = "invoice_counters"

    financial_year: Mapped[str] = mapped_column(String(7), primary_key=True)   # "2026-27"
    last_no:        Mapped[int] = mapped_column(Integer, nullable=False, default=0)
