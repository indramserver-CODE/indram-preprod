"""
app/routers/flats.py
--------------------
Super admin only:
  GET    /api/societies/{society_id}/flats        — list flats
  POST   /api/societies/{society_id}/flats/csv   — bulk upload via CSV
  DELETE /api/societies/{society_id}/flats/{id}  — delete flat

Society admin:
  GET    /api/sa/flats                            — list own society's flats (with charger + meter)
  PATCH  /api/sa/flats/{flat_id}                  — update owner_name / email

CSV format (headers required):
  flat_number, owner_name, email
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.flat import Flat
from app.models.charger import Charger
from app.models.meter import Meter
from app.models.society import Society
from app.schemas.flat import FlatOut
from app.models.user import SocietyAdmin, User
from app.dependencies.auth import require_super_admin, require_society_admin

router = APIRouter()

REQUIRED_COLUMNS = {"flat_number"}


async def _get_society_or_404(society_id: int, db: AsyncSession) -> Society:
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


# ── Super admin endpoints ─────────────────────────────────────────────────────

@router.get("/{society_id}/flats", response_model=list[FlatOut])
async def list_flats(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    await _get_society_or_404(society_id, db)
    result = await db.execute(
        select(
            Flat.id,
            Flat.society_id,
            Flat.flat_number,
            Flat.owner_name,
            Flat.email,
            Flat.created_at,
            Charger.charger_id,
            Charger.meter_id,
            Meter.label.label("meter_label"),
            Charger.status.label("charger_status"),
            Charger.fault_code,
            Charger.lock_reasons,
            Charger.last_seen_at,
        )
        .outerjoin(Charger, Charger.flat_id == Flat.id)
        .outerjoin(Meter, Meter.id == Charger.meter_id)
        .where(Flat.society_id == society_id)
        .order_by(Flat.flat_number)
    )
    return [
        FlatOut(
            id=r.id,
            society_id=r.society_id,
            flat_number=r.flat_number,
            owner_name=r.owner_name,
            email=r.email,
            charger_id=r.charger_id,
            meter_id=r.meter_id,
            meter_label=r.meter_label,
            charger_status=r.charger_status,
            fault_code=r.fault_code,
            lock_reasons=r.lock_reasons or [],
            last_seen_at=r.last_seen_at,
            created_at=r.created_at,
        )
        for r in result.all()
    ]


@router.post("/{society_id}/flats/csv", status_code=status.HTTP_200_OK)
async def upload_flats_csv(
    society_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    await _get_society_or_404(society_id, db)

    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))

    if not REQUIRED_COLUMNS.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain columns: {REQUIRED_COLUMNS}",
        )

    existing = await db.execute(
        select(Flat.flat_number).where(Flat.society_id == society_id)
    )
    existing_numbers = {r for r in existing.scalars().all()}

    imported, skipped = [], []

    for i, row in enumerate(reader, start=2):
        flat_number = (row.get("flat_number") or "").strip()

        if not flat_number:
            skipped.append({"row": i, "reason": "flat_number is required"})
            continue

        if flat_number in existing_numbers:
            skipped.append({"row": i, "flat_number": flat_number, "reason": "duplicate"})
            continue

        flat = Flat(
            society_id=society_id,
            flat_number=flat_number,
            owner_name=(row.get("owner_name") or "").strip() or None,
            email=(row.get("email") or "").strip() or None,
        )
        db.add(flat)
        existing_numbers.add(flat_number)
        imported.append(flat_number)

    await db.flush()

    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "skipped_details": skipped,
    }


@router.delete("/{society_id}/flats/{flat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flat(
    society_id: int,
    flat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    result = await db.execute(
        select(Flat).where(Flat.id == flat_id, Flat.society_id == society_id)
    )
    flat = result.scalar_one_or_none()
    if not flat:
        raise HTTPException(status_code=404, detail="Flat not found")
    await db.delete(flat)


# ── Society admin endpoints ───────────────────────────────────────────────────

@router.get("/flats", response_model=list[FlatOut])
async def list_my_society_flats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    """
    List all flats in the admin's society.
    Joins Charger and Meter so each flat shows which charger and meter it belongs to.
    """
    sa_result = await db.execute(
        select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == current_user.id)
    )
    society_id = sa_result.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned to this admin")

    result = await db.execute(
        select(
            Flat.id,
            Flat.society_id,
            Flat.flat_number,
            Flat.owner_name,
            Flat.email,
            Flat.created_at,
            Charger.charger_id,
            Charger.meter_id,
            Meter.label.label("meter_label"),
            Charger.status.label("charger_status"),
            Charger.fault_code,
            Charger.lock_reasons,
            Charger.last_seen_at,
        )
        .outerjoin(Charger, Charger.flat_id == Flat.id)
        .outerjoin(Meter, Meter.id == Charger.meter_id)
        .where(Flat.society_id == society_id)
        .order_by(Flat.flat_number)
    )
    rows = result.all()
    return [
        FlatOut(
            id=r.id,
            society_id=r.society_id,
            flat_number=r.flat_number,
            owner_name=r.owner_name,
            email=r.email,
            charger_id=r.charger_id,
            meter_id=r.meter_id,
            meter_label=r.meter_label,
            charger_status=r.charger_status,
            fault_code=r.fault_code,
            lock_reasons=r.lock_reasons or [],
            last_seen_at=r.last_seen_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


class FlatAdminUpdate(BaseModel):
    owner_name: str | None = None
    email: str | None = None


@router.patch("/flats/{flat_id}", response_model=FlatOut)
async def update_my_society_flat(
    flat_id: int,
    body: FlatAdminUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    sa_result = await db.execute(
        select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == current_user.id)
    )
    society_id = sa_result.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned to this admin")

    result = await db.execute(
        select(Flat).where(Flat.id == flat_id, Flat.society_id == society_id)
    )
    flat = result.scalar_one_or_none()
    if not flat:
        raise HTTPException(status_code=404, detail="Flat not found")

    if body.owner_name is not None:
        flat.owner_name = body.owner_name
    if body.email is not None:
        flat.email = body.email

    await db.flush()
    await db.refresh(flat)
    return flat