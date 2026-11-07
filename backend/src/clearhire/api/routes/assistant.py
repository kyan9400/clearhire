"""The AI assistant in the console: a grounded summary of each match, and questions about a candidate.

The model only ever reads redacted text, whatever the reviewer's blind setting, so personal details can
neither leak into an answer nor sway it. Every call is written to the audit log with the model's name.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from clearhire import audit
from clearhire.api.deps import Session, Shared, Staff
from clearhire.api.routes.public import RateLimit
from clearhire.api.schemas import AnswerOut, AskIn, AssistantStatus, SummaryOut
from clearhire.assistant import LLMError, MatchContext, ask, summarize
from clearhire.db.models import AISummary, Candidate, Profile, User, Vacancy
from clearhire.services.pipeline import Services

router = APIRouter(prefix="/api", tags=["assistant"])
_limits: dict[int, RateLimit] = {}


def _limit(services: Services, user: User) -> None:
    per_hour = services.settings.llm_calls_per_hour
    _limits.setdefault(per_hour, RateLimit(per_hour, what="assistant requests")).check(str(user.id))


async def _context(session: Session, services: Services, vacancy_id: uuid.UUID, candidate_id: uuid.UUID) -> tuple[Vacancy, MatchContext, int]:  # fmt: skip
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vacancy not found")
    if await session.get(Candidate, candidate_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    results = await services.matcher.compute(session, vacancy, [candidate_id])
    if candidate_id not in results:
        raise HTTPException(status.HTTP_409_CONFLICT, "the CV has not been read yet")
    await session.commit()
    cv = (await services.matcher.load(session, [candidate_id]))[candidate_id]
    version = (
        await session.execute(select(Profile.version).where(Profile.candidate_id == candidate_id))
    ).scalar_one()
    context = MatchContext.build(
        vacancy.title, vacancy.language, vacancy.requirements, cv, results[candidate_id]
    )
    return vacancy, context, version


@router.get("/assistant")
async def assistant_status(services: Shared, user: Staff) -> AssistantStatus:
    return AssistantStatus(
        enabled=services.llm is not None, model=services.llm.name if services.llm else None
    )


@router.post("/vacancies/{vacancy_id}/matches/{candidate_id}/summary")
async def match_summary(vacancy_id: uuid.UUID, candidate_id: uuid.UUID, session: Session, services: Shared,
                        user: Staff, refresh: bool = False) -> SummaryOut:  # fmt: skip
    """A few sentences on the match, each citing its evidence. Kept until the requirements, the CV or the
    model change; `refresh` writes a new one."""
    vacancy, context, profile_version = await _context(session, services, vacancy_id, candidate_id)
    model_name = services.llm.name if services.llm else "rules"
    stored = await session.get(AISummary, (candidate_id, vacancy_id))
    if (stored and not refresh and stored.requirements_version == vacancy.requirements_version
            and stored.profile_version == profile_version and stored.model in (model_name, "rules")
            and not (stored.model == "rules" and services.llm)):  # fmt: skip
        return SummaryOut(**stored.payload, cached=True, created_at=stored.created_at)
    if services.llm:
        _limit(services, user)
    summary = await summarize(context, services.llm)
    payload = {"sentences": [asdict(s) for s in summary.sentences], "sources": summary.sources,
               "model": summary.model, "dropped": summary.dropped, "notes": summary.notes}  # fmt: skip
    now = datetime.now(UTC)
    statement = insert(AISummary).values(candidate_id=candidate_id, vacancy_id=vacancy_id, model=summary.model,
                                         requirements_version=vacancy.requirements_version,
                                         profile_version=profile_version, payload=payload, created_at=now)  # fmt: skip
    await session.execute(statement.on_conflict_do_update(
        index_elements=[AISummary.candidate_id, AISummary.vacancy_id],
        set_={c: statement.excluded[c] for c in ("requirements_version", "profile_version", "model", "payload", "created_at")},
    ))  # fmt: skip
    await audit.record(session, "ai.summary", "candidate", candidate_id, actor_type="ai", actor_id=summary.model, data={
        "vacancy": str(vacancy_id), "requested_by": str(user.id), "sentences": len(summary.sentences),
        "dropped": summary.dropped, "seconds": round(summary.seconds, 2), "tokens": summary.tokens,
    })  # fmt: skip
    await session.commit()
    return SummaryOut(**payload, cached=False, created_at=now)


@router.post("/vacancies/{vacancy_id}/matches/{candidate_id}/ask")
async def ask_about_candidate(vacancy_id: uuid.UUID, candidate_id: uuid.UUID, body: AskIn, session: Session,
                              services: Shared, user: Staff) -> AnswerOut:  # fmt: skip
    """Answer a question about the candidate from their CV, citing the passages it used."""
    if services.llm is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "the AI assistant is not configured")
    _, context, _ = await _context(session, services, vacancy_id, candidate_id)
    if not context.result.results and not context.cv.chunks:
        raise HTTPException(status.HTTP_409_CONFLICT, "nothing was read from this CV")
    _limit(services, user)
    try:
        answer = await ask(
            context, body.question.strip(), services.llm, services.matcher.embedder, services.matcher.taxonomy
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    await audit.record(session, "ai.question", "candidate", candidate_id, actor_type="ai", actor_id=answer.model, data={
        "vacancy": str(vacancy_id), "asked_by": str(user.id), "question": body.question.strip(),
        "refused": answer.refused, "grounded": answer.grounded, "tools": [s.tool for s in answer.steps],
        "sources": [s["ref"] for s in answer.sources], "seconds": round(answer.seconds, 2), "tokens": answer.tokens,
        "answer_sha256": hashlib.sha256(answer.text.encode()).hexdigest(),
    })  # fmt: skip
    await session.commit()
    return AnswerOut(text=answer.text, sources=answer.sources, model=answer.model, refused=answer.refused,
                     grounded=answer.grounded, quotes=answer.quotes, seconds=round(answer.seconds, 2),
                     steps=[{"tool": s.tool, "arguments": {k: str(v) for k, v in s.arguments.items()}, "refs": s.refs}
                            for s in answer.steps])  # fmt: skip
