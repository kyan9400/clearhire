"""Anchoring the audit log, and checking it against the chain.

Every period (an hour by default) the entries logged since the last anchor are committed to the
AuditAnchor contract: their Merkle root, and the hash-chain head. Ranges are contiguous by entry id, so
anyone holding the log can rebuild each tree and compare it with the chain. A rewritten entry changes the
rebuilt root, and the chain still holds the original.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from clearhire import audit
from clearhire.anchoring.chain import ChainError, OnChainAnchor, Receipt
from clearhire.anchoring.merkle import Tree, build, leaf
from clearhire.db.models import Anchor, AuditEntry


class ChainLike(Protocol):
    contract: str | None

    async def chain_id(self) -> int: ...
    async def anchor(
        self, period: int, root: bytes, head: bytes, first_id: int, last_id: int, entries: int
    ) -> Receipt: ...
    async def anchor_of(self, period: int) -> OnChainAnchor | None: ...
    async def verify_entry(
        self, period: int, entry_id: int, entry_hash: bytes, proof: list[bytes]
    ) -> bool: ...


def period_of(moment: datetime, seconds: int) -> int:
    return int(moment.timestamp()) // seconds


def period_start(period: int, seconds: int) -> datetime:
    return datetime.fromtimestamp(period * seconds, UTC)


async def _rows(session: AsyncSession, first_id: int, last_id: int) -> list[tuple[int, bytes]]:
    return [(i, h) for i, h in (await session.execute(
        select(AuditEntry.id, AuditEntry.hash).where(AuditEntry.id.between(first_id, last_id)).order_by(AuditEntry.id)
    )).all()]  # fmt: skip


def _tree(rows: list[tuple[int, bytes]]) -> Tree:
    return build([leaf(i, h) for i, h in rows])


async def anchor_pending(session: AsyncSession, chain: ChainLike, period_seconds: int, *, now: datetime | None = None,
                         close_current: bool = False) -> Anchor | None:  # fmt: skip
    """Anchor everything logged since the last anchor, up to the end of the last finished period (or up to
    now, with `close_current`, for a first demo run). Nothing to do: None."""
    now = now or datetime.now(UTC)
    current = period_of(now, period_seconds)
    target = current if close_current else current - 1
    last = (await session.execute(select(Anchor).order_by(Anchor.period.desc()).limit(1))).scalar()
    if last is not None and last.period >= target:
        return None
    boundary = now if close_current else period_start(current, period_seconds)
    after = last.last_id if last else 0
    last_id = (await session.execute(
        select(func.max(AuditEntry.id)).where(AuditEntry.id > after, AuditEntry.at < boundary)
    )).scalar()  # fmt: skip
    if last_id is None:
        return None
    rows = await _rows(session, after + 1, last_id)
    tree = _tree(rows)
    first_id, head = rows[0][0], rows[-1][1]

    existing = await chain.anchor_of(target)
    if existing is not None:  # sent before, but the database write after it failed: record it, do not resend
        if existing.root != tree.root or existing.first_id != first_id or existing.last_id != last_id:
            raise ChainError(f"period {target} is anchored on chain with different contents")
        receipt = Receipt("", 0)
    else:
        receipt = await chain.anchor(target, tree.root, head, first_id, last_id, len(rows))
    row = Anchor(period=target, period_seconds=period_seconds, root=tree.root, head=head, first_id=first_id,
                 last_id=last_id, entries=len(rows), chain_id=await chain.chain_id(), contract=chain.contract or "",
                 tx_hash=receipt.tx_hash, block=receipt.block)  # fmt: skip
    session.add(row)
    await audit.record(session, "audit.anchored", "anchor", target, actor_type="system", at=now, data={
        "root": tree.root.hex(), "head": head.hex(), "first_id": first_id, "last_id": last_id, "entries": len(rows),
        "tx": receipt.tx_hash, "block": receipt.block,
    })  # fmt: skip
    await session.commit()
    return row


@dataclass
class Proof:
    entry_id: int
    anchored: bool
    period: int | None = None
    leaf: str | None = None
    proof: list[str] | None = None
    root: str | None = None
    tx_hash: str | None = None
    root_matches_log: bool | None = None  # the tree rebuilt from today's log has the recorded root
    root_matches_chain: bool | None = None  # the chain holds the recorded root (None: chain unreachable)
    verified_on_chain: bool | None = None  # the contract's verifyEntry accepts this entry and proof


async def prove(session: AsyncSession, chain: ChainLike | None, entry_id: int) -> Proof | None:
    entry = await session.get(AuditEntry, entry_id)
    if entry is None:
        return None
    anchor = (await session.execute(
        select(Anchor).where(Anchor.first_id <= entry_id, Anchor.last_id >= entry_id)
    )).scalar()  # fmt: skip
    if anchor is None:
        return Proof(entry_id, anchored=False)
    rows = await _rows(session, anchor.first_id, anchor.last_id)
    tree = _tree(rows)
    index = next(i for i, (row_id, _) in enumerate(rows) if row_id == entry_id)
    path = tree.proof(index)
    result = Proof(entry_id, True, anchor.period, "0x" + tree.levels[0][index].hex(), ["0x" + p.hex() for p in path],
                   "0x" + anchor.root.hex(), anchor.tx_hash, tree.root == anchor.root)  # fmt: skip
    if chain is not None:
        try:
            on_chain = await chain.anchor_of(anchor.period)
            result.root_matches_chain = on_chain is not None and on_chain.root == anchor.root
            result.verified_on_chain = await chain.verify_entry(anchor.period, entry_id, entry.hash, path)
        except ChainError:
            pass
    return result


@dataclass
class Check:
    anchors: int
    matching: int
    reachable: bool
    first_mismatch_period: int | None
    details: list[dict[str, Any]]


async def check_all(session: AsyncSession, chain: ChainLike, limit: int = 1000) -> Check:
    """Rebuild every anchored range from the log as it is now and compare it with the chain. A mismatch
    means the log was changed after that period was anchored."""
    anchors = (await session.execute(select(Anchor).order_by(Anchor.period).limit(limit))).scalars().all()
    details: list[dict[str, Any]] = []
    first_bad = None
    try:
        for anchor in anchors:
            rows = await _rows(session, anchor.first_id, anchor.last_id)
            rebuilt = _tree(rows).root if rows else b""
            on_chain = await chain.anchor_of(anchor.period)
            ok = (
                on_chain is not None
                and on_chain.root == rebuilt
                and on_chain.head == (rows[-1][1] if rows else b"")
            )
            details.append({"period": anchor.period, "entries": len(rows), "matches": ok})
            if not ok and first_bad is None:
                first_bad = anchor.period
    except ChainError:
        return Check(len(anchors), sum(d["matches"] for d in details), False, first_bad, details)
    return Check(len(anchors), sum(d["matches"] for d in details), True, first_bad, details)
