"""Alembic migrations, run against CLEARHIRE_DATABASE_URL."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from clearhire.config import get_settings
from clearhire.db.models import Base

target_metadata = Base.metadata


def run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(main())
