from datetime import datetime, date
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Date, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MonthlyBill(Base):
    __tablename__ = "monthly_bills"

    id:                   Mapped[int]        = mapped_column(primary_key=True)
    meter_id:             Mapped[int]        = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False, index=True)
    billing_month:        Mapped[date]       = mapped_column(Date, nullable=False)
    tariff:               Mapped[float]      = mapped_column(Numeric(10, 4), nullable=False)
    total_bill_amount:    Mapped[float]      = mapped_column(Numeric(12, 2), nullable=False)
    total_units_consumed: Mapped[float]      = mapped_column(Numeric(12, 4), nullable=False)
    effective_unit_rate:  Mapped[float]      = mapped_column(Numeric(10, 4), nullable=False)
    due_date:             Mapped[date]       = mapped_column(Date, nullable=False)
    bill_photo_s3_key:    Mapped[str|None]   = mapped_column(String(500))
    created_by:           Mapped[int|None]   = mapped_column(ForeignKey("users.id"))
    created_at:           Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter:      Mapped["Meter"]          = relationship("Meter", back_populates="monthly_bills")
    flat_bills: Mapped[list["FlatBill"]] = relationship("FlatBill", back_populates="monthly_bill", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("meter_id", "billing_month", name="uq_monthly_bill_meter_month"),
    )


class FlatBill(Base):
    __tablename__ = "flat_bills"

    id:                           Mapped[int]           = mapped_column(primary_key=True)
    monthly_bill_id:              Mapped[int]           = mapped_column(ForeignKey("monthly_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    flat_id:                      Mapped[int]           = mapped_column(ForeignKey("flats.id", ondelete="CASCADE"), nullable=False, index=True)
    units_consumed:               Mapped[float]         = mapped_column(Numeric(12, 4), nullable=False, default=0)
    bill_excl_taxes:              Mapped[float]         = mapped_column(Numeric(12, 2), nullable=False, default=0)
    mseb_taxes:                   Mapped[float]         = mapped_column(Numeric(12, 2), nullable=False, default=0)
    electricity_charges_incl_tax: Mapped[float]         = mapped_column(Numeric(12, 2), nullable=False, default=0)
    indram_charges:               Mapped[float]         = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_payable:                Mapped[float]         = mapped_column(Numeric(12, 2), nullable=False, default=0)
    pdf_s3_key:                   Mapped[str|None]      = mapped_column(String(500))
    email_status:                 Mapped[str]           = mapped_column(String(20), default="pending")
    email_sent_at:                Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_at:                   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    monthly_bill: Mapped["MonthlyBill"] = relationship("MonthlyBill", back_populates="flat_bills")
    flat:         Mapped["Flat"]        = relationship("Flat")


class IndramBill(Base):
    """
    One Indram bill per society per billing month.
    Aggregates indram_charges from all flat_bills across all meters
    in that society for the given month.
    Auto-created/updated whenever flat bills are generated or deleted.
    """
    __tablename__ = "indram_bills"

    id:                  Mapped[int]           = mapped_column(primary_key=True)
    society_id:          Mapped[int]           = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), nullable=False, index=True)
    billing_month:       Mapped[date]          = mapped_column(Date, nullable=False)
    total_indram_amount: Mapped[float]         = mapped_column(Numeric(12, 2), nullable=False)
    total_units:         Mapped[float]         = mapped_column(Numeric(12, 4), nullable=False)
    due_date:            Mapped[date]          = mapped_column(Date, nullable=False)
    payment_status:      Mapped[str]           = mapped_column(String(20), default="unpaid")   # unpaid | paid
    paid_at:             Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    pdf_s3_key:          Mapped[str|None]      = mapped_column(String(500))
    email_status:        Mapped[str]           = mapped_column(String(20), default="pending")  # pending | sent | failed
    email_sent_at:       Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_at:          Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:          Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    society: Mapped["Society"] = relationship("Society")

    __table_args__ = (
        UniqueConstraint("society_id", "billing_month", name="uq_indram_bill_society_month"),
    )