"""
app/models/ticket.py
--------------------
Support ticket model.

Ticket flow:
  open → in_progress → resolved | closed

Roles:
  - super_admin  : sees ALL tickets across all societies
  - society_admin: sees only tickets for their society

Indexes
───────
Every column that appears in a WHERE or ORDER BY clause has an index:
  - society_id   : scope filter for society_admin list view
  - status       : status filter on list view
  - priority     : priority filter on list view
  - category     : category filter on list view
  - created_at   : ORDER BY on list view
  - ticket_id    : FK join in comment count subquery
"""

from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class TicketStatus(str, enum.Enum):
    open        = "open"
    in_progress = "in_progress"
    resolved    = "resolved"
    closed      = "closed"


class TicketPriority(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


class TicketCategory(str, enum.Enum):
    billing  = "billing"
    charger  = "charger"
    rfid     = "rfid"
    account  = "account"
    other    = "other"


class Ticket(Base):
    __tablename__ = "tickets"

    id:          Mapped[int]            = mapped_column(primary_key=True)
    title:       Mapped[str]            = mapped_column(String(255), nullable=False)
    description: Mapped[str]            = mapped_column(Text, nullable=False)

    status:   Mapped[TicketStatus]   = mapped_column(
        SAEnum(TicketStatus,   name="ticket_status"),   default=TicketStatus.open,     nullable=False
    )
    priority: Mapped[TicketPriority] = mapped_column(
        SAEnum(TicketPriority, name="ticket_priority"), default=TicketPriority.medium, nullable=False
    )
    category: Mapped[TicketCategory] = mapped_column(
        SAEnum(TicketCategory, name="ticket_category"), default=TicketCategory.other,  nullable=False
    )

    created_by_id:  Mapped[int]      = mapped_column(ForeignKey("users.id",     ondelete="SET NULL"), nullable=True)
    society_id:     Mapped[int|None] = mapped_column(ForeignKey("societies.id", ondelete="SET NULL"), nullable=True)
    assigned_to_id: Mapped[int|None] = mapped_column(ForeignKey("users.id",     ondelete="SET NULL"), nullable=True)

    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:  Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    created_by:  Mapped["User"]                = relationship("User", foreign_keys=[created_by_id])
    assigned_to: Mapped["User|None"]           = relationship("User", foreign_keys=[assigned_to_id])
    society:     Mapped["Society|None"]        = relationship("Society")
    comments:    Mapped[list["TicketComment"]] = relationship(
        "TicketComment", back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketComment.created_at",
    )

    __table_args__ = (
        # List view filters
        Index("ix_tickets_society_id",  "society_id"),
        Index("ix_tickets_status",      "status"),
        Index("ix_tickets_priority",    "priority"),
        Index("ix_tickets_category",    "category"),
        # Default sort column
        Index("ix_tickets_created_at",  "created_at"),
        # Composite: the most common query pattern — society + status + created_at
        Index("ix_tickets_society_status_created", "society_id", "status", "created_at"),
    )


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id:          Mapped[int]      = mapped_column(primary_key=True)
    ticket_id:   Mapped[int]      = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    author_id:   Mapped[int]      = mapped_column(ForeignKey("users.id",   ondelete="SET NULL"), nullable=True)
    body:        Mapped[str]      = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool]     = mapped_column(default=False)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="comments")
    author: Mapped["User"]   = relationship("User", foreign_keys=[author_id])

    __table_args__ = (
        # Heavily used in the correlated subquery (COUNT WHERE ticket_id = ?)
        Index("ix_ticket_comments_ticket_id", "ticket_id"),
    )