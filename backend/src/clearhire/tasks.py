"""Background jobs. With Redis (CLEARHIRE_REDIS_URL) CVs are read by the Taskiq worker:

    taskiq worker clearhire.tasks:broker

Without Redis they are read in the API process after the response is sent, which is enough for
development and the tests.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import AsyncBroker, InMemoryBroker

from clearhire.config import Settings, get_settings
from clearhire.db.models import Application, Document, DocumentStatus, Match, Vacancy
from clearhire.db.session import sessions
from clearhire.events import Events
from clearhire.services.pipeline import Services, process_document

log = logging.getLogger(__name__)


def _broker() -> AsyncBroker:
    settings = get_settings()
    if settings.redis_url:
        from taskiq_redis import ListQueueBroker

        return ListQueueBroker(settings.redis_url, queue_name="clearhire:jobs")
    return InMemoryBroker()


broker = _broker()


_services: Services | None = None


def build_services(settings: Settings | None = None) -> Services:
    """Shared, slow-to-build objects: the embedding model, the taxonomy, OCR and the file store.
    Built once per process."""
    global _services
    if _services is not None:
        return _services
    from clearhire.embeddings import load_embedder
    from clearhire.ingest import TesseractOcr
    from clearhire.services.matcher import Matcher
    from clearhire.services.storage import FileStore
    from clearhire.skills import load_taxonomy

    settings = settings or get_settings()
    ocr = TesseractOcr(settings.ocr_languages)
    llm = None
    if settings.llm_url:
        from clearhire.assistant.llm import OpenAIChat

        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        llm = OpenAIChat(settings.llm_url, settings.llm_model, api_key=key, timeout=settings.llm_timeout)
    _services = Services(settings=settings, store=FileStore(settings.storage_dir), ocr=ocr if ocr.available else None,
                         matcher=Matcher(load_embedder(settings.embedding_model), load_taxonomy()), llm=llm)  # fmt: skip
    return _services


async def run_parse(document_id: uuid.UUID, services: Services | None = None) -> None:
    services = services or build_services()
    async with sessions()() as session:
        try:
            document = await process_document(session, services, document_id)
        except Exception:  # keep the worker alive; the failure is logged with the document id
            log.exception("reading CV %s failed", document_id)
            raise
        await announce(session, services.settings, document)


async def announce(session: AsyncSession, settings: Settings, document: Document) -> None:
    """Tell other services (the Telegram bot) how the CV went for each application: matched, with the
    must-haves met, or unreadable. No names: the event bus carries ids and counts."""
    if not settings.redis_url:
        return
    rows = (await session.execute(
        select(Application.id, Application.source, Vacancy.id, Vacancy.title, Match.must_met, Match.must_total)
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .outerjoin(Match, (Match.candidate_id == Application.candidate_id) & (Match.vacancy_id == Application.vacancy_id))
        .where(Application.candidate_id == document.candidate_id)
    )).all()  # fmt: skip
    events = Events(settings.redis_url)
    try:
        for application_id, source, vacancy_id, title, must_met, must_total in rows:
            if document.status == DocumentStatus.PARSED:
                await events.publish("application.scored", application=str(application_id), vacancy=str(vacancy_id),
                                     title=title, source=source.value, must_met=must_met, must_total=must_total)  # fmt: skip
            else:
                await events.publish("application.cv_failed", application=str(application_id), title=title)
    finally:
        await events.close()


@broker.task(task_name="clearhire.parse_cv")
async def parse_cv(document_id: str) -> None:
    await run_parse(uuid.UUID(document_id))


async def enqueue_parse(document_id: uuid.UUID, background: BackgroundTasks | None = None) -> None:
    if get_settings().redis_url:
        await parse_cv.kiq(str(document_id))
    elif background is not None:
        background.add_task(run_parse, document_id)
    else:
        await run_parse(document_id)
