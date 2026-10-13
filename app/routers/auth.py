"""
app/routers/auth.py
-------------------
POST /api/auth/login              — both roles
POST /api/auth/logout             — client-side token drop (stateless)
GET  /api/auth/me                 — return current user info
POST /api/auth/forgot-password    — request a password reset email
POST /api/auth/reset-password     — consume a reset token, set new password
"""

import hashlib
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User, SocietyAdmin
from app.models.password_reset import PasswordResetToken
from app.schemas.user import LoginIn, TokenOut, UserOut, ForgotPasswordIn, ResetPasswordIn
from app.config import settings
from app.services.email_service import send_password_reset_email
from app.dependencies.auth import (
    verify_password,
    hash_password,
    create_access_token,
    get_current_user,
)

router = APIRouter()


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    # Fetch user by email
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # For society admins, include their society IDs in the token
    society_ids: list[int] = []
    if user.role == "society_admin":
        sa_result = await db.execute(
            select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id)
        )
        society_ids = list(sa_result.scalars().all())

    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "society_ids": society_ids,
    })

    return TokenOut(
        access_token=token,
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/logout")
async def logout():
    """
    JWT is stateless — logout is handled client-side by discarding the token.
    This endpoint exists so the frontend has a clean logout call to make.
    """
    return {"detail": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


# ------------------------------------------------------------------ #
#  Forgot / reset password
# ------------------------------------------------------------------ #

# Simple in-memory rate limit: max 3 requests per email per hour.
# Fine at this app's scale — swap for a Redis-backed limiter if the
# admin portal ever sits behind heavier traffic.
_reset_request_log: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_MAX = 3
_RATE_LIMIT_WINDOW_SECONDS = 60 * 60


def _is_rate_limited(email: str) -> bool:
    now = time.time()
    recent = [t for t in _reset_request_log[email] if now - t < _RATE_LIMIT_WINDOW_SECONDS]
    _reset_request_log[email] = recent
    if len(recent) >= _RATE_LIMIT_MAX:
        return True
    recent.append(now)
    return False


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Always returns the same generic response, whether or not the email
    belongs to an account — this endpoint must not be usable to discover
    which emails are registered admins.
    """
    generic_response = {
        "detail": "If that email is registered, a password reset link has been sent."
    }

    if _is_rate_limited(body.email):
        # Still return the generic response — don't reveal rate limiting
        # state either.
        return generic_response

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return generic_response

    # Invalidate any previous unused tokens for this user.
    existing = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    for old_token in existing.scalars().all():
        old_token.used_at = now

    raw_token = secrets.token_urlsafe(32)
    reset_row = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
    )
    db.add(reset_row)
    await db.flush()

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    background_tasks.add_task(
        send_password_reset_email,
        user.email,
        user.full_name,
        reset_url,
        settings.PASSWORD_RESET_EXPIRE_MINUTES,
    )

    return generic_response


@router.post("/reset-password")
async def reset_password(body: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    token_hash = _hash_token(body.token)

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    reset_row = result.scalar_one_or_none()

    invalid_exception = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This reset link is invalid or has expired. Please request a new one.",
    )

    if reset_row is None or reset_row.used_at is not None:
        raise invalid_exception

    now = datetime.now(timezone.utc)
    expires_at = reset_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise invalid_exception

    user_result = await db.execute(select(User).where(User.id == reset_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise invalid_exception

    user.hashed_password = hash_password(body.new_password)
    reset_row.used_at = now

    return {"detail": "Password has been reset successfully. You can now log in."}