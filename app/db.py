"""
app/db.py
---------
Creates and exposes the raw asyncpg connection pool.
Used by the MQTT subscriber for high-throughput session writes.

DATABASE_URL may have a SQLAlchemy driver prefix (postgresql+asyncpg://)
which asyncpg does not understand. Strip it before connecting.
"""

import asyncpg
from app.config import settings

_pool: asyncpg.Pool | None = None


def _get_asyncpg_dsn() -> str:
    """
    Convert SQLAlchemy-style URL to plain asyncpg URL.
    postgresql+asyncpg://... → postgresql://...
    asyncpg will reject the +asyncpg driver prefix.
    """
    dsn = settings.DATABASE_URL
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif dsn.startswith("postgres+asyncpg://"):
        dsn = dsn.replace("postgres+asyncpg://", "postgresql://", 1)
    return dsn


# Errors that mean "the database is briefly unreachable" — worth retrying, not a bug.
TRANSIENT_DB_ERRORS = (
    TimeoutError,                                   # pool acquire / connect timed out
    OSError,                                        # network down, connection refused / reset
    asyncpg.exceptions.PostgresConnectionError,     # connection closed mid-operation, cannot connect now
    asyncpg.exceptions.InterfaceError,              # connection lost mid-query
    asyncpg.exceptions.TooManyConnectionsError,
)


async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=_get_asyncpg_dsn(),
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool