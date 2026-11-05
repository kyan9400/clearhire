from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from clearhire import audit
from clearhire.api.deps import Recruiter, Session, Shared, Staff, Writable, pseudonym, sees_personal_data
from clearhire.api.schemas import (
    MatchOut,
    ParseRequirementsIn,
    RankedCandidate,
    RankingOut,
    RequirementIO,
    RequirementResultOut,
    RequirementsIn,
    VacancyIn,
    VacancyOut,
    VacancyPatch,
)
from clearhire.api.views import evidence_view
from clearhire.db.models import Application, Candidate, Match, Profile, Vacancy, VacancyStatus
from clearhire.vacancy import parse_requirements

router = APIRouter(prefix="/api/vacancies", tags=["vacancies"])


async def _get(session: Session, vacancy_id: uuid.UUID) -> Vacancy:
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vacancy not found")
    return vacancy


async def _out(session: Session, vacancy: Vacancy) -> VacancyOut:
    applicants = (await session.execute(
        select(func.count()).select_from(Application).where(Application.vacancy_id == vacancy.id)
    )).scalar_one()  # fmt: skip
    qualified = (await session.execute(
        select(func.count()).select_from(Match).join(
            Application, (Application.candidate_id == Match.candidate_id) & (Application.vacancy_id == Match.vacancy_id)
        ).where(Match.vacancy_id == vacancy.id, Match.must_met == Match.must_total,
                Match.requirements_version == vacancy.requirements_version)
    )).scalar_one()  # fmt: skip
    out = VacancyOut.model_validate(vacancy)
    out.applicants, out.qualified = applicants, qualified
    return out


@router.get("")
async def list_vacancies(
    session: Session, user: Staff, status_: Annotated[VacancyStatus | None, Query(alias="status")] = None
) -> list[VacancyOut]:
    query = select(Vacancy).order_by(Vacancy.created_at.desc())
    if status_ is not None:
        query = query.where(Vacancy.status == status_)
    vacancies = (await session.execute(query)).scalars().all()
    counts = dict((await session.execute(
        select(Application.vacancy_id, func.count()).group_by(Application.vacancy_id)
    )).all())  # fmt: skip
    qualified = dict((await session.execute(
        select(Match.vacancy_id, func.count()).join(
            Application, (Application.candidate_id == Match.candidate_id) & (Application.vacancy_id == Match.vacancy_id)
        ).where(Match.must_met == Match.must_total).group_by(Match.vacancy_id)
    )).all())  # fmt: skip
    out = []
    for vacancy in vacancies:
        item = VacancyOut.model_validate(vacancy)
        item.applicants, item.qualified = counts.get(vacancy.id, 0), qualified.get(vacancy.id, 0)
        out.append(item)
    return out


@router.post("", status_code=201, dependencies=[Writable])
async def create_vacancy(body: VacancyIn, session: Session, services: Shared, user: Recruiter) -> VacancyOut:
    requirements = parse_requirements(body.description, services.matcher.taxonomy)
    vacancy = Vacancy(
        **body.model_dump(), requirements=[r.to_dict() for r in requirements], created_by=user.id
    )
    session.add(vacancy)
    await session.flush()
    await audit.record(session, "vacancy.created", "vacancy", vacancy.id, actor_id=user.id,
                       data={"title": vacancy.title, "requirements": len(requirements)})  # fmt: skip
    await session.commit()
    return await _out(session, vacancy)


@router.get("/{vacancy_id}")
async def get_vacancy(vacancy_id: uuid.UUID, session: Session, user: Staff) -> VacancyOut:
    return await _out(session, await _get(session, vacancy_id))


@router.patch("/{vacancy_id}", dependencies=[Writable])
async def update_vacancy(
    vacancy_id: uuid.UUID, body: VacancyPatch, session: Session, user: Recruiter
) -> VacancyOut:
    vacancy = await _get(session, vacancy_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(vacancy, key, value)
    await audit.record(session, "vacancy.updated", "vacancy", vacancy.id, actor_id=user.id,
                       data={"fields": sorted(changes)})  # fmt: skip
    await session.commit()
    return await _out(session, vacancy)


@router.post("/parse-requirements")
async def parse(body: ParseRequirementsIn, services: Shared, user: Recruiter) -> list[RequirementIO]:
    """Draft requirements from a vacancy text, for the editor (nothing is saved)."""
    return [RequirementIO(**r.to_dict()) for r in parse_requirements(body.text, services.matcher.taxonomy)]


@router.put("/{vacancy_id}/requirements", dependencies=[Writable])
async def set_requirements(vacancy_id: uuid.UUID, body: RequirementsIn, session: Session, services: Shared,
                           user: Recruiter) -> VacancyOut:  # fmt: skip
    vacancy = await _get(session, vacancy_id)
    unknown = sorted({s for r in body.requirements for s in r.skills} - set(services.matcher.taxonomy.skills))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown skills: {', '.join(unknown)}")
    if len({r.id for r in body.requirements}) != len(body.requirements):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "requirement ids must be unique")
    vacancy.requirements = [r.model_dump() for r in body.requirements]
    vacancy.requirements_version += 1
    await services.matcher.drop_stale(session, vacancy)
    await audit.record(session, "vacancy.requirements_changed", "vacancy", vacancy.id, actor_id=user.id, data={
        "version": vacancy.requirements_version, "requirements": vacancy.requirements,
    })  # fmt: skip
    await session.commit()
    return await _out(session, vacancy)


