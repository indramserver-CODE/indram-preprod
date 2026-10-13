"""
app/routers/notifications.py
----------------------------
Super admin only. Billing notifications that need a charger switched off / on.

GET /api/notifications?unread_only=&society_id=&limit=  — newest first, with unread count
PUT /api/notifications/{id}/read                         — mark one read
PUT /api/notifications/read-all                          — mark all read
PUT /api/notifications/{id}/actioned                     — charger switched (also marks read)

The switch itself uses the existing RFID endpoints, which handle offline chargers:
  flat_unpaid → POST /api/rfid/flat/{flat_id}/deactivate
  flat_paid   → POST /api/rfid/flat/{flat_id}/activate
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_super_admin
from app.models.notification import Notification
from app.models.society import Society

router = APIRouter()

ACTIONS = {
    "flat_unpaid": ("deactivate", "/api/rfid/flat/{flat_id}/deactivate"),
    "flat_paid":   ("activate",   "/api/rfid/flat/{flat_id}/activate"),
}


class NotificationOut(BaseModel):
    id:            int
    type:          str
    message:       str
    society_id:    int
    society_name:  str | None
    flat_id:       int | None
    flat_bill_id:  int | None
    charger_id:    str | None
    action:        str | None   # deactivate | activate
    action_url:    str | None
    is_read:       bool
    actioned_at:   datetime | None
    created_at:    datetime


class NotificationListOut(BaseModel):
    unread_count: int
    items:        list[NotificationOut]


def _out(n: Notification, society_name: str | None) -> NotificationOut:
    action, url = ACTIONS.get(n.type, (None, None))
    return NotificationOut(
        id=n.id, type=n.type, message=n.message, society_id=n.society_id, society_name=society_name,
        flat_id=n.flat_id, flat_bill_id=n.flat_bill_id, charger_id=n.charger_id,
        action=action if n.flat_id else None,
        action_url=url.format(flat_id=n.flat_id) if url and n.flat_id else None,
        is_read=n.is_read, actioned_at=n.actioned_at, created_at=n.created_at,
    )


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    unread_only: bool       = False,
    society_id:  int | None = None,
    limit:       int        = Query(50, ge=1, le=200),
    db:          AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    q = (select(Notification, Society.name).join(Society, Society.id == Notification.society_id)
         .order_by(Notification.created_at.desc()).limit(limit))
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    if society_id is not None:
        q = q.where(Notification.society_id == society_id)
    unread = await db.scalar(select(func.count(Notification.id)).where(Notification.is_read.is_(False)))
    return NotificationListOut(
        unread_count=unread or 0,
        items=[_out(n, name) for n, name in (await db.execute(q)).all()],
    )


@router.put("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    result = await db.execute(update(Notification).where(Notification.is_read.is_(False)).values(is_read=True))
    await db.commit()
    return {"marked_read": result.rowcount}


async def _get(db: AsyncSession, notification_id: int) -> Notification:
    n = await db.get(Notification, notification_id)
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    return n


@router.put("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    n = await _get(db, notification_id)
    n.is_read = True
    await db.commit()
    return _out(n, await db.scalar(select(Society.name).where(Society.id == n.society_id)))


@router.put("/{notification_id}/actioned", response_model=NotificationOut)
async def mark_actioned(notification_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    n = await _get(db, notification_id)
    n.is_read, n.actioned_at = True, n.actioned_at or datetime.now(timezone.utc)
    await db.commit()
    return _out(n, await db.scalar(select(Society.name).where(Society.id == n.society_id)))
