"""The careers site's API: open vacancies, checking a CV against one before applying, applying, and a
private status page where candidates see what was read from their CV and can erase their data."""

from __future__ import annotations

import asyncio
import hmac
import time
import uuid
from collections import defaultdict, deque
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from clearhire.api.deps import Session, Shared
from clearhire.api.schemas import (
    ApplyOut,
    CheckItem,
    PrecheckOut,
    PublicRequirement,
    PublicVacancy,
    StatusOut,
    StatusStep,
)
from clearhire.api.views import evidence_view
from clearhire.cv.profile import extract_profile
from clearhire.db.models import (
    Application,
    Source,
    Stage,
    StageEvent,
    Vacancy,
    VacancyStatus,
)
from clearhire.ingest import UnreadableDocument, read_document
from clearhire.matching import IndexedCV, MatchResult, index_cv, match
from clearhire.security import status_token
from clearhire.services.matcher import page_lookup
from clearhire.services.pipeline import Services, UploadRejected, add_candidate, erase_candidate
from clearhire.tasks import enqueue_parse

router = APIRouter(prefix="/api/public", tags=["careers site"])
PUBLIC_STAGE = {Stage.NEW: "received", Stage.SCREENING: "in review", Stage.INTERVIEW: "interview",
                Stage.OFFER: "offer", Stage.HIRED: "hired", Stage.REJECTED: "closed"}  # fmt: skip
_email = TypeAdapter(EmailStr)


class RateLimit:
    """At most `limit` applications per IP address per hour (per API process)."""

    def __init__(self, limit: int = 10, window: float = 3600, what: str = "applications") -> None:
        self.limit, self.window, self.what = limit, window, what
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self.hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, f"too many {self.what} from this address, try later"
            )
        hits.append(now)


limiter = RateLimit()
precheck_limiter = RateLimit(30, what="CV checks")


async def _open(session: Session, vacancy_id: uuid.UUID) -> Vacancy:
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None or vacancy.status != VacancyStatus.OPEN:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vacancy not found")
    return vacancy


def _public(vacancy: Vacancy) -> PublicVacancy:
    return PublicVacancy(id=vacancy.id, title=vacancy.title, company=vacancy.company, location=vacancy.location,
                         remote=vacancy.remote, language=vacancy.language, description=vacancy.description,
                         created_at=vacancy.created_at, requirements=[
                             PublicRequirement(id=r["id"], text=r["text"], kind=r["kind"], must=r.get("must", True))
                             for r in vacancy.requirements
                         ])  # fmt: skip


def _from_bot(request: Request, services: Services) -> bool:
    """A request from the Telegram bot: it proves itself with the shared secret."""
    secret = services.settings.bot_secret
    given = request.headers.get("x-clearhire-bot", "")
    return bool(secret and given and hmac.compare_digest(given, secret.get_secret_value()))


def _caller(request: Request, services: Services) -> str:
    """Who the rate limits count: the client's address, or for the bot the Telegram user it acts for
    (otherwise every bot user would share the bot's one address and its limit)."""
    if _from_bot(request, services):
        return "tg:" + request.headers.get("x-telegram-user", "unknown")[:32]
    return request.client.host if request.client else "unknown"


def _items(vacancy: Vacancy, cv: IndexedCV, result: MatchResult) -> list[CheckItem]:
    """The candidate's own CV, so nothing is blacked out."""
    requirements = {r["id"]: r for r in vacancy.requirements}
    return [
        CheckItem(requirement_id=r.requirement_id, text=requirements[r.requirement_id]["text"],
                  must=requirements[r.requirement_id].get("must", True), status=r.status,
                  detail=r.detail, evidence=[evidence_view(cv, e, blind=False) for e in r.evidence])
        for r in result.results
        if r.requirement_id in requirements
    ]  # fmt: skip


@router.get("/vacancies")
async def vacancies(session: Session) -> list[PublicVacancy]:
    rows = (await session.execute(
        select(Vacancy).where(Vacancy.status == VacancyStatus.OPEN).order_by(Vacancy.created_at.desc())
    )).scalars()  # fmt: skip
    return [_public(v) for v in rows]


@router.get("/vacancies/{vacancy_id}")
async def vacancy(vacancy_id: uuid.UUID, session: Session) -> PublicVacancy:
    return _public(await _open(session, vacancy_id))


