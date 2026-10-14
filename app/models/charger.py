from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Charger(Base):
    __tablename__ = "chargers"

    id:           Mapped[int]           = mapped_column(primary_key=True)
    meter_id:     Mapped[int]           = mapped_column(
                                              ForeignKey("meters.id", ondelete="CASCADE"),
                                              nullable=False,
                                              index=True,
                                          )
    flat_id:      Mapped[int]           = mapped_column(
                                              ForeignKey("flats.id", ondelete="CASCADE"),
                                              nullable=False,
                                              unique=True,   # 1:1 charger ↔ flat
                                          )
    charger_id:   Mapped[str]           = mapped_column(String(50), nullable=False, unique=True)
    fw_version:   Mapped[str|None]      = mapped_column(String(20))
    is_active:    Mapped[bool]          = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))   # last message from the charger itself

    # Live state, kept up to date from charger messages (app/services/charger_state.py)
    status:            Mapped[str]           = mapped_column(String(20), nullable=False, default="never_connected",
                                                             server_default="never_connected")
                                                             # charging | available | locked | fault | offline | never_connected
    fault_code:        Mapped[str|None]      = mapped_column(String(10))    # blocking fault: E04, E08, 504
    locked:            Mapped[bool]          = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    lock_reasons:      Mapped[list]          = mapped_column(JSONB, nullable=False, default=list, server_default="[]")  # billing | society | tamper
    connection_type:   Mapped[str]           = mapped_column(String(10), nullable=False, default="hub", server_default="hub")  # hub | mesh
    status_updated_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    last_reset_reason: Mapped[str|None]      = mapped_column(String(50))
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    meter:    Mapped["Meter"]                  = relationship("Meter", back_populates="chargers")
    flat:     Mapped["Flat"]                   = relationship("Flat", back_populates="charger")
    sessions: Mapped[list["ChargingSession"]]  = relationship(
                                                     "ChargingSession",
                                                     back_populates="charger",
                                                     foreign_keys="ChargingSession.charger_id",
                                                 )