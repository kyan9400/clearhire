"""The audit log's anchors on the chain: list them, prove one entry, re-check the whole log."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from clearhire.anchoring.service import check_all, period_start, prove
from clearhire.api.deps import Recruiter, Session, Shared
from clearhire.api.schemas import AnchorCheckOut, AnchorOut, AnchorsOut, ProofOut
from clearhire.db.models import Anchor, AuditEntry

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/anchors")
async def anchors(
    session: Session, services: Shared, user: Recruiter, limit: int = Query(50, ge=1, le=500)
) -> AnchorsOut:
    settings = services.settings
    rows = (await session.execute(select(Anchor).order_by(Anchor.period.desc()).limit(limit))).scalars().all()
    last_id = rows[0].last_id if rows else 0
    unanchored = (await session.execute(select(func.count()).where(AuditEntry.id > last_id))).scalar_one()
    return AnchorsOut(
        enabled=services.chain is not None and bool(settings.anchor_contract), chain_name=settings.chain_name,
        chain_id=rows[0].chain_id if rows else None, contract=settings.anchor_contract,
        explorer_tx_url=settings.chain_explorer_tx_url, period_seconds=settings.anchor_period_seconds,
        unanchored=unanchored,
        items=[AnchorOut(period=a.period, starts_at=period_start(a.period, a.period_seconds), root="0x" + a.root.hex(),
                         head="0x" + a.head.hex(), first_id=a.first_id, last_id=a.last_id, entries=a.entries,
                         tx_hash=a.tx_hash, block=a.block, created_at=a.created_at) for a in rows],
    )  # fmt: skip


@router.get("/anchors/check")
async def check(session: Session, services: Shared, user: Recruiter) -> AnchorCheckOut:
    """Rebuild every anchored range from the log as it is now and compare it with the chain."""
    if services.chain is None or not services.chain.contract:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "anchoring is not configured")
    result = await check_all(session, services.chain)
    return AnchorCheckOut(anchors=result.anchors, matching=result.matching, reachable=result.reachable,
                          first_mismatch_period=result.first_mismatch_period)  # fmt: skip


@router.get("/{entry_id}/proof")
async def proof(entry_id: int, session: Session, services: Shared, user: Recruiter) -> ProofOut:
    """The Merkle proof that this entry is in an anchored period, checked by the contract itself."""
    chain = services.chain if services.chain is not None and services.chain.contract else None
    result = await prove(session, chain, entry_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such audit entry")
    return ProofOut(**asdict(result))
