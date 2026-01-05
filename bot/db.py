from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .models import Base


def to_async_database_url(url: str) -> str:
    """Convert sync postgres URL to asyncpg URL."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_engine_and_sessionmaker(database_url: str) -> tuple[AsyncEngine, sessionmaker]:
    async_url = to_async_database_url(database_url)
    engine = create_async_engine(async_url, pool_pre_ping=True)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
