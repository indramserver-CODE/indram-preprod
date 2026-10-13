"""
app/schemas/ticket.py
---------------------
Pydantic request/response schemas for the ticketing system.
"""

import math
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.ticket import TicketStatus, TicketPriority, TicketCategory


# ── Comment schemas ────────────────────────────────────────────────── #

class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    is_internal: bool = False


class CommentOut(BaseModel):
    id:          int
    body:        str
    is_internal: bool
    created_at:  datetime
    author_name: Optional[str] = None
    author_role: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Ticket schemas ─────────────────────────────────────────────────── #

class TicketCreate(BaseModel):
    title:       str            = Field(..., min_length=3, max_length=255)
    description: str            = Field(..., min_length=10, max_length=5000)
    priority:    TicketPriority = TicketPriority.medium
    category:    TicketCategory = TicketCategory.other


class TicketUpdate(BaseModel):
    """Super admin can update status, priority, and assignment."""
    status:         Optional[TicketStatus]   = None
    priority:       Optional[TicketPriority] = None
    assigned_to_id: Optional[int]            = None


class TicketOut(BaseModel):
    id:               int
    title:            str
    description:      str
    status:           TicketStatus
    priority:         TicketPriority
    category:         TicketCategory
    created_at:       datetime
    updated_at:       datetime
    resolved_at:      Optional[datetime] = None

    # Denormalised for display
    created_by_name:  Optional[str] = None
    created_by_email: Optional[str] = None
    society_name:     Optional[str] = None
    assigned_to_name: Optional[str] = None

    comments: list[CommentOut] = []

    model_config = {"from_attributes": True}


class TicketListItem(BaseModel):
    """Lightweight version for list views — no comments."""
    id:               int
    title:            str
    status:           TicketStatus
    priority:         TicketPriority
    category:         TicketCategory
    created_at:       datetime
    updated_at:       datetime
    created_by_name:  Optional[str] = None
    society_name:     Optional[str] = None
    assigned_to_name: Optional[str] = None
    comment_count:    int = 0

    model_config = {"from_attributes": True}


# ── Stats schema ───────────────────────────────────────────────────── #

class TicketStats(BaseModel):
    """
    Aggregated ticket counts returned by GET /api/tickets/stats.
    Computed with a single GROUP BY query — no ORM hydration, very fast.
    Scoped by role: super_admin sees all societies, society_admin sees only theirs.
    """
    open:        int = 0
    in_progress: int = 0
    resolved:    int = 0
    closed:      int = 0
    total:       int = 0


# ── Paginated list schema ──────────────────────────────────────────── #

class PaginatedTickets(BaseModel):
    """
    Paginated wrapper for GET /api/tickets/.
    `total` is the count of rows matching the current filters (used by the
    frontend to calculate how many pages exist without fetching all rows).
    """
    items:     list[TicketListItem]
    total:     int    # total rows matching current filters
    page:      int    # current page (1-based)
    page_size: int    # rows per page
    pages:     int    # ceil(total / page_size)

    @classmethod
    def build(cls, items: list[TicketListItem], total: int, page: int, page_size: int) -> "PaginatedTickets":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )