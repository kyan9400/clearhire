"""Is the database migrated far enough for this code? Kubernetes keeps pods out of service until it is.

Migrations are written to be backward compatible (add first, remove a release later), so a database at a
revision this code does not know, that is a newer release's, counts as current: a rollback still starts.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@cache
def _script() -> ScriptDirectory:
    return ScriptDirectory(str(MIGRATIONS))


def heads() -> frozenset[str]:
    return frozenset(_script().get_heads())


def known() -> frozenset[str]:
    return frozenset(revision.revision for revision in _script().walk_revisions())


async def applied(session: AsyncSession) -> frozenset[str]:
    try:
        rows = await session.execute(text("SELECT version_num FROM alembic_version"))
    except ProgrammingError:  # no alembic_version table: never migrated
        await session.rollback()
        return frozenset()
    return frozenset(row[0] for row in rows)


def is_current(done: frozenset[str]) -> bool:
    if done - known():  # a newer release has migrated already
        return True
    return heads() <= done
