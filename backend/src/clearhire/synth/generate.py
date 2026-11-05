"""Synthetic candidates and vacancies with known ground truth.

Each CV starts as a structured record (the truth) and is then written out as a PDF, a Word file or a
scan (synth/render.py). The evaluation reads only the files and compares what Clearhire extracts with
the record. Vacancies are generated the same way: structured requirements first, then the text.

Everyone here is fictional: names come from common-name lists, phone numbers use the unassigned
"+7 000" range, e-mail addresses use example.com, and Telegram handles are "@cand_<id>".
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from clearhire.cv.dates import DateRange, months_between
from clearhire.cv.dates import merged_months as _merged
from clearhire.skills import Taxonomy
from clearhire.synth import names
from clearhire.synth.archetypes import ARCHETYPES, BY_ID, Archetype, Choice
from clearhire.vacancy import Requirement

REFERENCE_DATE = date(2026, 10, 1)  # "today" for every generated CV; the evaluation uses the same date
SENIORITY = ("junior", "middle", "senior")
_TOTAL_YEARS = {"junior": (1.0, 2.5), "middle": (3.0, 5.5), "senior": (6.0, 12.0)}
_POSITIONS = {"junior": (1, 2), "middle": (2, 3), "senior": (2, 4)}

_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})  # fmt: skip


def translit(text: str) -> str:
    out = []
    for word in text.split(" "):
        latin = word.lower().translate(_TRANSLIT)
        out.append(latin[:1].upper() + latin[1:])
    return " ".join(out)


YearMonth = tuple[int, int]


@dataclass
class TruthPosition:
    title: str
    company: str
    start: YearMonth
    end: YearMonth
    current: bool
    skills: list[str]  # skill ids named in the title or the bullets
    bullets: list[tuple[str, list[str]]] = field(default_factory=list)  # template key + its skills

    @property
    def months(self) -> int:
        return months_between(self.start, self.end)


@dataclass
class TruthCandidate:
    id: str
    archetype: str
    seniority: str
    language: str  # the CV's language: ru | en
    gender: str  # f | m
    origin: str  # ru | en | world-<n>
    first_name: str
    last_name: str
    birth: date
    city: str
    positions: list[TruthPosition]
    listed_skills: list[str]
    languages: dict[str, int]  # language code -> level 1..7; written in the CV
    native_inferred: bool  # a Russian CV that does not state Russian
    degree: int
    university: str
    study_field: str
    graduation_year: int
    template: str = ""
    file_format: str = ""
    file: str = ""
    lead_team: int = 0  # team size in "led a team of N", 0 if none

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def explicit_skills(self) -> set[str]:
        return {s for p in self.positions for s in p.skills} | set(self.listed_skills)

    def skill_months(self, taxonomy: Taxonomy) -> dict[str, int]:
        ranges: dict[str, list[DateRange]] = {}
        for position in self.positions:
            for skill in taxonomy.closure(set(position.skills)):
                ranges.setdefault(skill, []).append(
                    DateRange(position.start, position.end, position.current, (0, 0))
                )
        return {skill: _merged(items) for skill, items in ranges.items()}

    def total_months(self) -> int:
        return _merged([DateRange(p.start, p.end, p.current, (0, 0)) for p in self.positions])

    def level(self, code: str) -> int | None:
        if code == "ru" and self.native_inferred:
            return 7
        return self.languages.get(code)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["birth"] = self.birth.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TruthCandidate:
        data = dict(data)
        data["birth"] = date.fromisoformat(data["birth"])
        data["positions"] = [
            TruthPosition(
                p["title"], p["company"], tuple(p["start"]), tuple(p["end"]), p["current"], p["skills"],
                [(key, skills) for key, skills in p.get("bullets", [])],
            )
            for p in data["positions"]
        ]  # fmt: skip
        return cls(**data)


@dataclass
class TruthVacancy:
    id: str
    archetype: str
    seniority: str
    language: str
    title: str
    company: str
    text: str
    requirements: list[Requirement]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["requirements"] = [r.to_dict() for r in self.requirements]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TruthVacancy:
        data = dict(data)
        data["requirements"] = [Requirement.from_dict(r) for r in data["requirements"]]
        return cls(**data)


def _resolve(choice: Choice, rng: random.Random) -> str:
    return rng.choice(choice) if isinstance(choice, tuple) else choice


def _skill_set(archetype: Archetype, rng: random.Random) -> tuple[list[str], list[str]]:
    """(skills used at work, skills only listed): every core skill, some common ones, maybe a rare one."""
    core = [_resolve(c, rng) for c in archetype.core]
    common = [_resolve(c, rng) for c in archetype.common if rng.random() < 0.55]
    rare = [_resolve(c, rng) for c in archetype.rare if rng.random() < 0.18]
    pool = list(dict.fromkeys(core + common + rare))
    listed_only = [s for s in pool if s not in core and rng.random() < 0.2]
    used = [s for s in pool if s not in listed_only]
    return used, listed_only


def _add_months(year_month: YearMonth, months: int) -> YearMonth:
    total = year_month[0] * 12 + (year_month[1] - 1) + months
    return total // 12, total % 12 + 1


def _career(seniority: str, rng: random.Random) -> list[tuple[YearMonth, YearMonth, bool]]:
    """Back-to-back roles ending today (or a few months ago), newest first."""
    low, high = _TOTAL_YEARS[seniority]
    total = round(rng.uniform(low, high) * 12)
    count = rng.randint(*_POSITIONS[seniority])
    count = max(1, min(count, total // 8))
    cuts = sorted(rng.sample(range(8, total - 7), count - 1)) if count > 1 and total > 16 else []
    lengths = [b - a for a, b in zip([0, *cuts], [*cuts, total], strict=True)]
    current = rng.random() < 0.8
    end: YearMonth = (REFERENCE_DATE.year, REFERENCE_DATE.month)
    if not current:
        end = _add_months(end, -rng.randint(1, 8))
    roles: list[tuple[YearMonth, YearMonth, bool]] = []
    for index, length in enumerate(lengths):
        start = _add_months(end, -(length - 1))
        roles.append((start, end, index == 0 and current))
        end = _add_months(start, -1 - (rng.randint(0, 3) if rng.random() < 0.3 else 0))
    return roles


def _origin(language: str, rng: random.Random) -> str:
    if language == "ru":
        return "ru" if rng.random() < 0.85 else "world-3"  # Central Asian names in Russian CVs
    roll = rng.random()
    if roll < 0.35:
        return "ru"
    if roll < 0.65:
        return "en"
    return f"world-{rng.randrange(len(names.WORLD))}"


def person_name(origin: str, gender: str, language: str, rng: random.Random) -> tuple[str, str]:
    if origin == "ru":
        first = rng.choice(names.RU_FEMALE if gender == "f" else names.RU_MALE)
        last = rng.choice(names.RU_SURNAMES)
        if gender == "f":
            last = names.feminine_surname(last)
        return (first, last) if language == "ru" else (translit(first), translit(last))
    if origin == "en":
        return rng.choice(names.EN_FEMALE if gender == "f" else names.EN_MALE), rng.choice(names.EN_SURNAMES)
    males, females, surnames = names.WORLD[int(origin.split("-")[1])]
    return rng.choice(females if gender == "f" else males), rng.choice(surnames)


def _languages(language: str, origin: str, seniority: str, rng: random.Random) -> tuple[dict[str, int], bool]:
    english = rng.choices([2, 3, 4, 5, 6], weights=[10, 28, 34, 22, 6])[0]
    if seniority == "senior":
        english = min(6, english + rng.choice([0, 0, 1]))
    levels: dict[str, int] = {}
    inferred = False
    if language == "ru":
        if rng.random() < 0.6:
            levels["ru"] = 7
        else:
            inferred = True
        levels["en"] = english
    else:
        levels["en"] = 7 if origin == "en" else english
        if origin == "ru":
            levels["ru"] = 7
        elif origin == "world-0":
            levels["ar"] = 7
        elif origin == "world-1":
            levels["zh"] = 7
        elif origin == "world-3":
            levels["ru"] = rng.choice([4, 5, 6])
    if rng.random() < 0.2:
        extra = rng.choice(["de", "fr", "es", "tr"])
        levels.setdefault(extra, rng.choice([1, 2, 3]))
    return levels, inferred


def make_candidate(index: int, archetype: Archetype, seniority: str, rng: random.Random) -> TruthCandidate:
    language = "ru" if rng.random() < 0.55 else "en"
    gender = rng.choice("fm")
    origin = _origin(language, rng)
    first, last = person_name(origin, gender, language, rng)
    used, listed_only = _skill_set(archetype, rng)
    roles = _career(seniority, rng)
    level_index = SENIORITY.index(seniority)
    titles = archetype.titles_ru if language == "ru" else archetype.titles_en
    companies = names.RU_COMPANIES if language == "ru" else names.EN_COMPANIES
    positions: list[TruthPosition] = []
    core_members = {s for c in archetype.core for s in (c if isinstance(c, tuple) else (c,))}
    for role_index, (start, end, current) in enumerate(roles):
        title, title_skills = titles[max(0, level_index - role_index)]
        k = min(len(used), rng.randint(2, 5))
        chosen = rng.sample(used, k)
        for skill in [s for s in used if s in core_members]:
            if skill not in chosen and rng.random() < 0.6:
                chosen.append(skill)
        positions.append(TruthPosition(title, rng.choice(companies), start, end, current,
                                       sorted(set(chosen) | set(title_skills))))  # fmt: skip
    # every used skill appears in at least one role
    for skill in used:
        if not any(skill in p.skills for p in positions):
            rng.choice(positions).skills.append(skill)
    lead = rng.randint(3, 8) if seniority == "senior" and rng.random() < 0.5 else 0
    if lead:
        positions[0].skills.append("team_lead")
    for position in positions:
        position.skills = sorted(set(position.skills))
    listed = sorted(set(listed_only) | {s for s in used if rng.random() < 0.7})
    if rng.random() < 0.15:  # some CVs have no skills section at all
        listed = [s for s in listed if s not in listed_only]
        listed_only = []
    levels, inferred = _languages(language, origin, seniority, rng)
    degree = rng.choices([0, 1, 2, 3, 4], weights=[10, 8, 42, 36, 4])[0]
    age_at_start = rng.randint(20, 25)
    first_start = positions[-1].start
    birth_year = first_start[0] - age_at_start
    universities = names.RU_UNIVERSITIES if language == "ru" else names.EN_UNIVERSITIES
    if archetype.id == "designer":
        fields_ru, fields_en = ["дизайн", "графический дизайн"], ["Design", "Interaction Design"]
    elif archetype.id in ("product_manager", "data_analyst"):
        fields_ru, fields_en = ["экономика", "бизнес-информатика", "прикладная математика"], [
            "Economics", "Information Systems", "Applied Mathematics"]  # fmt: skip
    else:
        fields_ru = ["прикладная математика", "программная инженерия", "информатика и вычислительная техника"]
        fields_en = ["Computer Science", "Software Engineering", "Applied Mathematics"]
    return TruthCandidate(
        id=f"c{index:04d}", archetype=archetype.id, seniority=seniority, language=language, gender=gender,
        origin=origin, first_name=first, last_name=last,
        birth=date(birth_year, rng.randint(1, 12), rng.randint(1, 28)),
        city=rng.choice(names.RU_CITIES if language == "ru" else names.EN_CITIES),
        positions=positions, listed_skills=listed, languages=levels, native_inferred=inferred,
        degree=degree, university=rng.choice(universities),
        study_field=rng.choice(fields_ru if language == "ru" else fields_en),
        graduation_year=min(first_start[0] + rng.randint(-1, 1), REFERENCE_DATE.year), lead_team=lead,
    )  # fmt: skip


def make_candidates(count: int, seed: int) -> list[TruthCandidate]:
    rng = random.Random(seed)
    out: list[TruthCandidate] = []
    for index in range(count):
        archetype = ARCHETYPES[index % len(ARCHETYPES)]
        seniority = rng.choices(SENIORITY, weights=[30, 40, 30])[0]
        out.append(make_candidate(index + 1, archetype, seniority, rng))
    return out


# ---- vacancies ----

_YEARS = {"junior": (None, 1), "middle": (2, 3), "senior": (4, 5)}


def _vacancy_requirements(archetype: Archetype, seniority: str, rng: random.Random) -> list[Requirement]:
    reqs: list[Requirement] = []

    def add(**kwargs: Any) -> None:
        must = kwargs.pop("must", True)
        reqs.append(
            Requirement(id=f"r{len(reqs) + 1}", text="", must=must, weight=1.0 if must else 0.5, **kwargs)
        )

    singles = [c for c in archetype.core if isinstance(c, str)]
    choices = [c for c in archetype.core if isinstance(c, tuple)]
    if not singles:  # every core skill is a choice (mobile: Kotlin or Swift, Android or iOS)
        singles = [rng.choice(choices[0])]
        choices = choices[1:]
    years = rng.choice(_YEARS[seniority])
    add(kind="skill", skills=[singles[0]], min_years=float(years) if years else None)
    if choices:
        alternatives = list(choices[0])
        rng.shuffle(alternatives)
        add(kind="skill", skills=sorted(alternatives[: max(2, len(alternatives) - 1)]), any_of=True)
    rest = singles[1:]
    if len(rest) >= 2:
        add(kind="skill", skills=rng.sample(rest, 2))
    elif rest:
        add(kind="skill", skills=rest)
    english = archetype.english[SENIORITY.index(seniority)]
    add(kind="language", language="en", min_level=english, must=rng.random() < 0.7)
    if seniority != "junior" and rng.random() < 0.6:
        add(kind="experience", min_years=float((years or 1) + rng.choice([0, 1])))
    if seniority == "senior" and rng.random() < 0.5:
        add(kind="skill", skills=["team_lead"])
    commons = [_resolve(c, rng) for c in rng.sample(archetype.common, 2)]
    for skill in commons:
        add(kind="skill", skills=[skill], must=False)
    if rng.random() < 0.4:
        add(kind="education", min_degree=2, must=False)
    if rng.random() < 0.5:
        add(kind="other", must=False)
    return reqs


def make_vacancies(seed: int) -> list[TruthVacancy]:
    from clearhire.synth.render import render_vacancy

    rng = random.Random(seed + 1)
    vacancies: list[TruthVacancy] = []
    for archetype in ARCHETYPES:
        for seniority in SENIORITY:
            language = "ru" if rng.random() < 0.5 else "en"
            requirements = _vacancy_requirements(archetype, seniority, rng)
            title = (archetype.titles_ru if language == "ru" else archetype.titles_en)[
                SENIORITY.index(seniority)
            ][0]
            company = rng.choice(names.RU_COMPANIES if language == "ru" else names.EN_COMPANIES)
            vacancy = TruthVacancy(f"v{len(vacancies) + 1:02d}", archetype.id, seniority, language, title, company,
                                   "", requirements)  # fmt: skip
            vacancy.text = render_vacancy(vacancy, archetype, rng)
            vacancies.append(vacancy)
    return vacancies


# ---- relevance labels ----


def requirement_met(req: Requirement, candidate: TruthCandidate, taxonomy: Taxonomy) -> bool | None:
    """Whether the candidate meets a requirement, from the truth. None for free-text requirements."""
    if req.kind == "skill":
        have = taxonomy.closure(candidate.explicit_skills())
        months = candidate.skill_months(taxonomy)
        need = round(req.min_years * 12) if req.min_years else 0

        def ok(skill: str) -> bool:
            return skill in have and months.get(skill, 0) >= need

        return any(ok(s) for s in req.skills) if req.any_of else all(ok(s) for s in req.skills)
    if req.kind == "language":
        level = candidate.level(req.language or "")
        return level is not None and level >= (req.min_level or 0)
    if req.kind == "experience":
        return candidate.total_months() >= round((req.min_years or 0) * 12)
    if req.kind == "education":
        return candidate.degree >= (req.min_degree or 2)
    return None


def relevance(vacancy: TruthVacancy, candidate: TruthCandidate, taxonomy: Taxonomy) -> int:
    """3 = meets every must-have and at least half the nice-to-haves; 2 = every must-have;
    1 = at least 60% of the must-haves; 0 = less."""
    must = [requirement_met(r, candidate, taxonomy) for r in vacancy.requirements if r.must]
    nice = [requirement_met(r, candidate, taxonomy) for r in vacancy.requirements if not r.must]
    must_known = [m for m in must if m is not None]
    nice_known = [n for n in nice if n is not None]
    if all(must_known):
        return 3 if nice_known and sum(nice_known) * 2 >= len(nice_known) else 2
    return 1 if sum(must_known) >= 0.6 * len(must_known) else 0


def neighbours(archetype_id: str) -> tuple[str, ...]:
    from clearhire.synth.archetypes import NEIGHBOURS

    return NEIGHBOURS.get(archetype_id, ())


__all__ = [
    "BY_ID",
    "REFERENCE_DATE",
    "TruthCandidate",
    "TruthPosition",
    "TruthVacancy",
    "make_candidates",
    "make_vacancies",
    "neighbours",
    "relevance",
    "requirement_met",
    "translit",
]
