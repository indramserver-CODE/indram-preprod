"""
app/routers/admin_users.py
--------------------------
Super admin only. Nested under societies.

GET    /api/societies/{society_id}/admins              — list admins of a society
POST   /api/societies/{society_id}/admins              — create admin for this society
PUT    /api/societies/{society_id}/admins/{user_id}    — update admin (name/email/password/active)
DELETE /api/societies/{society_id}/admins/{user_id}    — remove admin from society (keeps account)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.user import User, SocietyAdmin
from app.models.society import Society
from app.schemas.user import UserOut
from app.dependencies.auth import require_super_admin, hash_password

router = APIRouter()


class AdminCreate(BaseModel):
    email:     EmailStr
    password:  str
    full_name: str | None = None


class AdminUpdate(BaseModel):
    full_name: str | None = None
    email:     EmailStr | None = None   # also their login
    password:  str | None = None
    is_active: bool | None = None


async def _get_society_or_404(society_id: int, db: AsyncSession) -> Society:
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


@router.get("/{society_id}", response_model=list[UserOut])
async def list_society_admins(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    await _get_society_or_404(society_id, db)
    result = await db.execute(
        select(User)
        .join(SocietyAdmin, SocietyAdmin.user_id == User.id)
        .where(SocietyAdmin.society_id == society_id)
        .order_by(User.email)
    )
    return result.scalars().all()


@router.post("/{society_id}", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_society_admin(
    society_id: int,
    body: AdminCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    await _get_society_or_404(society_id, db)

    # Check email is not already taken
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role="society_admin",
    )
    db.add(user)
    await db.flush()  # get user.id

    db.add(SocietyAdmin(user_id=user.id, society_id=society_id))
    await db.flush()
    await db.refresh(user)
    return user


@router.put("/{society_id}/{user_id}", response_model=UserOut)
async def update_society_admin(
    society_id: int,
    user_id: int,
    body: AdminUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    await _get_society_or_404(society_id, db)

    # Confirm this user is actually an admin of this society
    result = await db.execute(
        select(User)
        .join(SocietyAdmin, SocietyAdmin.user_id == User.id)
        .where(User.id == user_id, SocietyAdmin.society_id == society_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Admin not found in this society")

    if body.email is not None and body.email.lower() != user.email.lower():
        taken = await db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower(), User.id != user.id))
        if taken:
            raise HTTPException(status_code=409, detail="Another account already uses this email")
        user.email = body.email
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.hashed_password = hash_password(body.password)

    await db.flush()
    await db.refresh(user)
    return user


@router.delete("/{society_id}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_society_admin(
    society_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    await _get_society_or_404(society_id, db)

    result = await db.execute(
        select(SocietyAdmin).where(
            SocietyAdmin.user_id == user_id,
            SocietyAdmin.society_id == society_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Admin not found in this society")

    # Remove the society assignment only — user account stays intact
    await db.delete(assignment)