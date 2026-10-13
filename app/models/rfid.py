from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class RFIDCard(Base):
    __tablename__ = "rfid_cards"

    id:         Mapped[int]      = mapped_column(primary_key=True)
    flat_id:    Mapped[int]      = mapped_column(ForeignKey("flats.id", ondelete="CASCADE"), nullable=False)
    uid:        Mapped[str]      = mapped_column(String(50), nullable=False, unique=True)
    label:      Mapped[str|None] = mapped_column(String(100))
    is_active:  Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    flat: Mapped["Flat"] = relationship("Flat", back_populates="rfid_cards")
