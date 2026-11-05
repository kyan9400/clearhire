from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete, select, text

from clearhire import audit
from clearhire.api.deps import Recruiter, Session, Shared, Staff, Writable, pseudonym, sees_personal_data
from clearhire.api.schemas import ApplicationOut, CandidateOut, SearchHit
from clearhire.db.models import Application, Candidate, Document, Profile, Source, Stage, StageEvent, Vacancy
from clearhire.security import status_token
from clearhire.services.pipeline import UploadRejected, add_candidate
from clearhire.tasks import enqueue_parse

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
RRF_K = 60

# Search queries. Every one filters by experience and, when :skills is not empty, by skills.
KEYWORD_SQL = text("""
    with query as (select websearch_to_tsquery('russian', :q) || websearch_to_tsquery('english', :q) as q)
    select c.candidate_id, c.text, ts_rank(c.search, query.q) as rank
    from chunks c join profiles p on p.candidate_id = c.candidate_id, query
    where c.search @@ query.q and p.total_months >= :min_months
      and (cardinality(CAST(:skills AS varchar[])) = 0 or p.skills @> CAST(:skills AS varchar[]))
    order by rank desc limit :limit""")
SEMANTIC_SQL = text("""
    select c.candidate_id, c.text, 1 - (c.embedding <=> CAST(:v AS vector)) as rank
    from chunks c join profiles p on p.candidate_id = c.candidate_id
    where p.total_months >= :min_months
      and (cardinality(CAST(:skills AS varchar[])) = 0 or p.skills @> CAST(:skills AS varchar[]))
    order by c.embedding <=> CAST(:v AS vector) limit :limit""")
SKILL_SQL = text("""
    select p.candidate_id,
           cardinality(array(select unnest(p.skills) intersect select unnest(CAST(:qs AS varchar[])))) as hits
    from profiles p
    where p.skills && CAST(:qs AS varchar[]) and p.total_months >= :min_months
      and (cardinality(CAST(:skills AS varchar[])) = 0 or p.skills @> CAST(:skills AS varchar[]))
    order by hits desc, p.total_months desc limit :limit""")
BROWSE_SQL = text("""
    select p.candidate_id from profiles p
    where p.total_months >= :min_months
      and (cardinality(CAST(:skills AS varchar[])) = 0 or p.skills @> CAST(:skills AS varchar[]))
    order by p.total_months desc limit :limit""")


async def _candidate(session: Session, candidate_id: uuid.UUID) -> Candidate:
    candidate = await session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    return candidate


