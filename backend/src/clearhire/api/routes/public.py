"""The careers site's API: open vacancies, applying with a CV, and a private status page."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile, status
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from clearhire.api.deps import Session, Shared
from clearhire.api.schemas import ApplyOut, PublicVacancy, StatusOut
from clearhire.db.models import (
    Application,
    Document,
    DocumentStatus,
    Source,
    Stage,
    StageEvent,
    Vacancy,
    VacancyStatus,
)
from clearhire.security import status_token
from clearhire.services.pipeline import UploadRejected, add_candidate
from clearhire.tasks import enqueue_parse

router = APIRouter(prefix="/api/public", tags=["careers site"])
PUBLIC_STAGE = {Stage.NEW: "received", Stage.SCREENING: "in review", Stage.INTERVIEW: "interview",
                Stage.OFFER: "offer", Stage.HIRED: "hired", Stage.REJECTED: "closed"}  # fmt: skip
_email = TypeAdapter(EmailStr)


class RateLimit:
    """At most `limit` applications per IP address per hour (per API process)."""

    def __init__(self, limit: int = 10, window: float = 3600) -> None:
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self.hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "too many applications from this address, try later"
            )
        hits.append(now)


limiter = RateLimit()


async def _open(session: Session, vacancy_id: uuid.UUID) -> Vacancy:
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None or vacancy.status != VacancyStatus.OPEN:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vacancy not found")
    return vacancy


def _public(vacancy: Vacancy) -> PublicVacancy:
    return PublicVacancy(id=vacancy.id, title=vacancy.title, company=vacancy.company, location=vacancy.location,
                         remote=vacancy.remote, language=vacancy.language, description=vacancy.description,
                         created_at=vacancy.created_at)  # fmt: skip


@router.get("/vacancies")
async def vacancies(session: Session) -> list[PublicVacancy]:
    rows = (await session.execute(
        select(Vacancy).where(Vacancy.status == VacancyStatus.OPEN).order_by(Vacancy.created_at.desc())
    )).scalars()  # fmt: skip
    return [_public(v) for v in rows]


@router.get("/vacancies/{vacancy_id}")
async def vacancy(vacancy_id: uuid.UUID, session: Session) -> PublicVacancy:
    return _public(await _open(session, vacancy_id))


@router.post("/vacancies/{vacancy_id}/apply", status_code=201)
async def apply(
    vacancy_id: uuid.UUID,
    request: Request,
    session: Session,
    services: Shared,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    full_name: Annotated[str, Form(min_length=2, max_length=200)],
    email: Annotated[str, Form(max_length=254)],
    consent: Annotated[bool, Form()],
    telegram: Annotated[str | None, Form(max_length=64)] = None,
) -> ApplyOut:
    """Apply with a CV. The answer carries a private token for the status page; keep it."""
    limiter.check(request.client.host if request.client else "unknown")
    vacancy = await _open(session, vacancy_id)
    try:
        address = str(_email.validate_python(email))
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid e-mail address") from exc
    data = await file.read(services.settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        candidate, document = await add_candidate(
            session, services, data, file.filename or "cv", source=Source.PORTAL, consent=consent,
            full_name=full_name, email=address, telegram=(telegram or "").lstrip("@") or None,
            actor=("candidate", None),
        )  # fmt: skip
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    application = Application(candidate_id=candidate.id, vacancy_id=vacancy.id, source=Source.PORTAL,
                              status_token=status_token())  # fmt: skip
    session.add(application)
    await session.flush()
    session.add(StageEvent(application_id=application.id, stage=Stage.NEW))
    await session.commit()
    await enqueue_parse(document.id, background)
    await request.app.state.events.publish("application.received", application=str(application.id),
                                           vacancy=vacancy.title)  # fmt: skip
    return ApplyOut(application_id=application.id, status_token=application.status_token)


@router.get("/status/{token}")
async def application_status(token: str, session: Session) -> StatusOut:
    application = (
        await session.execute(select(Application).where(Application.status_token == token))
    ).scalar()
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown status link")
    vacancy = await session.get(Vacancy, application.vacancy_id)
    assert vacancy is not None
    parsed = (await session.execute(select(Document.id).where(
        Document.candidate_id == application.candidate_id, Document.status == DocumentStatus.PARSED
    ).limit(1))).scalar() is not None  # fmt: skip
    return StatusOut(vacancy=vacancy.title, company=vacancy.company, stage=PUBLIC_STAGE[application.stage],
                     updated_at=application.updated_at, cv_read=parsed)  # fmt: skip
