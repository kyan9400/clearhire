"""The append-only audit log: who (or which model) decided what, chained by SHA-256.

Recruiters, candidates and auditors can rely on it because rewriting history is detectable: each entry's
hash covers the previous entry's hash, and the daily Merkle roots of the log are anchored in a smart
contract (contracts/AuditAnchor.sol), which no one can edit afterwards.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from clearhire.db.models import AuditEntry

GENESIS = bytes(32)
_LOCK_KEY = 0x434C454152  # pg_advisory_xact_lock key: serialises appends ("CLEAR")


def canonical(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def entry_hash(prev_hash: bytes, entry: dict[str, Any]) -> bytes:
    return hashlib.sha256(prev_hash + canonical(entry)).digest()


def _fields(row: AuditEntry) -> dict[str, Any]:
    return {
        "at": row.at.astimezone(UTC).isoformat(timespec="microseconds"),
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "data": row.data,
    }


async def record(
    session: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: object,
    *,
    actor_type: str = "user",
    actor_id: object | None = None,
    data: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> AuditEntry:
    """Append an entry in the caller's transaction. Commit to make it permanent."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
    previous = (
        await session.execute(select(AuditEntry.hash).order_by(AuditEntry.id.desc()).limit(1))
    ).scalar()
    row = AuditEntry(
        at=at or datetime.now(UTC),
        actor_type=actor_type,
        actor_id=str(actor_id) if actor_id is not None else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        data=data or {},
        prev_hash=previous or GENESIS,
        hash=b"",
    )
    row.hash = entry_hash(row.prev_hash, _fields(row))
    session.add(row)
    await session.flush()
    return row


@dataclass
class Verification:
    entries: int
    valid: bool
    first_bad_id: int | None = None
    head: str = ""


async def verify(session: AsyncSession, batch: int = 5000) -> Verification:
    """Recompute every hash from the start; the first mismatch is where the log was changed."""
    previous = GENESIS
    count = 0
    last_id = 0
    while True:
        rows = (await session.execute(
            select(AuditEntry).where(AuditEntry.id > last_id).order_by(AuditEntry.id).limit(batch)
        )).scalars().all()  # fmt: skip
        if not rows:
            break
        for row in rows:
            if row.prev_hash != previous or row.hash != entry_hash(previous, _fields(row)):
                return Verification(count, False, row.id, previous.hex())
            previous = row.hash
            count += 1
            last_id = row.id
    return Verification(count, True, None, previous.hex())
