"""A candidate profile from CV text: positions, skills with evidence and months of use, languages, education.

Everything keeps offsets into the CV text, so each fact can be shown with the words that support it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from clearhire.cv.dates import DateRange, YearMonth, find_ranges, merged_months
from clearhire.cv.languages import find_languages
from clearhire.cv.sections import Section, split_sections
from clearhire.skills import Mention, Taxonomy

DEGREE_NAMES = {0: "not stated", 1: "vocational", 2: "higher (bachelor or specialist)", 3: "master", 4: "doctorate"}
_DEGREES: list[tuple[int, re.Pattern[str]]] = [
    (4, re.compile(r"\b(ph\.?\s?d|doctor of|кандидат\w* наук|доктор\w* наук|аспирантур\w*)", re.I)),
    (3, re.compile(r"\b(master'?s?|m\.?sc|mba|магистр\w*|магистратур\w*)", re.I)),
    (2, re.compile(r"\b(bachelor'?s?|b\.?sc|b\.?a\.|b\.?s\.|бакалавр\w*|специалист\w*|высшее|university|"
                   r"университет\w*|институт\w*|академи\w*|institute|college of engineering)", re.I)),
    (1, re.compile(r"\b(college|колледж\w*|техникум\w*|среднее специальное|училищ\w*)", re.I)),
]  # fmt: skip
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w+])(?:\+\d{1,3}[\s(.-]*|8[\s(]+)\d{2,4}[)\s.-]*\d{2,3}[\s.-]*\d{2}[\s.-]*\d{2,3}(?!\d)")
_TELEGRAM = re.compile(r"(?:t\.me/|telegram[:\s]+@?|tg[:\s]+@)([A-Za-z][\w]{3,31})|(?<![\w@])@([A-Za-z][\w]{3,31})\b")
_LINK = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in|github\.com|gitlab\.com)/[\w./-]+", re.I)
_BULLET = re.compile(r"^\s*(?:[-–—•·▪●*]|\d{1,2}[.)])\s")
_NAME_LINE = re.compile(r"^[A-ZА-ЯЁ][a-zа-яё'’-]+(?:\s+[A-ZА-ЯЁ][a-zа-яё'’-]+){1,2}$")
_CYRILLIC = re.compile(r"[а-яё]", re.I)
_LATIN = re.compile(r"[a-z]", re.I)


@dataclass(frozen=True, slots=True)
class Position:
    title: str
    start: YearMonth
    end: YearMonth
    current: bool
    months: int
    span: tuple[int, int]  # the whole entry: header line(s), dates and description
    dates_span: tuple[int, int]


@dataclass(slots=True)
class SkillEvidence:
    skill_id: str
    mentions: list[Mention] = field(default_factory=list)  # where the CV names the skill
    months: int = 0  # experience months of the positions that use it (named, or implied by a named skill)
    implied_by: list[str] = field(default_factory=list)  # set when the skill is only implied

    @property
    def explicit(self) -> bool:
        return bool(self.mentions)


@dataclass(frozen=True, slots=True)
class LanguageSkill:
    code: str
    level: int | None
    span: tuple[int, int] | None  # None when inferred from the language the CV is written in
    inferred: bool = False


@dataclass(frozen=True, slots=True)
class Education:
    degree: int
    text: str
    span: tuple[int, int]


@dataclass(slots=True)
class CandidateProfile:
    text: str
    sections: list[Section]
    positions: list[Position]
    total_months: int
    skills: dict[str, SkillEvidence]
    languages: dict[str, LanguageSkill]
    education: Education | None
    name: str | None
    contacts: dict[str, list[str]]
    language: str  # the language the CV is written in: "ru", "en" or "mixed"

    def section_kind(self, position: int) -> str:
        for section in self.sections:
            if section.start <= position < section.end:
                return section.kind
        return "header"

    def position_at(self, offset: int) -> Position | None:
        for position in self.positions:
            if position.span[0] <= offset < position.span[1]:
                return position
        return None


def cyrillic_share(text: str) -> float:
    cyrillic = len(_CYRILLIC.findall(text))
    latin = len(_LATIN.findall(text))
    return cyrillic / (cyrillic + latin) if cyrillic + latin else 0.0


def detect_language(text: str) -> str:
    """"ru" or "en" for a CV written mostly in one of them; Russian CVs are full of Latin tech names."""
    share = cyrillic_share(text)
    if share >= 0.5:
        return "ru"
    if share <= 0.1:
        return "en"
    return "mixed"


def _line_start(text: str, offset: int) -> int:
    return text.rfind("\n", 0, offset) + 1


def _line_end(text: str, offset: int) -> int:
    end = text.find("\n", offset)
    return len(text) if end == -1 else end


def _positions(text: str, ranges: list[DateRange], bounds: dict[int, tuple[int, int]]) -> list[Position]:
    """One position per date range. An entry starts at its header line: the dates' own line when it has
    words besides the dates, else the short line just above it (the "Company — Title" line)."""
    starts: list[int] = []
    for date_range in ranges:
        line_start = _line_start(text, date_range.span[0])
        line_end = _line_end(text, date_range.span[1])
        own_words = len((text[line_start : date_range.span[0]] + text[date_range.span[1] : line_end]).split())
        start = line_start
        if own_words < 3 and line_start > 0:
            previous_start = _line_start(text, line_start - 1)
            previous = text[previous_start : line_start - 1]
            is_previous_entry = bool(starts) and previous_start <= starts[-1]
            is_heading = previous_start <= bounds[len(starts)][0]  # the section's own heading line
            if (
                previous.strip()
                and len(previous) <= 120
                and not _BULLET.match(previous)
                and not is_previous_entry
                and not is_heading
            ):
                start = previous_start
        starts.append(start)
    positions: list[Position] = []
    for index, date_range in enumerate(ranges):
        start = starts[index]
        section_end = bounds[index][1]
        end = min(starts[index + 1] if index + 1 < len(ranges) else section_end, section_end)
        header = text[start:_line_end(text, date_range.span[1])]
        title = (header.replace(text[date_range.span[0] : date_range.span[1]], " ")).strip(" \n,|—–-")
        if not title:  # hh.ru layout: dates first, then the company and title lines
            following = text[date_range.span[1] : end].strip().split("\n")
            title = " — ".join(line.strip() for line in following[:2] if line.strip() and not _BULLET.match(line))
        title = " ".join(title.split())[:140]
        positions.append(
            Position(title, date_range.start, date_range.end, date_range.current, date_range.months,
                     (start, max(end, date_range.span[1])), date_range.span)
        )  # fmt: skip
    return positions


def _contacts(text: str) -> dict[str, list[str]]:
    telegram = [a or b for a, b in _TELEGRAM.findall(text)]
    return {
        "email": sorted(set(_EMAIL.findall(text))),
        "phone": sorted({" ".join(p.split()) for p in _PHONE.findall(text)}),
        "telegram": sorted(set(telegram)),
        "links": sorted({link.rstrip(".,") for link in _LINK.findall(text)}),
    }


def _name(text: str, sections: list[Section]) -> str | None:
    header = next((s for s in sections if s.kind == "header"), None)
    region = text[header.start : header.end] if header else text[:300]
    for line in region.split("\n")[:4]:
        candidate = line.strip()
        lowered = candidate.lower()
        if any(word in lowered for word in ("resume", "curriculum", "резюме", "cv")):
            continue
        if _NAME_LINE.match(candidate):
            return candidate
    return None


def extract_profile(text: str, taxonomy: Taxonomy, *, today: date | None = None) -> CandidateProfile:
    today = today or date.today()
    sections = split_sections(text)
    experience = [s for s in sections if s.kind == "experience"]
    if not experience:  # no headings: take dates from everywhere except education and courses
        experience = [s for s in sections if s.kind not in ("education", "certifications")]
    ranges: list[DateRange] = []
    bounds: list[tuple[int, int]] = []
    for section in experience:
        for date_range in find_ranges(text[section.start : section.end], today):
            shifted = (date_range.span[0] + section.start, date_range.span[1] + section.start)
            ranges.append(DateRange(date_range.start, date_range.end, date_range.current, shifted))
            bounds.append((section.start, section.end))
    positions = _positions(text, ranges, dict(enumerate(bounds)))

    skills: dict[str, SkillEvidence] = {}
    mentions = taxonomy.find(text)
    for mention in mentions:
        skills.setdefault(mention.skill_id, SkillEvidence(mention.skill_id)).mentions.append(mention)
    # months per skill: the date ranges of every position that names it or a skill implying it
    skill_ranges: dict[str, list[DateRange]] = {}
    for position in positions:
        named = {m.skill_id for m in mentions if position.span[0] <= m.start < position.span[1]}
        for skill_id in taxonomy.closure(named):
            skill_ranges.setdefault(skill_id, []).append(
                DateRange(position.start, position.end, position.current, position.span)
            )
    for skill_id in taxonomy.closure(set(skills)) - set(skills):
        implied_by = sorted(s for s in skills if skill_id in taxonomy.closure({s}))
        skills[skill_id] = SkillEvidence(skill_id, implied_by=implied_by)
    for skill_id, evidence in skills.items():
        evidence.months = merged_months(skill_ranges.get(skill_id, []))

    languages: dict[str, LanguageSkill] = {}
    language_sections = [s for s in sections if s.kind == "languages"]
    for region_start, region_end, preferred in [
        *((s.start, s.end, True) for s in language_sections),
        (0, len(text), False),
    ]:
        for found in find_languages(text[region_start:region_end]):
            span = (found.span[0] + region_start, found.span[1] + region_start)
            current = languages.get(found.code)
            if current is None or (preferred and (current.level or 0) < (found.level or 0)):
                languages[found.code] = LanguageSkill(found.code, found.level, span)
    written_in = detect_language(text)
    if cyrillic_share(text) >= 0.35 and "ru" not in languages:  # a CV written largely in Russian
        languages["ru"] = LanguageSkill("ru", 6, None, inferred=True)

    education: Education | None = None
    for section in [s for s in sections if s.kind == "education"] or sections:
        chunk = text[section.start : section.end]
        for degree, pattern in _DEGREES:
            match = pattern.search(chunk)
            if match and (education is None or degree > education.degree):
                start = section.start + _line_start(chunk, match.start())
                end = section.start + _line_end(chunk, match.end())
                education = Education(degree, text[start:end].strip(), (start, end))
                break

    return CandidateProfile(
        text=text,
        sections=sections,
        positions=positions,
        total_months=merged_months(ranges),
        skills=skills,
        languages=languages,
        education=education,
        name=_name(text, sections),
        contacts=_contacts(text),
        language=written_in,
    )
