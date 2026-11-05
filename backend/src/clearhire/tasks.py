"""Background jobs. With Redis (CLEARHIRE_REDIS_URL) CVs are read by the Taskiq worker:

    taskiq worker clearhire.tasks:broker

Without Redis they are read in the API process after the response is sent, which is enough for
development and the tests.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import BackgroundTasks
from taskiq import AsyncBroker, InMemoryBroker

from clearhire.config import Settings, get_settings
from clearhire.db.session import sessions
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
    _services = Services(settings=settings, store=FileStore(settings.storage_dir), ocr=ocr if ocr.available else None,
                         matcher=Matcher(load_embedder(settings.embedding_model), load_taxonomy()))  # fmt: skip
    return _services


async def run_parse(document_id: uuid.UUID, services: Services | None = None) -> None:
    async with sessions()() as session:
        try:
            await process_document(session, services or build_services(), document_id)
        except Exception:  # keep the worker alive; the failure is logged with the document id
            log.exception("reading CV %s failed", document_id)
            raise


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
