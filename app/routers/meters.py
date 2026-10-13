"""
app/routers/meters.py
---------------------
Meter management endpoints.

Super admin — full CRUD:
  GET    /api/meters/{society_id}       — list all meters for a society
  POST   /api/meters/{society_id}       — create a meter under a society
  PUT    /api/meters/{meter_id}         — update a meter
  DELETE /api/meters/{meter_id}         — delete a meter (cascades to chargers + bills)

Society admin — view only:
  GET    /api/sa/meters                 — list meters for their own society (with charger count)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.meter import Meter
from app.models.charger import Charger
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.schemas.meter import MeterCreate, MeterUpdate, MeterOut, MeterSummaryOut
from app.dependencies.auth import require_super_admin, require_society_admin

# Two separate routers — registered at different prefixes in main.py
super_router   = APIRouter()
society_router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_society_or_404(society_id: int, db: AsyncSession) -> Society:
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


async def _get_meter_or_404(meter_id: int, db: AsyncSession) -> Meter:
    meter = await db.get(Meter, meter_id)
    if not meter:
        raise HTTPException(status_code=404, detail="Meter not found")
    return meter


async def _get_society_id_for_admin(user: User, db: AsyncSession) -> int:
    result = await db.execute(
        select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id)
    )
    society_id = result.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned to this admin")
    return society_id


# ── Super admin endpoints ─────────────────────────────────────────────────────

@super_router.get("/{society_id}", response_model=list[MeterOut])
async def list_meters(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """List all meters for a society."""
    await _get_society_or_404(society_id, db)
    result = await db.execute(
        select(Meter)
        .where(Meter.society_id == society_id)
        .order_by(Meter.meter_number)
    )
    return result.scalars().all()


@super_router.post("/{society_id}", response_model=MeterOut, status_code=status.HTTP_201_CREATED)
async def create_meter(
    society_id: int,
    body: MeterCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Create a new meter under a society."""
    await _get_society_or_404(society_id, db)

    # Enforce unique meter_number within this society
    existing = await db.execute(
        select(Meter).where(
            Meter.society_id == society_id,
            Meter.meter_number == body.meter_number,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Meter number '{body.meter_number}' already exists in this society",
        )

    meter = Meter(
        society_id=society_id,
        meter_number=body.meter_number,
        label=body.label,
        sanctioned_load=body.sanctioned_load,
        location=body.location,
    )
    db.add(meter)
    await db.flush()
    await db.refresh(meter)
    await db.commit()
    return meter


@super_router.put("/{meter_id}", response_model=MeterOut)
async def update_meter(
    meter_id: int,
    body: MeterUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Update a meter's details."""
    meter = await _get_meter_or_404(meter_id, db)

    # If meter_number is changing, check uniqueness within the same society
    if body.meter_number is not None and body.meter_number != meter.meter_number:
        conflict = await db.execute(
            select(Meter).where(
                Meter.society_id == meter.society_id,
                Meter.meter_number == body.meter_number,
                Meter.id != meter_id,
            )
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Meter number '{body.meter_number}' already exists in this society",
            )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(meter, field, value)

    await db.flush()
    await db.refresh(meter)
    await db.commit()
    return meter


@super_router.delete("/{meter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meter(
    meter_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    Delete a meter. Cascades to all chargers and monthly bills belonging to it.
    Use with caution — this is irreversible.
    """
    meter = await _get_meter_or_404(meter_id, db)
    await db.delete(meter)
    await db.commit()


# ── Society admin endpoints ───────────────────────────────────────────────────

@society_router.get("", response_model=list[MeterSummaryOut])
async def list_meters_for_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    """
    List all meters for the society admin's own society.
    Includes charger count per meter. Read-only — no create/edit/delete.
    """
    society_id = await _get_society_id_for_admin(current_user, db)

    # Fetch meters with charger counts in a single query
    result = await db.execute(
        select(
            Meter,
            func.count(Charger.id).label("charger_count"),
        )
        .outerjoin(Charger, Charger.meter_id == Meter.id)
        .where(Meter.society_id == society_id)
        .group_by(Meter.id)
        .order_by(Meter.meter_number)
    )
    rows = result.all()

    return [
        MeterSummaryOut(
            id=meter.id,
            meter_number=meter.meter_number,
            label=meter.label,
            sanctioned_load=meter.sanctioned_load,
            location=meter.location,
            charger_count=charger_count,
        )
        for meter, charger_count in rows
    ]