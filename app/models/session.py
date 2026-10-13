from datetime import datetime
from sqlalchemy import String, Numeric, BigInteger, ForeignKey, ForeignKeyConstraint, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ChargingSession(Base):
    __tablename__ = "charging_sessions"

    id:             Mapped[int]        = mapped_column(primary_key=True)
    msg_id:         Mapped[str|None]   = mapped_column(String(50), unique=True)  # e.g. EZC001-0042-END
    session_id:     Mapped[int]        = mapped_column(BigInteger, nullable=False)   # per-charger counter, unique only with charger_id
    charger_id:     Mapped[str]        = mapped_column(String(50), ForeignKey("chargers.charger_id"), nullable=False)
    rfid_uid:       Mapped[str|None]   = mapped_column(String(50))
    start_kwhr:     Mapped[float|None] = mapped_column(Numeric(12, 4))
    end_kwhr:       Mapped[float|None] = mapped_column(Numeric(12, 4))
    units_consumed: Mapped[float|None] = mapped_column(Numeric(12, 4))
    start_epoch:    Mapped[int|None]   = mapped_column(BigInteger)               # Unix UTC seconds
    stop_epoch:     Mapped[int|None]   = mapped_column(BigInteger)               # Unix UTC seconds
    start_meter_kwh: Mapped[float|None] = mapped_column(Numeric(10, 4))          # PZEM absolute meter at start
    end_meter_kwh:  Mapped[float|None] = mapped_column(Numeric(10, 4))           # PZEM absolute meter at end
    offline:        Mapped[bool]       = mapped_column(default=False)             # True = delivered from EEPROM queue
    status:         Mapped[str]        = mapped_column(String(50), nullable=False, default="active")
    fault_code:     Mapped[str|None]   = mapped_column(String(100))
    temperature_c:  Mapped[float|None] = mapped_column(Numeric(6, 2))
    fw_version:     Mapped[str|None]   = mapped_column(String(20))
    started_at:     Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at:       Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_at:     Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("charger_id", "session_id", name="uq_charging_sessions_charger_session"),
    )

    # Relationships
    charger:    Mapped["Charger"]           = relationship("Charger", back_populates="sessions", foreign_keys=[charger_id])
    heartbeats: Mapped[list["Heartbeat"]]   = relationship("Heartbeat", back_populates="session", cascade="all, delete-orphan")


class Heartbeat(Base):
    __tablename__ = "heartbeats"

    id:          Mapped[int]      = mapped_column(primary_key=True)
    session_id:  Mapped[int]      = mapped_column(BigInteger, nullable=False)
    charger_id:  Mapped[str]      = mapped_column(String(50), nullable=False)
    status:      Mapped[str|None] = mapped_column(String(50))
    fault_code:  Mapped[str|None] = mapped_column(String(100))
    fw_version:  Mapped[str|None] = mapped_column(String(20))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["charger_id", "session_id"],
            ["charging_sessions.charger_id", "charging_sessions.session_id"],
            ondelete="CASCADE",
        ),
    )

    # Relationships
    session: Mapped["ChargingSession"] = relationship("ChargingSession", back_populates="heartbeats")


class OrphanMessage(Base):
    __tablename__ = "orphan_messages"

    id:          Mapped[int]      = mapped_column(primary_key=True)
    charger_id:  Mapped[str|None] = mapped_column(String(50))
    session_id:  Mapped[int|None] = mapped_column(BigInteger)
    event:       Mapped[str|None] = mapped_column(String(100))
    payload:     Mapped[str|None] = mapped_column(String)      # stored as JSONB in DB
    is_reviewed: Mapped[bool]     = mapped_column(default=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChargerStatus(Base):
    __tablename__ = "charger_status"

    id:             Mapped[int]        = mapped_column(primary_key=True)
    charger_id:     Mapped[str]        = mapped_column(String(50), nullable=False, unique=True)
    charger_status: Mapped[str|None]   = mapped_column(String(50))
    voltage:        Mapped[float|None] = mapped_column(Numeric(8, 2))
    current:        Mapped[float|None] = mapped_column(Numeric(8, 2))
    energy_kwh:     Mapped[float|None] = mapped_column(Numeric(12, 4))
    rfid_uid:       Mapped[str|None]   = mapped_column(String(50))
    duration_min:   Mapped[int|None]   = mapped_column()
    fault_code:     Mapped[str|None]   = mapped_column(String(100))
    temperature_c:  Mapped[float|None] = mapped_column(Numeric(6, 2))
    fw_version:     Mapped[str|None]   = mapped_column(String(20))
    device_datetime: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    received_at:    Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())