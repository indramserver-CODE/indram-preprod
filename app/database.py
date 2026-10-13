"""
app/database.py
---------------
SQLAlchemy async engine and session setup.
Uses asyncpg as the driver under the hood.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

import ssl

ssl_context = ssl.create_default_context()

# Convert standard postgres:// DSN to postgresql+asyncpg://
DATABASE_URL = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace(
    "postgres://", "postgresql+asyncpg://"
)

# ✅ FIXED ENGINE CONFIG
engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    echo=False,

    # ⭐ CRITICAL FIX (prevents "connection is closed" error)
    pool_pre_ping=True,

    # Optional but recommended (recycles stale connections)
    pool_recycle=1800,

    # Optional: prevents hanging forever
    pool_timeout=30,

    connect_args={"ssl": ssl_context},
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # ✅ Explicit close (extra safety)
            await session.close()