def _read_and_match(data: bytes, services: Services, vacancy: Vacancy) -> tuple[IndexedCV, MatchResult]:
    matcher = services.matcher
    parsed = read_document(data, ocr=services.ocr, max_pages=services.settings.max_pages)
    profile = extract_profile(parsed.text, matcher.taxonomy)
    cv = index_cv(profile, matcher.embedder, page_lookup(parsed.pages), blind=True)  # type: ignore[arg-type]
    return cv, match(cv, matcher.prepared(vacancy), matcher.taxonomy)


@router.post("/vacancies/{vacancy_id}/precheck")
async def precheck(
    vacancy_id: uuid.UUID,
    request: Request,
    session: Session,
    services: Shared,
    file: Annotated[UploadFile, File()],
) -> PrecheckOut:
    """Check a CV against the vacancy before applying. The file is read in memory and nothing is kept, so
    no consent is needed; the same matcher the recruiter uses gives the answer."""
    precheck_limiter.check(_caller(request, services))
    vacancy = await _open(session, vacancy_id)
    limit = services.settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"the file is larger than {services.settings.max_upload_mb} MB",
        )
    services.matcher.prepared(vacancy)  # fill the cache here, not in the worker thread
    try:
        cv, result = await asyncio.to_thread(_read_and_match, data, services, vacancy)
    except UnreadableDocument as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    taxonomy = services.matcher.taxonomy
    return PrecheckOut(must_met=result.must_met, must_total=result.must_total, qualified=result.qualified,
                       experience_months=cv.profile.total_months,
                       skills=sorted(taxonomy.name(s) for s in cv.profile.skills),
                       items=_items(vacancy, cv, result))  # fmt: skip


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
    limiter.check(_caller(request, services))
    source = Source.TELEGRAM if _from_bot(request, services) else Source.PORTAL
    vacancy = await _open(session, vacancy_id)
    try:
        address = str(_email.validate_python(email))
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid e-mail address") from exc
    data = await file.read(services.settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        candidate, document = await add_candidate(
            session, services, data, file.filename or "cv", source=source, consent=consent,
            full_name=full_name, email=address, telegram=(telegram or "").lstrip("@") or None,
            actor=("candidate", None),
        )  # fmt: skip
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    application = Application(candidate_id=candidate.id, vacancy_id=vacancy.id, source=source,
                              status_token=status_token())  # fmt: skip
    session.add(application)
    await session.flush()
    session.add(StageEvent(application_id=application.id, stage=Stage.NEW))
    await session.commit()
    await enqueue_parse(document.id, background)
    await request.app.state.events.publish("application.received", application=str(application.id),
                                           vacancy=vacancy.title)  # fmt: skip
    return ApplyOut(application_id=application.id, status_token=application.status_token)


async def _by_token(session: Session, token: str) -> Application:
    application = (
        await session.execute(select(Application).where(Application.status_token == token))
    ).scalar()
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown status link")
    return application


@router.get("/status/{token}")
async def application_status(token: str, session: Session, services: Shared) -> StatusOut:
    """Where the application is, and the same requirement-by-requirement reading the recruiter sees."""
    application = await _by_token(session, token)
    vacancy = await session.get(Vacancy, application.vacancy_id)
    assert vacancy is not None
    events = (await session.execute(
        select(StageEvent.stage, StageEvent.at).where(StageEvent.application_id == application.id)
        .order_by(StageEvent.at, StageEvent.id)
    )).all()  # fmt: skip
    timeline: list[StatusStep] = []
    for stage, at in events:
        if not timeline or timeline[-1].stage != PUBLIC_STAGE[stage]:
            timeline.append(StatusStep(stage=PUBLIC_STAGE[stage], at=at))
    items: list[CheckItem] = []
    results = await services.matcher.compute(session, vacancy, [application.candidate_id])
    if application.candidate_id in results:
        await session.commit()
        cv = (await services.matcher.load(session, [application.candidate_id]))[application.candidate_id]
        items = _items(vacancy, cv, results[application.candidate_id])
    return StatusOut(vacancy=vacancy.title, company=vacancy.company, stage=PUBLIC_STAGE[application.stage],
                     updated_at=application.updated_at, cv_read=application.candidate_id in results,
                     timeline=timeline, items=items)  # fmt: skip


@router.delete("/status/{token}", status_code=204)
async def withdraw(token: str, session: Session, services: Shared) -> Response:
    """Withdraw consent: the candidate erases their applications, CV and profile themselves."""
    application = await _by_token(session, token)
    await erase_candidate(session, services, application.candidate_id, actor=("candidate", None))
    return Response(status_code=204)