@router.post("", status_code=202, dependencies=[Writable])
async def upload(
    session: Session,
    services: Shared,
    user: Recruiter,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form(description="the candidate agreed to processing of their personal data")],
    vacancy_id: Annotated[uuid.UUID | None, Form()] = None,
) -> CandidateOut:
    """Add a candidate from their CV. Reading the CV happens in the background; the profile appears
    when it is done (GET /api/candidates/{id})."""
    data = await file.read(services.settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        candidate, document = await add_candidate(session, services, data, file.filename or "cv", source=Source.UPLOAD,
                                                  consent=consent, actor=("user", user.id))  # fmt: skip
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if vacancy_id is not None:
        if await session.get(Vacancy, vacancy_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vacancy not found")
        application = Application(candidate_id=candidate.id, vacancy_id=vacancy_id, source=Source.UPLOAD,
                                  status_token=status_token())  # fmt: skip
        session.add(application)
        await session.flush()
        session.add(StageEvent(application_id=application.id, stage=Stage.NEW, by_user=user.id))
    await session.commit()
    await enqueue_parse(document.id, background)
    return await _view(session, candidate, show=True)


async def _view(session: Session, candidate: Candidate, *, show: bool) -> CandidateOut:
    profile = await session.get(Profile, candidate.id)
    document = (await session.execute(
        select(Document).where(Document.candidate_id == candidate.id).order_by(Document.created_at.desc()).limit(1)
    )).scalar()  # fmt: skip
    applications = (
        (await session.execute(select(Application).where(Application.candidate_id == candidate.id)))
        .scalars()
        .all()
    )
    languages = {code: value[0] for code, value in (profile.data["languages"].items() if profile else [])}
    return CandidateOut(
        id=candidate.id, name=candidate.full_name if show else pseudonym(candidate.id),
        email=candidate.email if show else None, phone=candidate.phone if show else None,
        telegram=candidate.telegram if show else None, city=candidate.city if show else "",
        source=candidate.source, created_at=candidate.created_at, retain_until=candidate.retain_until,
        document_status=document.status.value if document else None,
        experience_months=profile.total_months if profile else None,
        skills=sorted(s for s, v in profile.data["skills"].items() if v["mentions"]) if profile else [],
        languages=languages, applications=[ApplicationOut.model_validate(a) for a in applications],
    )  # fmt: skip


@router.get("/search")
async def search(
    session: Session,
    services: Shared,
    user: Staff,
    q: str = Query("", max_length=300),
    skills: Annotated[list[str] | None, Query()] = None,
    min_years: float = Query(0, ge=0, le=40),
    blind: bool = True,
    limit: int = Query(20, ge=1, le=100),
) -> list[SearchHit]:
    """Hybrid search over CV passages: PostgreSQL full-text search (Russian and English) and pgvector
    similarity, fused by reciprocal rank. Optional filters on skills and years of experience."""
    show = sees_personal_data(user, blind)
    params: dict[str, object] = {
        "min_months": round(min_years * 12),
        "skills": skills or [],
        "limit": limit * 5,
    }
    ranked: dict[uuid.UUID, float] = {}
    snippets: dict[uuid.UUID, str] = {}
    if q.strip():
        keyword = (await session.execute(KEYWORD_SQL, {**params, "q": q})).all()
        vector = services.matcher.embedder.embed_queries([q])[0].tolist()
        semantic = (await session.execute(SEMANTIC_SQL, {**params, "v": str(vector)})).all()
        # skills named in the query ("Kafka микросервисы" -> kafka, microservices) rank candidates who
        # have them; short passages such as skill lists are otherwise close to almost any query
        query_skills = sorted(services.matcher.taxonomy.skill_ids(q))
        by_skill: list[tuple[uuid.UUID, str, float]] = []
        if query_skills:
            rows = (await session.execute(SKILL_SQL, {**params, "qs": query_skills})).all()
            by_skill = [(row[0], "", float(row[1])) for row in rows]
        for results in (keyword, semantic, by_skill):
            seen: set[uuid.UUID] = set()
            for position, (candidate_id, chunk_text, _rank) in enumerate(results):
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                ranked[candidate_id] = ranked.get(candidate_id, 0.0) + 1 / (RRF_K + position + 1)
                snippets.setdefault(candidate_id, chunk_text[:240])
    else:
        rows = (await session.execute(BROWSE_SQL, params)).all()
        ranked = {row[0]: 1.0 / (index + 1) for index, row in enumerate(rows)}
    top = sorted(ranked, key=lambda cid: -ranked[cid])[:limit]
    if not top:
        return []
    names = dict(
        (await session.execute(select(Candidate.id, Candidate.full_name).where(Candidate.id.in_(top)))).all()
    )
    profiles = {
        p.candidate_id: p
        for p in (await session.execute(select(Profile).where(Profile.candidate_id.in_(top)))).scalars()
    }
    return [
        SearchHit(candidate_id=cid, name=names.get(cid, "") if show else pseudonym(cid),
                  experience_months=profiles[cid].total_months,
                  skills=sorted(s for s, v in profiles[cid].data["skills"].items() if v["mentions"])[:12],
                  snippet=snippets.get(cid, ""), score=round(ranked[cid], 5))
        for cid in top if cid in profiles
    ]  # fmt: skip


@router.get("")
async def list_candidates(session: Session, user: Staff, blind: bool = True, limit: int = Query(50, ge=1, le=200),
                          offset: int = Query(0, ge=0)) -> list[CandidateOut]:  # fmt: skip
    show = sees_personal_data(user, blind)
    rows = (
        await session.execute(
            select(Candidate).order_by(Candidate.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    return [await _view(session, candidate, show=show) for candidate in rows]


@router.get("/{candidate_id}")
async def get_candidate(
    candidate_id: uuid.UUID, session: Session, user: Staff, blind: bool = True
) -> CandidateOut:
    show = sees_personal_data(user, blind)
    candidate = await _candidate(session, candidate_id)
    if show:
        await audit.record(
            session, "candidate.viewed", "candidate", candidate.id, actor_id=user.id, data={"blind": False}
        )
        await session.commit()
    return await _view(session, candidate, show=show)


@router.get("/{candidate_id}/cv")
async def download_cv(
    candidate_id: uuid.UUID, session: Session, services: Shared, user: Recruiter
) -> Response:
    """The original file. Every download is written to the audit log."""
    document = (await session.execute(
        select(Document).where(Document.candidate_id == candidate_id).order_by(Document.created_at.desc()).limit(1)
    )).scalar()  # fmt: skip
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no CV")
    await audit.record(
        session,
        "cv.downloaded",
        "candidate",
        candidate_id,
        actor_id=user.id,
        data={"document": str(document.id)},
    )
    await session.commit()
    media = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "image": "application/octet-stream", "text": "text/plain; charset=utf-8"}.get(document.media_type, "application/octet-stream")  # fmt: skip
    return Response(services.store.get(document.storage_key), media_type=media, headers={
        "Content-Disposition": f'attachment; filename="cv-{candidate_id.hex[:8]}"', "X-Content-Type-Options": "nosniff",
    })  # fmt: skip


@router.delete("/{candidate_id}", status_code=204, dependencies=[Writable])
async def erase(candidate_id: uuid.UUID, session: Session, services: Shared, user: Recruiter) -> Response:
    """Right to erasure (152-FZ art. 21): the candidate, their files, profile, passages and matches are
    deleted. The audit log keeps that it happened, never what was deleted."""
    candidate = await _candidate(session, candidate_id)
    keys = list(
        (
            await session.execute(select(Document.storage_key).where(Document.candidate_id == candidate_id))
        ).scalars()
    )
    # one statement; PostgreSQL's ON DELETE CASCADE removes documents, profile, passages, applications and matches
    await session.execute(delete(Candidate).where(Candidate.id == candidate.id))
    await audit.record(
        session, "candidate.erased", "candidate", candidate_id, actor_id=user.id, data={"files": len(keys)}
    )
    await session.commit()
    services.matcher.forget(candidate_id)
    shared = set(
        (await session.execute(select(Document.storage_key).where(Document.storage_key.in_(keys)))).scalars()
    )
    for key in keys:
        if key not in shared:  # the same file can belong to another candidate (identical upload)
            services.store.delete(key)
    return Response(status_code=204)
