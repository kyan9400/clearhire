"""CV sections: "Work experience" / "Опыт работы", "Skills" / "Ключевые навыки", and so on."""

from __future__ import annotations

from dataclasses import dataclass

from clearhire.text import fold

_HEADINGS: dict[str, tuple[str, ...]] = {
    "experience": (
        "experience", "work experience", "professional experience", "employment", "employment history",
        "work history", "career history", "relevant experience", "опыт работы", "опыт", "трудовая деятельность",
        "места работы", "профессиональный опыт", "опыт работы и проекты",
    ),
    "education": (
        "education", "academic background", "education and training", "образование", "высшее образование",
    ),
    "skills": (
        "skills", "technical skills", "key skills", "core skills", "hard skills", "skills and tools",
        "skills & tools", "tech stack", "technical stack", "навыки", "ключевые навыки",
        "профессиональные навыки", "технические навыки", "стек технологий", "навыки и технологии",
    ),
    "languages": (
        "languages", "language skills", "языки", "знание языков", "владение языками", "иностранные языки",
    ),
    "summary": (
        "summary", "about", "about me", "profile", "professional summary", "objective", "о себе", "обо мне",
        "профиль", "цель", "краткая информация",
    ),
    "projects": ("projects", "personal projects", "pet projects", "selected projects", "проекты", "пет-проекты"),
    "certifications": (
        "certifications", "certificates", "courses", "training", "курсы", "сертификаты", "курсы и сертификаты",
        "повышение квалификации", "дополнительное образование",
    ),
    "contacts": ("contacts", "contact", "contact information", "контакты", "контактная информация"),
    "other": (
        "achievements", "достижения", "interests", "hobbies", "хобби", "интересы", "references", "рекомендации",
        "additional information", "дополнительная информация",
    ),
}  # fmt: skip

_LOOKUP = {heading: kind for kind, headings in _HEADINGS.items() for heading in headings}
_TRIM = " \t:：-–—•·*#|_=."


@dataclass(frozen=True, slots=True)
class Section:
    kind: str  # one of the keys above, or "header" for the text before the first heading
    title: str
    start: int
    end: int


def heading_kind(line: str) -> str | None:
    stripped = line.strip(_TRIM)
    if not stripped or len(stripped) > 40:
        return None
    return _LOOKUP.get(" ".join(fold(stripped).split()))


def split_sections(text: str) -> list[Section]:
    """The CV cut at its headings. Every character belongs to exactly one section."""
    sections: list[Section] = []
    kind, title, start = "header", "", 0
    offset = 0
    for line in text.split("\n"):
        found = heading_kind(line)
        if found is not None:
            if offset > start or sections or kind != "header":
                sections.append(Section(kind, title, start, offset))
            kind, title, start = found, line.strip(_TRIM), offset
        offset += len(line) + 1
    sections.append(Section(kind, title, start, len(text)))
    return [section for section in sections if section.end > section.start or section.kind != "header"]


def section_at(sections: list[Section], position: int) -> Section | None:
    for section in sections:
        if section.start <= position < section.end:
            return section
    return None
