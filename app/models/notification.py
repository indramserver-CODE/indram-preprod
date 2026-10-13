from datetime import datetime
from sqlalchemy import String, Text, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Notification(Base):
    """
    Super admin dashboard notifications.
    flat_unpaid — "Flat A-1202 of Society X has been marked Unpaid" → switch charger off
    flat_paid   — "Flat A-1202 of Society X has paid its unpaid bill" → switch charger on
    """
    __tablename__ = "notifications"

    id:           Mapped[int]           = mapped_column(primary_key=True)
    type:         Mapped[str]           = mapped_column(String(30), nullable=False)
    society_id:   Mapped[int]           = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), nullable=False, index=True)
    flat_id:      Mapped[int|None]      = mapped_column(ForeignKey("flats.id", ondelete="SET NULL"))
    flat_bill_id: Mapped[int|None]      = mapped_column(ForeignKey("flat_bills.id", ondelete="SET NULL"))
    charger_id:   Mapped[str|None]      = mapped_column(String(50))
    message:      Mapped[str]           = mapped_column(Text, nullable=False)
    is_read:      Mapped[bool]          = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    actioned_at:  Mapped[datetime|None] = mapped_column(DateTime(timezone=True))   # charger switched off/on from the notification
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
