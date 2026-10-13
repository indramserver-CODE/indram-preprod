from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Flat(Base):
    __tablename__ = "flats"

    id:          Mapped[int]      = mapped_column(primary_key=True)
    society_id:  Mapped[int]      = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    flat_number: Mapped[str]      = mapped_column(String(50), nullable=False)
    owner_name:  Mapped[str|None] = mapped_column(String(255))
    email:       Mapped[str|None] = mapped_column(String(255))
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    society:    Mapped["Society"]        = relationship("Society", back_populates="flats")
    charger:    Mapped["Charger|None"]   = relationship("Charger", back_populates="flat", uselist=False, cascade="all, delete-orphan")
    rfid_cards: Mapped[list["RFIDCard"]] = relationship("RFIDCard", back_populates="flat", cascade="all, delete-orphan")
    flat_bills: Mapped[list["FlatBill"]] = relationship("FlatBill", back_populates="flat", cascade="all, delete-orphan")