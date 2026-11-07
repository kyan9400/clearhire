"""From an uploaded CV file to a profile, searchable passages and matches, with every step audited."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from clearhire import audit
from clearhire.anchoring.chain import Chain
from clearhire.assistant.llm import ChatModel
from clearhire.config import Settings
from clearhire.cv.profile import extract_profile
from clearhire.db.models import Application, Candidate, Document, DocumentStatus, Profile, Source, Vacancy
from clearhire.db.models import Chunk as ChunkRow
from clearhire.ingest import TesseractOcr, UnreadableDocument, detect_type, read_document
from clearhire.matching import index_cv
from clearhire.services.matcher import Matcher, page_lookup
from clearhire.services.storage import FileStore

PARSER_VERSION = "1"


class UploadRejected(ValueError):
    pass


@dataclass
class Services:
    """What the API, the worker and the bot share: settings, file store, OCR, the matcher and the LLM."""

    settings: Settings
    store: FileStore
    ocr: TesseractOcr | None
    matcher: Matcher
    llm: ChatModel | None = None
    chain: Chain | None = None  # the AuditAnchor contract, when anchoring is configured


async def add_candidate(
    session: AsyncSession,
    services: Services,
    data: bytes,
    filename: str,
    *,
    source: Source,
    consent: bool,
    full_name: str = "",
    email: str | None = None,
    phone: str | None = None,
    telegram: str | None = None,
    actor: tuple[str, object | None] = ("user", None),
    candidate: Candidate | None = None,
) -> tuple[Candidate, Document]:
    """Store the file and create the candidate (or add a CV to an existing one). Parsing happens later,
    in process_document, so uploads return at once."""
    if not consent:
        raise UploadRejected("consent to personal data processing is required (152-FZ)")
    if len(data) > services.settings.max_upload_mb * 1024 * 1024:
        raise UploadRejected(f"the file is larger than {services.settings.max_upload_mb} MB")
    try:
        detect_type(data)
    except UnreadableDocument as exc:
        raise UploadRejected(str(exc)) from exc
    key, digest = services.store.put(data)
    now = datetime.now(UTC)
    if candidate is None:
        candidate = Candidate(
            full_name=full_name.strip()[:200], email=email, phone=phone, telegram=telegram, source=source,
            consent_at=now, retain_until=date.today() + timedelta(days=services.settings.retention_days),
        )  # fmt: skip
        session.add(candidate)
        await session.flush()
    document = Document(
        candidate_id=candidate.id, filename=filename[:255], sha256=digest, size=len(data), storage_key=key
    )
    session.add(document)
    await session.flush()
    await audit.record(session, "candidate.consent", "candidate", candidate.id, actor_type=actor[0], actor_id=actor[1],
                       data={"source": source.value, "document": str(document.id), "sha256": digest})  # fmt: skip
    return candidate, document


async def process_document(session: AsyncSession, services: Services, document_id: uuid.UUID) -> Document:
    """Read the CV, extract the profile, embed its passages, then match it against the candidate's
    applications. Failures are stored on the document (a damaged file is not an exception)."""
    document = await session.get(Document, document_id)
    if document is None:
        raise LookupError(f"document {document_id} not found")
    candidate = await session.get(Candidate, document.candidate_id)
    assert candidate is not None
    settings = services.settings
    try:
        parsed = read_document(
            services.store.get(document.storage_key), ocr=services.ocr, max_pages=settings.max_pages
        )
    except UnreadableDocument as exc:
        document.status = DocumentStatus.FAILED
        document.error = str(exc)
        await audit.record(
            session, "cv.failed", "document", document.id, actor_type="system", data={"error": str(exc)}
        )
        await session.commit()
        return document

    taxonomy = services.matcher.taxonomy
    profile = extract_profile(parsed.text, taxonomy)
    document.text = parsed.text
    document.media_type = parsed.media_type
    document.pages = [list(span) for span in parsed.pages]
    document.ocr_pages = parsed.ocr_pages
    document.ocr_confidence = parsed.ocr_confidence
    document.status = DocumentStatus.PARSED
    document.error = None

    row = await session.get(Profile, candidate.id)
    version = (row.version + 1) if row else 1
    if row is None:
        row = Profile(candidate_id=candidate.id)
        session.add(row)
    row.document_id = document.id
    row.data = profile.to_dict()
    row.total_months = profile.total_months
    row.skills = sorted(profile.skills)
    row.language = profile.language
    row.version = version

    indexed = index_cv(profile, services.matcher.embedder, page_lookup(document.pages), blind=True)  # type: ignore[arg-type]
    await session.execute(delete(ChunkRow).where(ChunkRow.candidate_id == candidate.id))
    for ordinal, (chunk, vector) in enumerate(zip(indexed.chunks, indexed.vectors, strict=True)):
        session.add(ChunkRow(candidate_id=candidate.id, ordinal=ordinal, section=chunk.section, start=chunk.span[0],
                             end=chunk.span[1], text=chunk.text, embedding=vector.tolist()))  # fmt: skip
    if not candidate.full_name and profile.name:
        candidate.full_name = profile.name
    for field, key in (("email", "email"), ("phone", "phone"), ("telegram", "telegram")):
        if not getattr(candidate, field) and profile.contacts.get(key):
            setattr(candidate, field, profile.contacts[key][0][:60])
    await session.flush()
    services.matcher.forget(candidate.id)
    await audit.record(session, "cv.parsed", "candidate", candidate.id, actor_type="system", data={
        "document": str(document.id), "parser": PARSER_VERSION, "media_type": parsed.media_type,
        "ocr_pages": parsed.ocr_pages, "skills": len(profile.skills), "experience_months": profile.total_months,
    })  # fmt: skip

    vacancies = (await session.execute(
        select(Vacancy).join(Application, Application.vacancy_id == Vacancy.id).where(Application.candidate_id == candidate.id)
    )).scalars().all()  # fmt: skip
    for vacancy in vacancies:
        result = (await services.matcher.compute(session, vacancy, [candidate.id]))[candidate.id]
        await audit.record(session, "match.computed", "candidate", candidate.id, actor_type="ai",
                           actor_id=services.matcher.embedder.name, data={
                               "vacancy": str(vacancy.id), "requirements_version": vacancy.requirements_version,
                               "score": result.score, "must_met": result.must_met, "must_total": result.must_total,
                           })  # fmt: skip
    await session.commit()
    return document


async def erase_candidate(
    session: AsyncSession, services: Services, candidate_id: uuid.UUID, *, actor: tuple[str, object | None]
) -> None:
    """Right to erasure (152-FZ art. 21): the candidate, their files, profile, passages and matches are
    deleted. The audit log keeps that it happened, never what was deleted."""
    keys = list(
        (
            await session.execute(select(Document.storage_key).where(Document.candidate_id == candidate_id))
        ).scalars()
    )
    # one statement; PostgreSQL's ON DELETE CASCADE removes documents, profile, passages, applications and matches
    await session.execute(delete(Candidate).where(Candidate.id == candidate_id))
    await audit.record(session, "candidate.erased", "candidate", candidate_id, actor_type=actor[0],
                       actor_id=actor[1], data={"files": len(keys)})  # fmt: skip
    await session.commit()
    services.matcher.forget(candidate_id)
    shared = set(
        (await session.execute(select(Document.storage_key).where(Document.storage_key.in_(keys)))).scalars()
    )
    for key in keys:
        if key not in shared:  # the same file can belong to another candidate (identical upload)
            services.store.delete(key)
