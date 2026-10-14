"""
app/routers/bulk_delete.py
--------------------------
Super admin only. "Delete all" for one society, per page.

GET    /api/societies/{society_id}/delete-all/{scope}   — what would be deleted, and what blocks it
DELETE /api/societies/{society_id}/delete-all/{scope}   — body {"confirm_name": "<society name>"}

scope:
  flats     flats + their chargers, RFID cards and pending commands.
            Blocked while the society has charging sessions or any bills (they would be lost).
  chargers  all chargers on the society's meters (flats and cards stay).
            Blocked while any of them has charging sessions.
  rfid      all RFID card records of the society's flats — database only: cards already
            on a charger keep working there until removed on the charger.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_super_admin
from app.models.bill import FlatBill
from app.models.charger import Charger
from app.models.command_log import PendingCommand
from app.models.flat import Flat
from app.models.meter import Meter
from app.models.rfid import RFIDCard
from app.models.session import ChargingSession
from app.models.society import Society

logger = logging.getLogger(__name__)
router = APIRouter()

Scope = Literal["flats", "chargers", "rfid"]


class DeleteAllPreview(BaseModel):
    society_id:   int
    society_name: str
    scope:        str
    counts:       dict[str, int]     # what will be deleted
    blocked:      str | None         # why it can't be done, or None
    warning:      str | None         # consequence to show before confirming


class DeleteAllConfirm(BaseModel):
    confirm_name: str


async def _society(db: AsyncSession, society_id: int) -> Society:
    society = await db.get(Society, society_id)
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


def _society_chargers(society_id: int):
    return select(Charger.charger_id).join(Meter, Meter.id == Charger.meter_id).where(Meter.society_id == society_id)


def _society_flats(society_id: int):
    return select(Flat.id).where(Flat.society_id == society_id)


async def _count(db: AsyncSession, q) -> int:
    return await db.scalar(select(func.count()).select_from(q.subquery())) or 0


async def _preview(db: AsyncSession, society: Society, scope: str) -> DeleteAllPreview:
    sid = society.id
    flats    = await _count(db, _society_flats(sid))
    chargers = await _count(db, _society_chargers(sid))
    cards    = await _count(db, select(RFIDCard.id).where(RFIDCard.flat_id.in_(_society_flats(sid))))
    sessions = await _count(db, select(ChargingSession.id).where(ChargingSession.charger_id.in_(_society_chargers(sid))))
    bills    = await _count(db, select(FlatBill.id).where(FlatBill.flat_id.in_(_society_flats(sid))))

    blocked = warning = None
    if scope == "flats":
        counts = {"flats": flats, "chargers": chargers, "rfid_cards": cards}
        reasons = []
        if sessions:
            reasons.append(f"{sessions} charging session{'s' if sessions != 1 else ''}")
        if bills:
            reasons.append(f"{bills} flat bill{'s' if bills != 1 else ''}")
        if reasons:
            blocked = (f"{society.name} has {' and '.join(reasons)}. Flats with charging or billing history "
                       "can't be deleted — that history would be lost.")
    elif scope == "chargers":
        counts = {"chargers": chargers}
        if sessions:
            blocked = (f"These chargers have {sessions} charging session{'s' if sessions != 1 else ''}. "
                       "Chargers with charging history can't be deleted.")
        warning = "Flats and their RFID cards stay; the flats will have no charger until new ones are added."
    else:
        counts = {"rfid_cards": cards}
        warning = ("Cards are removed from the database only. Cards already on a charger keep working there "
                   "until they are removed on the charger itself.")

    if not blocked and not any(counts.values()):
        blocked = f"Nothing to delete — {society.name} has no {scope.replace('rfid', 'RFID cards')}."
    return DeleteAllPreview(society_id=sid, society_name=society.name, scope=scope,
                            counts=counts, blocked=blocked, warning=warning)


@router.get("/{society_id}/delete-all/{scope}", response_model=DeleteAllPreview)
async def delete_all_preview(society_id: int, scope: Scope, db: AsyncSession = Depends(get_db),
                             _=Depends(require_super_admin)):
    return await _preview(db, await _society(db, society_id), scope)


@router.delete("/{society_id}/delete-all/{scope}", response_model=DeleteAllPreview)
async def delete_all(society_id: int, scope: Scope, body: DeleteAllConfirm, db: AsyncSession = Depends(get_db),
                     _=Depends(require_super_admin)):
    society = await _society(db, society_id)
    if body.confirm_name.strip().casefold() != society.name.strip().casefold():
        raise HTTPException(status_code=400, detail="The society name doesn't match — nothing was deleted.")

    preview = await _preview(db, society, scope)   # checked again here, not trusted from the client
    if preview.blocked:
        raise HTTPException(status_code=409, detail=preview.blocked)

    if scope == "flats":
        # chargers, RFID cards and pending commands go with their flat (ON DELETE CASCADE)
        charger_ids = (await db.execute(_society_chargers(society_id))).scalars().all()
        if charger_ids:
            await db.execute(delete(PendingCommand).where(PendingCommand.charger_id.in_(charger_ids)))
        await db.execute(delete(Flat).where(Flat.society_id == society_id))
    elif scope == "chargers":
        charger_ids = (await db.execute(_society_chargers(society_id))).scalars().all()
        await db.execute(delete(PendingCommand).where(PendingCommand.charger_id.in_(charger_ids)))
        await db.execute(delete(Charger).where(Charger.charger_id.in_(charger_ids)))
    else:
        await db.execute(delete(RFIDCard).where(RFIDCard.flat_id.in_(_society_flats(society_id))))

    await db.commit()
    logger.warning("DELETE ALL %s | society=%s (%s) | %s", scope, society_id, society.name, preview.counts)
    return preview
