from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, Integer, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Society(Base):
    __tablename__ = "societies"

    id:           Mapped[int]            = mapped_column(primary_key=True)
    name:         Mapped[str]            = mapped_column(String(255), nullable=False)
    address:      Mapped[str | None]     = mapped_column(Text)
    indram_rate:  Mapped[Decimal | None] = mapped_column(
                                               Numeric(10, 4),
                                               nullable=True,
                                               comment="INDRAM platform charge per kWh. Falls back to ₹1.50 if not set.",
                                           )
    gstin:        Mapped[str | None]     = mapped_column(String(15))

    # Late fee — set by super admin. Applied to that bill only, once
    # grace_days have passed after the due date.
    resident_late_fee_pct:        Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("5"), server_default="5")
    resident_late_fee_grace_days: Mapped[int]     = mapped_column(Integer, nullable=False, default=0, server_default="0")
    indram_late_fee_pct:          Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("5"), server_default="5")
    indram_late_fee_grace_days:   Mapped[int]     = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Letterhead + payment details — set by the society admin, printed on every resident bill/receipt
    letterhead_s3_key: Mapped[str | None] = mapped_column(String(500))
    payee_name:        Mapped[str | None] = mapped_column(String(255))
    bank_name:         Mapped[str | None] = mapped_column(String(255))
    bank_account_no:   Mapped[str | None] = mapped_column(String(50))
    bank_ifsc:         Mapped[str | None] = mapped_column(String(20))
    upi_id:            Mapped[str | None] = mapped_column(String(100))
    payment_note:      Mapped[str | None] = mapped_column(Text)

    # Running resident bill number: SOC{id}-{bill_counter:06d}
    bill_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at:   Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    flats:          Mapped[list["Flat"]]         = relationship("Flat", back_populates="society", cascade="all, delete-orphan")
    meters:         Mapped[list["Meter"]]        = relationship("Meter", back_populates="society", cascade="all, delete-orphan")
    society_admins: Mapped[list["SocietyAdmin"]] = relationship("SocietyAdmin", back_populates="society", cascade="all, delete-orphan")
