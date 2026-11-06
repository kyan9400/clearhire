"""Analytics, the audit log, the skill list and health."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select, text

from clearhire import analytics
from clearhire import audit as audit_log
from clearhire.api.deps import Recruiter, Session, Shared, Staff
from clearhire.api.schemas import AuditOut, AuditVerifyOut, HealthOut, OverviewOut, SkillOut
from clearhire.db.models import AuditEntry

router = APIRouter(tags=["insights"])


@router.get("/api/analytics/overview")
async def overview(session: Session, user: Staff) -> OverviewOut:
    return OverviewOut.model_validate(await analytics.overview(session))


@router.get("/api/audit")
async def audit_entries(session: Session, user: Recruiter, entity_id: str | None = None, action: str | None = None,
                        limit: int = Query(100, ge=1, le=1000)) -> list[AuditOut]:  # fmt: skip
    query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    if entity_id:
        query = query.where(AuditEntry.entity_id == entity_id)
    if action:
        query = query.where(AuditEntry.action == action)
    rows = (await session.execute(query)).scalars().all()
    return [AuditOut(id=r.id, at=r.at, actor_type=r.actor_type, actor_id=r.actor_id, action=r.action,
                     entity_type=r.entity_type, entity_id=r.entity_id, data=r.data, hash=r.hash.hex()) for r in rows]  # fmt: skip


@router.get("/api/audit/verify")
async def verify(session: Session, user: Recruiter) -> AuditVerifyOut:
    """Recompute the whole hash chain. `valid: false` names the first entry that was changed."""
    result = await audit_log.verify(session)
    return AuditVerifyOut(
        entries=result.entries, valid=result.valid, first_bad_id=result.first_bad_id, head=result.head
    )


@router.get("/api/skills")
async def skills(services: Shared, user: Staff, q: str = Query("", max_length=60)) -> list[SkillOut]:
    """The skill taxonomy, for the requirement editor's autocomplete."""
    needle = q.lower().strip()
    out = []
    for skill in services.matcher.taxonomy.skills.values():
        if not needle or needle in skill.name.lower() or any(needle in alias for alias in skill.aliases):
            out.append(SkillOut(id=skill.id, name=skill.name, category=skill.category))
    return sorted(out, key=lambda s: (not s.name.lower().startswith(needle), s.name.lower()))[:50]


@router.get("/api/health")
async def health(session: Session, services: Shared) -> HealthOut:
    database = True
    try:
        await session.execute(text("select 1"))
    except Exception:  # health must answer even when the database is down
        database = False
    return HealthOut(
        status="ok" if database else "degraded",
        database=database,
        embedding_model=services.matcher.embedder.name,
        ocr=bool(services.ocr and services.ocr.available),
        native_matcher=services.matcher.taxonomy.native,
        read_only=services.settings.demo_read_only,
    )