@router.get("/{vacancy_id}/ranking")
async def ranking(
    vacancy_id: uuid.UUID,
    session: Session,
    services: Shared,
    user: Staff,
    scope: Literal["applicants", "pool"] = "applicants",
    blind: bool = True,
    limit: int = Query(50, ge=1, le=500),
) -> RankingOut:
    """Candidates for the vacancy, best first: fewest unmet must-haves, then requirement score, then
    similarity. `pool` ranks everyone in the database, not only applicants (talent search)."""
    vacancy = await _get(session, vacancy_id)
    show = sees_personal_data(user, blind)
    applications = {a.candidate_id: a for a in (await session.execute(
        select(Application).where(Application.vacancy_id == vacancy.id)
    )).scalars()}  # fmt: skip
    if scope == "applicants":
        ids = list(applications)
    else:
        ids = list((await session.execute(select(Profile.candidate_id))).scalars())
    stored = {m.candidate_id: m for m in (await session.execute(select(Match).where(
        Match.vacancy_id == vacancy.id, Match.requirements_version == vacancy.requirements_version,
        Match.candidate_id.in_(ids),
    ))).scalars()}  # fmt: skip
    versions = dict((await session.execute(
        select(Profile.candidate_id, Profile.version).where(Profile.candidate_id.in_(ids))
    )).all())  # fmt: skip
    stale = [cid for cid in versions if cid not in stored or stored[cid].profile_version != versions[cid]]
    if stale:
        await services.matcher.compute(session, vacancy, stale)
        await session.commit()
        stored = {m.candidate_id: m for m in (await session.execute(select(Match).where(
            Match.vacancy_id == vacancy.id, Match.requirements_version == vacancy.requirements_version,
            Match.candidate_id.in_(ids),
        ))).scalars()}  # fmt: skip
    names = dict(
        (
            await session.execute(
                select(Candidate.id, Candidate.full_name).where(Candidate.id.in_(list(stored)))
            )
        ).all()
    )
    months = dict(
        (
            await session.execute(
                select(Profile.candidate_id, Profile.total_months).where(
                    Profile.candidate_id.in_(list(stored))
                )
            )
        ).all()
    )
    must_ids = {r["id"] for r in vacancy.requirements if r.get("must")}
    ordered = sorted(
        stored.values(), key=lambda m: (m.must_have_gaps, -m.score, -m.semantic, str(m.candidate_id))
    )
    items = [
        RankedCandidate(
            candidate_id=m.candidate_id,
            application_id=applications[m.candidate_id].id if m.candidate_id in applications else None,
            name=names.get(m.candidate_id, "") if show else pseudonym(m.candidate_id),
            stage=applications[m.candidate_id].stage.value if m.candidate_id in applications else None,
            score=m.score, must_met=m.must_met, must_total=m.must_total, must_have_gaps=m.must_have_gaps,
            semantic=m.semantic, qualified=m.must_met == m.must_total,
            experience_months=months.get(m.candidate_id, 0),
            strengths=[r["requirement_id"] for r in m.results if r["status"] == "met"],
            gaps=[r["requirement_id"] for r in m.results if r["status"] == "missing" and r["requirement_id"] in must_ids],
        )
        for m in ordered[:limit]
    ]  # fmt: skip
    return RankingOut(vacancy_id=vacancy.id, scope=scope, blind=not show, total=len(stored), items=items)


@router.get("/{vacancy_id}/matches/{candidate_id}")
async def match_detail(vacancy_id: uuid.UUID, candidate_id: uuid.UUID, session: Session, services: Shared,
                       user: Staff, blind: bool = True) -> MatchOut:  # fmt: skip
    """Every requirement with its status, the reason, and the CV lines that show it."""
    vacancy = await _get(session, vacancy_id)
    candidate = await session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    results = await services.matcher.compute(session, vacancy, [candidate_id])
    if candidate_id not in results:
        raise HTTPException(status.HTTP_409_CONFLICT, "the CV has not been read yet")
    await session.commit()
    show = sees_personal_data(user, blind)
    cv = (await services.matcher.load(session, [candidate_id]))[candidate_id]
    result = results[candidate_id]
    if show:
        await audit.record(session, "candidate.viewed", "candidate", candidate_id, actor_id=user.id,
                           data={"vacancy": str(vacancy_id), "blind": False})  # fmt: skip
        await session.commit()
    return MatchOut(
        candidate_id=candidate_id, vacancy_id=vacancy_id, name=candidate.full_name if show else pseudonym(candidate_id),
        blind=not show, score=result.score, must_met=result.must_met, must_total=result.must_total,
        semantic=result.semantic, requirements=[RequirementIO(**r) for r in vacancy.requirements],
        results=[RequirementResultOut(requirement_id=r.requirement_id, status=r.status, detail=r.detail,
                                      evidence=[evidence_view(cv, e, blind=not show) for e in r.evidence])
                 for r in result.results],
    )  # fmt: skip
