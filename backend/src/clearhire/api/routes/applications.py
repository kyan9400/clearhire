from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from clearhire import audit
from clearhire.api.deps import Recruiter, Session, Shared, Staff, Writable
from clearhire.api.schemas import ApplicationIn, ApplicationOut, NoteIn, NoteOut, StagePatch
from clearhire.db.models import Application, Candidate, Note, Source, StageEvent, Vacancy
from clearhire.security import status_token

router = APIRouter(prefix="/api/applications", tags=["applications"])


async def _application(session: Session, application_id: uuid.UUID) -> Application:
    application = await session.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
    return application


@router.post("", status_code=201, dependencies=[Writable])
async def create(body: ApplicationIn, session: Session, services: Shared, user: Recruiter) -> ApplicationOut:
    """Put an existing candidate into a vacancy's pipeline (from talent search)."""
    vacancy = await session.get(Vacancy, body.vacancy_id)
    if vacancy is None or await session.get(Candidate, body.candidate_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate or vacancy not found")
    application = Application(candidate_id=body.candidate_id, vacancy_id=body.vacancy_id, source=Source.UPLOAD,
                              status_token=status_token())  # fmt: skip
    session.add(application)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "already in this vacancy's pipeline") from exc
    session.add(StageEvent(application_id=application.id, stage=application.stage, by_user=user.id))
    await services.matcher.compute(session, vacancy, [body.candidate_id])
    await audit.record(session, "application.created", "application", application.id, actor_id=user.id,
                       data={"vacancy": str(vacancy.id), "candidate": str(body.candidate_id)})  # fmt: skip
    await session.commit()
    return ApplicationOut.model_validate(application)


@router.get("")
async def list_applications(
    session: Session, user: Staff, vacancy_id: uuid.UUID | None = None
) -> list[ApplicationOut]:
    query = select(Application).order_by(Application.updated_at.desc())
    if vacancy_id is not None:
        query = query.where(Application.vacancy_id == vacancy_id)
    return [ApplicationOut.model_validate(a) for a in (await session.execute(query.limit(1000))).scalars()]


@router.patch("/{application_id}", dependencies=[Writable])
async def move(
    application_id: uuid.UUID, body: StagePatch, request: Request, session: Session, user: Staff
) -> ApplicationOut:
    """Move a candidate to another stage. Every move is kept for analytics and the audit log; the
    candidate is told through their status page and, if they use it, the Telegram bot."""
    application = await _application(session, application_id)
    if body.stage == application.stage:
        return ApplicationOut.model_validate(application)
    previous = application.stage
    application.stage = body.stage
    session.add(StageEvent(application_id=application.id, stage=body.stage, by_user=user.id))
    await audit.record(session, "application.stage_changed", "application", application.id, actor_id=user.id,
                       data={"from": previous.value, "to": body.stage.value})  # fmt: skip
    await session.commit()
    await request.app.state.events.publish("application.stage_changed", application=str(application.id),
                                           candidate=str(application.candidate_id), stage=body.stage.value)  # fmt: skip
    return ApplicationOut.model_validate(application)


@router.get("/{application_id}/notes")
async def notes(application_id: uuid.UUID, session: Session, user: Staff) -> list[NoteOut]:
    await _application(session, application_id)
    rows = (
        await session.execute(
            select(Note).where(Note.application_id == application_id).order_by(Note.created_at)
        )
    ).scalars()
    return [NoteOut.model_validate(n) for n in rows]


@router.post("/{application_id}/notes", status_code=201, dependencies=[Writable])
async def add_note(application_id: uuid.UUID, body: NoteIn, session: Session, user: Staff) -> NoteOut:
    await _application(session, application_id)
    note = Note(application_id=application_id, author_id=user.id, text=body.text)
    session.add(note)
    await session.flush()
    await audit.record(
        session, "note.added", "application", application_id, actor_id=user.id, data={"note": note.id}
    )
    await session.commit()
    return NoteOut.model_validate(note)
