"""Async engine and sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from clearhire.config import get_settings


@cache
def engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)


@cache
def sessions() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessions()() as session:
        yield session
