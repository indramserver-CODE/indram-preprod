from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, DateTime, Numeric, func
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
    created_at:   Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    flats:          Mapped[list["Flat"]]         = relationship("Flat", back_populates="society", cascade="all, delete-orphan")
    meters:         Mapped[list["Meter"]]        = relationship("Meter", back_populates="society", cascade="all, delete-orphan")
    society_admins: Mapped[list["SocietyAdmin"]] = relationship("SocietyAdmin", back_populates="society", cascade="all, delete-orphan")