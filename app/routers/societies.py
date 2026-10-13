""""
app/routers/societies.py
------------------------
Super admin only.

GET    /api/societies              — list all societies
POST   /api/societies              — create society
GET    /api/societies/{id}         — get society
PUT    /api/societies/{id}         — update society
DELETE /api/societies/{id}         — delete society
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.society import Society
from app.schemas.society import SocietyCreate, SocietyUpdate, SocietyOut
from app.dependencies.auth import require_super_admin

router = APIRouter()


@router.get("", response_model=list[SocietyOut])
async def list_societies(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    result = await db.execute(select(Society).order_by(Society.name))
    return result.scalars().all()


@router.post("", response_model=SocietyOut, status_code=status.HTTP_201_CREATED)
async def create_society(
    body: SocietyCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    society = Society(**body.model_dump())
    db.add(society)
    await db.flush()
    await db.refresh(society)
    return society


@router.get("/{society_id}", response_model=SocietyOut)
async def get_society(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


@router.put("/{society_id}", response_model=SocietyOut)
async def update_society(
    society_id: int,
    body: SocietyUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(society, field, value)
    await db.flush()
    await db.refresh(society)
    return society


@router.delete("/{society_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_society(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    await db.delete(society)
