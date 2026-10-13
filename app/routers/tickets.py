"""
app/routers/tickets.py
----------------------
Support ticket endpoints.

Endpoint summary
────────────────
POST   /api/tickets/              → Create a ticket (any admin)
GET    /api/tickets/stats         → Aggregated counts by status (any admin, role-scoped)
GET    /api/tickets/              → Paginated ticket list (any admin, role-scoped)
GET    /api/tickets/{id}          → Ticket detail (any admin, role-scoped)
PATCH  /api/tickets/{id}          → Update status / priority / assignment (super admin)
DELETE /api/tickets/{id}          → Delete ticket (super admin)
POST   /api/tickets/{id}/comments → Add a comment (any admin)

Performance notes
─────────────────
- /stats     : single GROUP BY query, no ORM hydration — replaces the unfiltered
               full-list fetch that the frontend was doing just to count statuses
- list       : paginated (default 25/page) + correlated comment-count subquery
               → single DB round-trip, bounded result size regardless of ticket volume
- society_id : memoised on user object — no repeated extra query per request
- PATCH      : returns already-mutated ORM object — no second SELECT after commit
- POST comment: CommentOut built from in-memory objects — no re-query needed
"""

import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies.auth import require_super_admin, require_any_admin
from app.models.ticket import Ticket, TicketComment, TicketStatus
from app.models.user import User, SocietyAdmin
from app.schemas.ticket import (
    TicketCreate, TicketUpdate, TicketOut, TicketListItem,
    CommentCreate, CommentOut, TicketStats, PaginatedTickets,
)

router = APIRouter()

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX     = 100


# ──────────────────────────────────────────────────────────────────── #
#  Helpers
# ──────────────────────────────────────────────────────────────────── #

async def _get_society_id_for_user(user: User, db: AsyncSession) -> Optional[int]:
    """
    Return the society_id for a society_admin, or None for super_admin.
    Memoised on the user object — zero extra DB hits if called multiple times
    within the same request.
    """
    if user.role == "super_admin":
        return None
    if not hasattr(user, "_society_id_cache"):
        result = await db.execute(
            select(SocietyAdmin.society_id)
            .where(SocietyAdmin.user_id == user.id)
            .limit(1)
        )
        user._society_id_cache = result.scalar_one_or_none()
    return user._society_id_cache


def _comment_count_subquery():
    """
    Correlated scalar subquery — embedded into the list SELECT so comment
    counts arrive in the same round-trip as the ticket rows.
    """
    return (
        select(func.count(TicketComment.id))
        .where(TicketComment.ticket_id == Ticket.id)
        .correlate(Ticket)
        .scalar_subquery()
    )


def _apply_filters(q, status_filter, priority, category, search):
    """Apply shared filter clauses to any query."""
    if status_filter:
        q = q.where(Ticket.status == status_filter)
    if priority:
        q = q.where(Ticket.priority == priority)
    if category:
        q = q.where(Ticket.category == category)
    if search:
        q = q.where(Ticket.title.ilike(f"%{search}%"))
    return q


def _to_list_item(ticket: Ticket, comment_count: int = 0) -> TicketListItem:
    return TicketListItem(
        id=ticket.id,
        title=ticket.title,
        status=ticket.status,
        priority=ticket.priority,
        category=ticket.category,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        created_by_name=ticket.created_by.full_name if ticket.created_by else None,
        society_name=ticket.society.name if ticket.society else None,
        assigned_to_name=ticket.assigned_to.full_name if ticket.assigned_to else None,
        comment_count=comment_count,
    )


def _to_detail(ticket: Ticket) -> TicketOut:
    return TicketOut(
        id=ticket.id,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        category=ticket.category,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        created_by_name=ticket.created_by.full_name if ticket.created_by else None,
        created_by_email=ticket.created_by.email if ticket.created_by else None,
        society_name=ticket.society.name if ticket.society else None,
        assigned_to_name=ticket.assigned_to.full_name if ticket.assigned_to else None,
        comments=[
            CommentOut(
                id=c.id,
                body=c.body,
                is_internal=c.is_internal,
                created_at=c.created_at,
                author_name=c.author.full_name if c.author else None,
                author_role=c.author.role if c.author else None,
            )
            for c in ticket.comments
        ],
    )


# ──────────────────────────────────────────────────────────────────── #
#  Stats  —  single GROUP BY, no ORM hydration
# ──────────────────────────────────────────────────────────────────── #

@router.get("/stats", response_model=TicketStats)
async def get_ticket_stats(
    current_user: User         = Depends(require_any_admin),
    db:           AsyncSession = Depends(get_db),
):
    """
    Returns ticket counts grouped by status in a single aggregated DB query.
    The frontend calls this once on page load and caches the result for 60 s —
    replacing the previous pattern of fetching the entire unfiltered ticket list
    just to count statuses client-side.
    """
    q = select(
        Ticket.status,
        func.count(Ticket.id).label("cnt"),
    ).group_by(Ticket.status)

    if current_user.role == "society_admin":
        society_id = await _get_society_id_for_user(current_user, db)
        q = q.where(Ticket.society_id == society_id)

    rows = (await db.execute(q)).all()
    counts = {row.status: row.cnt for row in rows}

    total = sum(counts.values())
    return TicketStats(
        open=counts.get(TicketStatus.open, 0),
        in_progress=counts.get(TicketStatus.in_progress, 0),
        resolved=counts.get(TicketStatus.resolved, 0),
        closed=counts.get(TicketStatus.closed, 0),
        total=total,
    )


