"""Vacancy requirements, parsed from the vacancy text. Recruiters can edit them; the parse is a draft.

Each requirement line becomes one check: a skill set (all of them, or any one), optionally with
minimum years; total experience; a language at a minimum level; a degree; or free text, which is
matched by meaning.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from clearhire.cv.languages import find_languages, parse_level
from clearhire.skills import Taxonomy
from clearhire.text import fold

KINDS = ("skill", "experience", "language", "education", "other")

_SECTION_KINDS: dict[str, tuple[str, ...]] = {
    "must": (
        "requirements", "required", "must have", "must-have", "what we expect", "what you need", "you have",
        "qualifications", "требования", "мы ожидаем", "мы ждем", "что мы ждем", "что мы ждем от кандидата",
        "ожидания от кандидата", "необходимо", "что нужно", "наши ожидания", "кого мы ищем",
    ),
    "nice": (
        "nice to have", "nice-to-have", "a plus", "bonus points", "preferred", "будет плюсом",
        "будет преимуществом", "желательно", "плюсом будет", "дополнительным плюсом будет",
    ),
    "duties": (
        "responsibilities", "what you will do", "what you'll do", "your tasks", "tasks", "обязанности",
        "задачи", "чем предстоит заниматься", "что нужно делать", "чем вы будете заниматься",
    ),
    "offer": ("we offer", "benefits", "conditions", "условия", "мы предлагаем", "что мы предлагаем"),
    "about": ("about us", "about the company", "о компании", "о нас", "about the role", "о вакансии"),
}  # fmt: skip
_HEADING_LOOKUP = {heading: kind for kind, headings in _SECTION_KINDS.items() for heading in headings}
_BULLET = re.compile(r"^\s*(?:[-–—•·▪●*✓✔]|\d{1,2}[.)])\s*")
_YEARS = re.compile(
    r"(?:(?:от|не менее|не меньше|at least|minimum|min\.?|over|более)\s*)?"
    r"(\d+(?:[.,]5)?)\s*(?:\+|\s*[-–—]\s*\d+)?\s*(?:years?|yrs?|лет|года|год)",
    re.IGNORECASE,
)
_ANY_OF = re.compile(r"\s(?:or|или|либо)\s|/|\bany of\b|\bодин из\b", re.IGNORECASE)
_DEGREE = re.compile(
    r"(degree|bachelor|master|ph\.?d|higher education|высшее|бакалавр|магистр|образовани)", re.IGNORECASE
)
_MASTER = re.compile(r"(master|магистр|ph\.?d|кандидат наук)", re.IGNORECASE)


@dataclass
class Requirement:
    id: str
    text: str
    kind: str
    must: bool = True
    skills: list[str] = field(default_factory=list)
    any_of: bool = False
    min_years: float | None = None
    language: str | None = None
    min_level: int | None = None
    min_degree: int | None = None
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Requirement:
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})


def _heading_kind(line: str) -> str | None:
    stripped = _BULLET.sub("", line).strip(" \t:：-–—*#.!?")
    if not stripped or len(stripped) > 60:
        return None
    return _HEADING_LOOKUP.get(" ".join(fold(stripped).split()))


def parse_requirement(text: str, taxonomy: Taxonomy, *, must: bool, rid: str) -> Requirement:
    """One requirement line → a structured check."""
    clean = _BULLET.sub("", text).strip().rstrip(";.")
    weight = 1.0 if must else 0.5
    languages = find_languages(clean)
    mentions = [
        m for m in taxonomy.find(clean) if not any(lm.span[0] <= m.start < lm.span[1] for lm in languages)
    ]
    skills: list[str] = []
    for mention in mentions:
        if mention.skill_id not in skills:
            skills.append(mention.skill_id)
    years = _YEARS.search(clean)
    min_years = float(years.group(1).replace(",", ".")) if years else None
    if languages and not skills:
        level = parse_level(clean)
        return Requirement(rid, clean, "language", must, language=languages[0].code,
                           min_level=level or 3, weight=weight)  # fmt: skip
    if skills:
        any_of = False
        ordered = sorted(mentions, key=lambda m: m.start)
        for previous, current in itertools.pairwise(ordered):
            if current.skill_id != previous.skill_id and _ANY_OF.search(clean[previous.end : current.start]):
                any_of = True
        return Requirement(rid, clean, "skill", must, skills=skills, any_of=any_of, min_years=min_years,
                           weight=weight)  # fmt: skip
    if min_years is not None:
        return Requirement(rid, clean, "experience", must, min_years=min_years, weight=weight)
    if _DEGREE.search(clean):
        return Requirement(rid, clean, "education", must, min_degree=3 if _MASTER.search(clean) else 2,
                           weight=weight)  # fmt: skip
    return Requirement(rid, clean, "other", must, weight=weight)


def parse_requirements(text: str, taxonomy: Taxonomy) -> list[Requirement]:
    """Requirement lines from the "Requirements" and "Nice to have" parts of a vacancy.

    Without such headings every bullet line counts as a must-have.
    """
    lines = text.split("\n")
    kinds = [_heading_kind(line) for line in lines]
    has_sections = any(kind in ("must", "nice") for kind in kinds)
    requirements: list[Requirement] = []
    current: str | None = None if has_sections else "must"
    for line, kind in zip(lines, kinds, strict=True):
        if kind is not None:
            current = kind
            continue
        body = line.strip()
        if current not in ("must", "nice") or not body:
            continue
        if not has_sections and not _BULLET.match(line):
            continue
        if len(body) < 3 or body.endswith(":"):
            continue
        requirement = parse_requirement(
            body, taxonomy, must=current == "must", rid=f"r{len(requirements) + 1}"
        )
        requirements.append(requirement)
    return requirements


def vacancy_query_text(title: str, text: str) -> str:
    """What the vacancy is about, for semantic similarity: the title and the duty and requirement lines."""
    keep: list[str] = [title]
    current: str | None = None
    for line in text.split("\n"):
        kind = _heading_kind(line)
        if kind is not None:
            current = kind
            continue
        if current in (None, "must", "nice", "duties") and line.strip():
            keep.append(_BULLET.sub("", line).strip())
    return "\n".join(keep)[:2000]
