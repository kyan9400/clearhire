"""Request and response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from clearhire.db.models import Role, Source, Stage, VacancyStatus
from clearhire.vacancy import KINDS

StageName = Literal["new", "screening", "interview", "offer", "hired", "rejected"]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str
    role: Role


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth token type, not a secret
    user: UserOut


class RequirementIO(BaseModel):
    id: str = Field(pattern=r"^r\d{1,3}$")
    text: str = Field(min_length=1, max_length=400)
    kind: str
    must: bool = True
    skills: list[str] = Field(default_factory=list, max_length=8)
    any_of: bool = False
    min_years: float | None = Field(default=None, ge=0, le=40)
    language: str | None = Field(default=None, max_length=8)
    min_level: int | None = Field(default=None, ge=1, le=7)
    min_degree: int | None = Field(default=None, ge=1, le=4)
    weight: float = Field(default=1.0, gt=0, le=1)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        return value


class VacancyIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=120)
    remote: bool = False
    language: Literal["en", "ru"] = "en"
    description: str = Field(min_length=10, max_length=20000)
    status: VacancyStatus = VacancyStatus.DRAFT


class VacancyPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=120)
    remote: bool | None = None
    description: str | None = Field(default=None, min_length=10, max_length=20000)
    status: VacancyStatus | None = None


class VacancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    company: str
    location: str
    remote: bool
    language: str
    description: str
    status: VacancyStatus
    requirements: list[RequirementIO]
    requirements_version: int
    created_at: datetime
    applicants: int = 0
    qualified: int = 0


class ParseRequirementsIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class RequirementsIn(BaseModel):
    requirements: list[RequirementIO] = Field(max_length=40)


class EvidenceOut(BaseModel):
    quote: str
    highlight: tuple[int, int]
    page: int | None
    section: str
    source: str


class RequirementResultOut(BaseModel):
    requirement_id: str
    status: Literal["met", "partial", "missing"]
    detail: str
    evidence: list[EvidenceOut]


class RankedCandidate(BaseModel):
    candidate_id: uuid.UUID
    application_id: uuid.UUID | None
    name: str  # a pseudonym in blind mode
    stage: StageName | None
    score: float
    must_met: int
    must_total: int
    must_have_gaps: int
    semantic: float
    qualified: bool
    experience_months: int
    strengths: list[str]  # requirement ids fully met
    gaps: list[str]  # must-have requirement ids missing


class RankingOut(BaseModel):
    vacancy_id: uuid.UUID
    scope: Literal["applicants", "pool"]
    blind: bool
    total: int
    items: list[RankedCandidate]


class MatchOut(BaseModel):
    candidate_id: uuid.UUID
    vacancy_id: uuid.UUID
    name: str
    blind: bool
    score: float
    must_met: int
    must_total: int
    semantic: float
    requirements: list[RequirementIO]
    results: list[RequirementResultOut]


class CandidateOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    telegram: str | None
    city: str
    source: Source
    created_at: datetime
    retain_until: date
    document_status: str | None
    experience_months: int | None
    skills: list[str]
    languages: dict[str, int | None]
    applications: list[ApplicationOut] = Field(default_factory=list)


class SearchHit(BaseModel):
    candidate_id: uuid.UUID
    name: str
    experience_months: int
    skills: list[str]
    snippet: str
    score: float


class ApplicationIn(BaseModel):
    candidate_id: uuid.UUID
    vacancy_id: uuid.UUID


class StagePatch(BaseModel):
    stage: Stage


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    candidate_id: uuid.UUID
    vacancy_id: uuid.UUID
    stage: Stage
    source: Source
    created_at: datetime
    updated_at: datetime


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author_id: uuid.UUID | None
    text: str
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    at: datetime
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str
    data: dict[str, object]
    hash: str


class PublicVacancy(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    location: str
    remote: bool
    language: str
    description: str
    created_at: datetime


class ApplyOut(BaseModel):
    application_id: uuid.UUID
    status_token: str


class StatusOut(BaseModel):
    vacancy: str
    company: str
    stage: Literal["received", "in review", "interview", "offer", "hired", "closed"]
    updated_at: datetime
    cv_read: bool


CandidateOut.model_rebuild()
