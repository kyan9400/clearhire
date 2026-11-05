"""Database tables (PostgreSQL 16+ with pgvector)."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384  # intfloat/multilingual-e5-small


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}
    # fetch server-generated values (updated_at) with RETURNING, so no lazy load happens after a commit
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 - SQLAlchemy declares it as an instance attribute


def _enum(cls: type[enum.Enum]) -> Enum:
    return Enum(cls, name=cls.__name__.lower(), values_callable=lambda e: [m.value for m in e])


class Role(enum.StrEnum):
    ADMIN = "admin"
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"


class VacancyStatus(enum.StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class Stage(enum.StrEnum):
    NEW = "new"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"


class Source(enum.StrEnum):
    UPLOAD = "upload"  # added by a recruiter
    PORTAL = "portal"  # applied on the careers site
    TELEGRAM = "telegram"
    IMPORT = "import"  # the demo dataset


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(_enum(Role))
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    remote: Mapped[bool] = mapped_column(default=False)
    language: Mapped[str] = mapped_column(String(8), default="en")
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[list[Any]] = mapped_column(default=list)  # Requirement dicts, edited by recruiters
    requirements_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[VacancyStatus] = mapped_column(_enum(VacancyStatus), default=VacancyStatus.DRAFT)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    applications: Mapped[list[Application]] = relationship(back_populates="vacancy")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    telegram: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[Source] = mapped_column(_enum(Source))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # 152-FZ: consent to processing
    retain_until: Mapped[date] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)  # set when they talk to the bot

    documents: Mapped[list[Document]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    profile: Mapped[Profile | None] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    applications: Mapped[list[Application]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(16), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[DocumentStatus] = mapped_column(_enum(DocumentStatus), default=DocumentStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    pages: Mapped[list[Any]] = mapped_column(default=list)  # [start, end) of each page in text
    ocr_pages: Mapped[list[Any]] = mapped_column(default=list)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidate: Mapped[Candidate] = relationship(back_populates="documents")


class Profile(Base):
    """What Clearhire read from the candidate's latest CV."""

    __tablename__ = "profiles"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    data: Mapped[dict[str, Any]] = mapped_column()  # CandidateProfile.to_dict()
    total_months: Mapped[int] = mapped_column(Integer)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    language: Mapped[str] = mapped_column(String(8))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    candidate: Mapped[Candidate] = relationship(back_populates="profile")

    __table_args__ = (Index("ix_profiles_skills", "skills", postgresql_using="gin"),)


class Chunk(Base):
    """A CV passage for semantic matching and search; its embedding never saw personal details."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(32))
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM))
    search: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('russian', text) || to_tsvector('english', text)", persisted=True)
    )

    __table_args__ = (
        Index("ix_chunks_search", "search", postgresql_using="gin"),
        Index("ix_chunks_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"}),
    )  # fmt: skip


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    stage: Mapped[Stage] = mapped_column(_enum(Stage), default=Stage.NEW)
    source: Mapped[Source] = mapped_column(_enum(Source))
    status_token: Mapped[str] = mapped_column(String(64), unique=True)  # lets the candidate check progress
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    candidate: Mapped[Candidate] = relationship(back_populates="applications")
    vacancy: Mapped[Vacancy] = relationship(back_populates="applications")
    events: Mapped[list[StageEvent]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("candidate_id", "vacancy_id"),)


class StageEvent(Base):
    """Every stage change, for time-in-stage analytics."""

    __tablename__ = "stage_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[Stage] = mapped_column(_enum(Stage))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    by_user: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    application: Mapped[Application] = relationship(back_populates="events")


class Match(Base):
    """The requirement-level match of a candidate and a vacancy, cached until either side changes."""

    __tablename__ = "matches"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True
    )
    requirements_version: Mapped[int] = mapped_column(Integer)
    profile_version: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    must_have_gaps: Mapped[int] = mapped_column(Integer)
    must_met: Mapped[int] = mapped_column(Integer)
    must_total: Mapped[int] = mapped_column(Integer)
    semantic: Mapped[float] = mapped_column(Float)
    results: Mapped[list[Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_matches_rank", "vacancy_id", "must_have_gaps", "score"),)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEntry(Base):
    """Append-only, hash-chained log of every decision, human or AI.

    hash = SHA-256(previous hash + canonical JSON of this entry). Changing or deleting any entry breaks
    every hash after it; the daily Merkle roots anchored on-chain (contracts/) prove the log's history.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(String(16))  # user | ai | system | candidate
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
