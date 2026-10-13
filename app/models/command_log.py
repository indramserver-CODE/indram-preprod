"""
app/models/command_log.py
--------------------------
Audit log for cmd_ack and uid_ack messages received from chargers.

cmd_ack  — published after every command (DEACTIVATE, ACTIVE, ADDUID)
uid_ack  — published specifically after ADDUID with slot details

These are stored for audit, debugging and detecting failed commands.
"""

from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CommandLog(Base):
    __tablename__ = "command_logs"

    id:              Mapped[int]        = mapped_column(primary_key=True)
    charger_id:      Mapped[str]        = mapped_column(String(50), nullable=False)
    log_type:        Mapped[str]        = mapped_column(String(20), nullable=False)  # "cmd_ack" | "uid_ack"

    # cmd_ack fields
    cmd:             Mapped[str|None]   = mapped_column(String(50))   # DEACTIVATE | ACTIVE | ADDUID
    ok:              Mapped[bool|None]  = mapped_column(Boolean)       # True = success
    reason:          Mapped[str|None]   = mapped_column(String(100))   # failure reason if ok=False

    # uid_ack specific fields
    rfid_uid:        Mapped[str|None]   = mapped_column(String(50))
    slots_remaining: Mapped[int|None]   = mapped_column(Integer)

    # Common fields
    fw_version:      Mapped[str|None]   = mapped_column(String(20))
    received_at:     Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())


class PendingCommand(Base):
    """
    Tracks in-flight commands sent to chargers.
    Written before MQTT publish, resolved when cmd_ack/uid_ack arrives.
    Multi-instance safe — all state in DB, subscriber applies changes regardless
    of which instance handled the original API request.
    """
    __tablename__ = "pending_commands"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    charger_id:   Mapped[str]        = mapped_column(String(50), nullable=False)
    cmd:          Mapped[str]        = mapped_column(String(20), nullable=False)
    flat_id:      Mapped[int|None]   = mapped_column(ForeignKey("flats.id", ondelete="CASCADE"))
    rfid_uid:     Mapped[str|None]   = mapped_column(String(50))
    rfid_card_id: Mapped[int|None]   = mapped_column(ForeignKey("rfid_cards.id", ondelete="CASCADE"))
    status:       Mapped[str]        = mapped_column(String(20), nullable=False, default="pending")
    reason:       Mapped[str|None]   = mapped_column(String(100))
    created_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at:  Mapped[datetime|None] = mapped_column(DateTime(timezone=True))

    # Society-wide (DEACTIVATE_ALL / ACTIVATE_ALL) queue — one row per charger.
    # status stays 'pending' until the charger acks; the subscriber re-sends the
    # per-charger command on each heartbeat. expires_at is set far in the future.
    society_id:   Mapped[int|None]   = mapped_column(Integer)
    attempts:     Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    last_sent_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))