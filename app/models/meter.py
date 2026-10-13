"""
app/models/meter.py
-------------------
Meter represents a physical MSEB electricity meter installed in a society.
One society can have multiple meters (typically 2-4).
Each meter has multiple chargers assigned to it.
Billing is generated per meter, not per society.
"""

from datetime import datetime
from sqlalchemy import String, Numeric, Text, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Meter(Base):
    __tablename__ = "meters"

    id:               Mapped[int]        = mapped_column(primary_key=True)
    society_id:       Mapped[int]        = mapped_column(
                                              ForeignKey("societies.id", ondelete="CASCADE"),
                                              nullable=False,
                                              index=True,
                                          )
    meter_number:     Mapped[str]        = mapped_column(String(100), nullable=False)
    label:            Mapped[str]        = mapped_column(String(100), nullable=False)
    sanctioned_load:  Mapped[float|None] = mapped_column(Numeric(10, 2))   # in kW
    location:         Mapped[str|None]   = mapped_column(Text)
    created_at:       Mapped[datetime]   = mapped_column(
                                              DateTime(timezone=True), server_default=func.now()
                                          )

    # Relationships
    society:       Mapped["Society"]           = relationship("Society", back_populates="meters")
    chargers:      Mapped[list["Charger"]]     = relationship(
                                                     "Charger",
                                                     back_populates="meter",
                                                     cascade="all, delete-orphan",
                                                 )
    monthly_bills: Mapped[list["MonthlyBill"]] = relationship(
                                                     "MonthlyBill",
                                                     back_populates="meter",
                                                     cascade="all, delete-orphan",
                                                 )

    __table_args__ = (
        # Same meter_number cannot appear twice within the same society
        UniqueConstraint("society_id", "meter_number", name="uq_meter_society_meter_number"),
    )