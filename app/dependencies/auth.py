"""
app/dependencies/auth.py
------------------------
JWT token creation and validation.
FastAPI dependencies for protecting routes by role.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models.user import User

# ------------------------------------------------------------------ #
#  Password hashing
# ------------------------------------------------------------------ #

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ------------------------------------------------------------------ #
#  JWT
# ------------------------------------------------------------------ #

bearer_scheme = HTTPBearer()


def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    return user


# ------------------------------------------------------------------ #
#  Role-based dependencies
# ------------------------------------------------------------------ #

async def get_current_user(
    user: User = Depends(_get_current_user),
) -> User:
    """Any authenticated user."""
    return user


async def require_super_admin(
    user: User = Depends(_get_current_user),
) -> User:
    """Only super admins."""
    if user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user


async def require_society_admin(
    user: User = Depends(_get_current_user),
) -> User:
    """Only society admins."""
    if user.role != "society_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Society admin access required",
        )
    return user


async def require_any_admin(
    user: User = Depends(_get_current_user),
) -> User:
    """Either role is allowed."""
    if user.role not in ("super_admin", "society_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