# ──────────────────────────────────────────────────────────────────── #
#  Create ticket
# ──────────────────────────────────────────────────────────────────── #

@router.post("/", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    current_user: User = Depends(require_any_admin),
    db: AsyncSession = Depends(get_db),
):
    society_id = await _get_society_id_for_user(current_user, db)

    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        category=payload.category,
        created_by_id=current_user.id,
        society_id=society_id,
        status=TicketStatus.open,
    )
    db.add(ticket)
    await db.flush()  # get ticket.id before loading relationships

    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.created_by),
            selectinload(Ticket.assigned_to),
            selectinload(Ticket.society),
            selectinload(Ticket.comments).selectinload(TicketComment.author),
        )
        .where(Ticket.id == ticket.id)
    )
    ticket = result.scalar_one()
    await db.commit()
    return _to_detail(ticket)


# ──────────────────────────────────────────────────────────────────── #
#  List tickets  —  paginated, single DB round-trip
# ──────────────────────────────────────────────────────────────────── #

@router.get("/", response_model=PaginatedTickets)
async def list_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority:      Optional[str] = Query(None),
    category:      Optional[str] = Query(None),
    search:        Optional[str] = Query(None),
    page:          int           = Query(1,                ge=1),
    page_size:     int           = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    current_user:  User          = Depends(require_any_admin),
    db:            AsyncSession  = Depends(get_db),
):
    # ── Base scope ────────────────────────────────────────────────
    scope_filter = []
    if current_user.role == "society_admin":
        society_id = await _get_society_id_for_user(current_user, db)
        scope_filter = [Ticket.society_id == society_id]

    # ── Total count (for pagination controls) — lightweight query ─
    count_q = select(func.count(Ticket.id)).where(*scope_filter)
    count_q = _apply_filters(count_q, status_filter, priority, category, search)
    total: int = (await db.execute(count_q)).scalar_one()

    # ── Paginated data query ──────────────────────────────────────
    offset = (page - 1) * page_size
    data_q = (
        select(
            Ticket,
            _comment_count_subquery().label("comment_count"),
        )
        .options(
            selectinload(Ticket.created_by),
            selectinload(Ticket.assigned_to),
            selectinload(Ticket.society),
        )
        .where(*scope_filter)
        .order_by(Ticket.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    data_q = _apply_filters(data_q, status_filter, priority, category, search)
    rows = (await db.execute(data_q)).all()

    items = [_to_list_item(ticket, count) for ticket, count in rows]
    return PaginatedTickets.build(items=items, total=total, page=page, page_size=page_size)


# ──────────────────────────────────────────────────────────────────── #
#  Get ticket detail
# ──────────────────────────────────────────────────────────────────── #

@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id:    int,
    current_user: User         = Depends(require_any_admin),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.created_by),
            selectinload(Ticket.assigned_to),
            selectinload(Ticket.society),
            selectinload(Ticket.comments).selectinload(TicketComment.author),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if current_user.role == "society_admin":
        society_id = await _get_society_id_for_user(current_user, db)
        if ticket.society_id != society_id:
            raise HTTPException(status_code=403, detail="Access denied")
        ticket.comments = [c for c in ticket.comments if not c.is_internal]

    return _to_detail(ticket)


# ──────────────────────────────────────────────────────────────────── #
#  Update ticket (super admin)  —  no second SELECT after commit
# ──────────────────────────────────────────────────────────────────── #

@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id:    int,
    payload:      TicketUpdate,
    current_user: User         = Depends(require_super_admin),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.created_by),
            selectinload(Ticket.assigned_to),
            selectinload(Ticket.society),
            selectinload(Ticket.comments).selectinload(TicketComment.author),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if payload.status is not None:
        ticket.status = payload.status
        ticket.resolved_at = (
            datetime.now(timezone.utc)
            if payload.status in (TicketStatus.resolved, TicketStatus.closed)
            else None
        )

    if payload.priority is not None:
        ticket.priority = payload.priority

    if payload.assigned_to_id is not None:
        assignee = await db.get(User, payload.assigned_to_id)
        if not assignee or assignee.role != "super_admin":
            raise HTTPException(status_code=400, detail="Assignee must be a super admin")
        ticket.assigned_to_id = payload.assigned_to_id
        ticket.assigned_to = assignee

    ticket.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _to_detail(ticket)


# ──────────────────────────────────────────────────────────────────── #
#  Delete ticket (super admin)
# ──────────────────────────────────────────────────────────────────── #

@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id:    int,
    current_user: User         = Depends(require_super_admin),
    db:           AsyncSession = Depends(get_db),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await db.delete(ticket)
    await db.commit()


# ──────────────────────────────────────────────────────────────────── #
#  Add comment  —  response built from in-memory objects, no re-query
# ──────────────────────────────────────────────────────────────────── #

@router.post("/{ticket_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    ticket_id:    int,
    payload:      CommentCreate,
    current_user: User         = Depends(require_any_admin),
    db:           AsyncSession = Depends(get_db),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_internal = payload.is_internal and current_user.role == "super_admin"

    comment = TicketComment(
        ticket_id=ticket_id,
        author_id=current_user.id,
        body=payload.body,
        is_internal=is_internal,
    )
    db.add(comment)

    if current_user.role == "super_admin" and ticket.status == TicketStatus.open:
        ticket.status = TicketStatus.in_progress

    await db.flush()
    await db.commit()

    return CommentOut(
        id=comment.id,
        body=comment.body,
        is_internal=comment.is_internal,
        created_at=comment.created_at,
        author_name=current_user.full_name,
        author_role=current_user.role,
    )