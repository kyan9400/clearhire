"""Requirement-level matching: for each vacancy requirement, met / partial / missing, with CV evidence.

A candidate's rank comes from the requirements, not from one similarity number:
  1. fewer unmet must-haves first,
  2. then the weighted requirement score (met = 1, partial = 0.5),
  3. then semantic similarity between the vacancy and the CV, as a tie-breaker.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from clearhire.cv.languages import NAMES, level_name
from clearhire.cv.profile import DEGREE_NAMES, CandidateProfile
from clearhire.embeddings import Embedder, Vectors
from clearhire.fairness import pii_spans, redact_for_model
from clearhire.skills import Mention, Taxonomy
from clearhire.text import quote
from clearhire.vacancy import Requirement

STATUS_SCORE = {"met": 1.0, "partial": 0.5, "missing": 0.0}
# cosine thresholds for free-text requirements with multilingual-e5-small (see eval/)
SEMANTIC_MET = 0.85
SEMANTIC_PARTIAL = 0.81
CHUNK_WORDS = 80


@dataclass(frozen=True, slots=True)
class Evidence:
    quote: str
    highlight: tuple[int, int]  # the supporting words inside `quote`
    span: tuple[int, int]  # the supporting words in the CV text
    page: int | None
    section: str
    source: str  # skill | implied | dates | language | education | semantic | inferred


@dataclass(slots=True)
class RequirementResult:
    requirement_id: str
    status: str  # met | partial | missing
    detail: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class MatchResult:
    score: float
    must_have_gaps: int
    semantic: float
    results: list[RequirementResult]

    def rank_key(self) -> tuple[int, float, float]:
        return (self.must_have_gaps, -round(self.score, 6), -self.semantic)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    span: tuple[int, int]
    section: str


@dataclass(slots=True)
class IndexedCV:
    """A parsed CV ready for matching: its profile, passages and their embeddings."""

    profile: CandidateProfile
    chunks: list[Chunk]
    vectors: Vectors
    page_of: Callable[[int], int | None]


def duration(months: int) -> str:
    years, rest = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if rest or not years:
        parts.append(f"{rest} month{'s' if rest != 1 else ''}")
    return " ".join(parts)


def chunk_profile(profile: CandidateProfile, max_words: int = CHUNK_WORDS) -> list[Chunk]:
    """Passages for semantic matching: each position, and the summary, skills, projects and similar
    sections, cut to about `max_words` words. The header (name, contacts) is left out."""
    text = profile.text
    regions: list[tuple[int, int, str]] = [(p.span[0], p.span[1], "experience") for p in profile.positions]
    covered = [(p.span[0], p.span[1]) for p in profile.positions]
    for section in profile.sections:
        if section.kind in ("header", "contacts", "other"):
            continue
        if any(start <= section.start and section.end <= end for start, end in covered):
            continue
        if section.kind == "experience" and profile.positions:
            continue
        regions.append((section.start, section.end, section.kind))
    chunks: list[Chunk] = []
    for start, end, kind in sorted(regions):
        words: list[tuple[int, int]] = []
        offset = start
        for token in text[start:end].split():
            position = text.find(token, offset, end)
            words.append((position, position + len(token)))
            offset = position + len(token)
        for index in range(0, len(words), max_words):
            piece = words[index : index + max_words]
            if len(piece) < 4 and chunks and index:
                continue
            span = (piece[0][0], piece[-1][1])
            chunks.append(Chunk(text[span[0] : span[1]], span, kind))
    return chunks


def index_cv(
    profile: CandidateProfile,
    embedder: Embedder,
    page_of: Callable[[int], int | None] | None = None,
    *,
    blind: bool = True,
) -> IndexedCV:
    """Embed the CV's passages. With `blind`, names, contacts, age, gender and similar details are
    replaced before the model sees the text, so they cannot move the similarity."""
    chunks = chunk_profile(profile)
    spans = pii_spans(profile) if blind else []
    texts = [redact_for_model(profile.text, chunk.span, spans) for chunk in chunks]
    vectors = embedder.embed_passages(texts) if texts else np.zeros((0, embedder.dim), dtype=np.float32)
    return IndexedCV(profile, chunks, vectors, page_of or (lambda _offset: None))


def _evidence(cv: IndexedCV, start: int, end: int, source: str) -> Evidence:
    text, highlight_start, highlight_end = quote(cv.profile.text, start, end)
    return Evidence(text, (highlight_start, highlight_end), (start, end), cv.page_of(start),
                    cv.profile.section_kind(start), source)  # fmt: skip


def _best_mentions(cv: IndexedCV, mentions: list[Mention], limit: int = 2) -> list[Mention]:
    """Mentions in dated roles first (they show use, not just a keyword), then the rest, in CV order."""
    in_roles = [m for m in mentions if cv.profile.position_at(m.start) is not None]
    others = [m for m in mentions if cv.profile.position_at(m.start) is None]
    chosen: list[Mention] = []
    seen_lines: set[int] = set()
    for mention in in_roles + others:
        line = cv.profile.text.rfind("\n", 0, mention.start)
        if line in seen_lines:
            continue
        seen_lines.add(line)
        chosen.append(mention)
        if len(chosen) == limit:
            break
    return chosen


def _skill_status(cv: IndexedCV, skill_id: str, min_months: int | None, taxonomy: Taxonomy) -> tuple[str, str, list[Evidence]]:  # fmt: skip
    name = taxonomy.name(skill_id)
    evidence = cv.profile.skills.get(skill_id)
    if evidence is None:
        return "missing", f"{name}: not found", []
    if evidence.explicit:
        items = [_evidence(cv, m.start, m.end, "skill") for m in _best_mentions(cv, evidence.mentions)]
        how = "named in the CV"
    else:
        sources = [cv.profile.skills[s] for s in evidence.implied_by if s in cv.profile.skills]
        mentions = [m for s in sources for m in s.mentions]
        items = [_evidence(cv, m.start, m.end, "implied") for m in _best_mentions(cv, mentions, 1)]
        how = "implied by " + ", ".join(taxonomy.name(s) for s in evidence.implied_by[:3])
    if min_months is None:
        if evidence.months:
            return "met", f"{name}: {duration(evidence.months)} in dated roles", items
        return "met", f"{name}: {how}", items
    need = duration(min_months)
    if evidence.months >= min_months:
        return "met", f"{name}: {duration(evidence.months)} in dated roles ({need} required)", items
    if evidence.months == 0:
        return "partial", f"{name}: {how}, but no dated role shows it ({need} required)", items
    if evidence.months * 2 >= min_months:
        return "partial", f"{name}: {duration(evidence.months)} shown, {need} required", items
    return "missing", f"{name}: only {duration(evidence.months)} shown, {need} required", items


def _match_skill(cv: IndexedCV, req: Requirement, taxonomy: Taxonomy) -> RequirementResult:
    min_months = round(req.min_years * 12) if req.min_years else None
    outcomes = [(skill, *_skill_status(cv, skill, min_months, taxonomy)) for skill in req.skills]
    order = {"met": 0, "partial": 1, "missing": 2}
    if req.any_of:
        best = min(outcomes, key=lambda o: order[o[1]])
        status = best[1]
        detail = best[2] if status != "missing" else (
            "None of " + ", ".join(taxonomy.name(s) for s in req.skills) + " found"
        )  # fmt: skip
        return RequirementResult(req.id, status, detail, best[3])
    worst = max(outcomes, key=lambda o: order[o[1]])[1]
    status = worst
    if worst == "missing" and any(o[1] != "missing" for o in outcomes):
        status = "partial"  # some of the skills are there
    detail = "; ".join(o[2] for o in outcomes)
    evidence = [item for o in outcomes for item in o[3]][:4]
    return RequirementResult(req.id, status, detail, evidence)


def _match_language(cv: IndexedCV, req: Requirement) -> RequirementResult:
    code = req.language or ""
    need = level_name(req.min_level)
    have = cv.profile.languages.get(code)
    name = NAMES.get(code, code)
    if have is None:
        return RequirementResult(req.id, "missing", f"{name}: not mentioned ({need} required)")
    if have.inferred or have.span is None:
        evidence = [Evidence(f"The CV is written in {name}.", (0, 0), (0, 0), None, "header", "inferred")]
    else:
        evidence = [_evidence(cv, have.span[0], have.span[1], "language")]
    if have.level is None:
        return RequirementResult(req.id, "partial", f"{name}: level not stated ({need} required)", evidence)
    detail = f"{name}: {level_name(have.level)} ({need} required)"
    if req.min_level is None or have.level >= req.min_level:
        return RequirementResult(req.id, "met", detail, evidence)
    status = "partial" if have.level == req.min_level - 1 else "missing"
    return RequirementResult(req.id, status, detail, evidence)


def _match_experience(cv: IndexedCV, req: Requirement) -> RequirementResult:
    need = round((req.min_years or 0) * 12)
    have = cv.profile.total_months
    evidence = [_evidence(cv, p.dates_span[0], p.dates_span[1], "dates") for p in cv.profile.positions[:2]]
    detail = f"{duration(have)} of dated experience ({duration(need)} required)"
    if have >= need:
        return RequirementResult(req.id, "met", detail, evidence)
    return RequirementResult(req.id, "partial" if have * 4 >= need * 3 else "missing", detail, evidence)


def _match_education(cv: IndexedCV, req: Requirement) -> RequirementResult:
    education = cv.profile.education
    need = DEGREE_NAMES.get(req.min_degree or 2, "higher")
    if education is None or education.degree == 0:
        return RequirementResult(req.id, "missing", f"Education: not stated ({need} required)")
    evidence = [_evidence(cv, education.span[0], education.span[1], "education")]
    detail = f"Education: {DEGREE_NAMES[education.degree]} ({need} required)"
    status = "met" if education.degree >= (req.min_degree or 2) else "partial"
    return RequirementResult(req.id, status, detail, evidence)


def _match_semantic(cv: IndexedCV, req: Requirement, query: Vectors) -> RequirementResult:
    if not cv.chunks:
        return RequirementResult(req.id, "missing", "No passage to compare with")
    scores = cv.vectors @ query
    best = int(np.argmax(scores))
    similarity = float(scores[best])
    chunk = cv.chunks[best]
    evidence = [_evidence(cv, chunk.span[0], chunk.span[1], "semantic")]
    detail = f"Closest passage, similarity {similarity:.2f}"
    if similarity >= SEMANTIC_MET:
        return RequirementResult(req.id, "met", detail, evidence)
    if similarity >= SEMANTIC_PARTIAL:
        return RequirementResult(req.id, "partial", detail, evidence)
    return RequirementResult(req.id, "missing", detail, [])


def semantic_similarity(cv: IndexedCV, vacancy_vector: Vectors, top: int = 3) -> float:
    if not cv.chunks:
        return 0.0
    scores = np.sort(cv.vectors @ vacancy_vector)[::-1][:top]
    return float(scores.mean())


@dataclass(slots=True)
class PreparedVacancy:
    """A vacancy's requirements with the embeddings that semantic checks need, computed once."""

    requirements: list[Requirement]
    requirement_vectors: dict[str, Vectors]
    vacancy_vector: Vectors


def prepare_vacancy(requirements: Sequence[Requirement], query_text: str, embedder: Embedder) -> PreparedVacancy:
    free_text = [r for r in requirements if r.kind == "other"]
    vectors = embedder.embed_queries([r.text for r in free_text]) if free_text else []
    return PreparedVacancy(
        list(requirements),
        {r.id: vectors[i] for i, r in enumerate(free_text)},
        embedder.embed_queries([query_text])[0],
    )


def match(cv: IndexedCV, vacancy: PreparedVacancy, taxonomy: Taxonomy) -> MatchResult:
    results: list[RequirementResult] = []
    total = 0.0
    weights = 0.0
    gaps = 0
    for req in vacancy.requirements:
        if req.kind == "skill" and req.skills:
            result = _match_skill(cv, req, taxonomy)
        elif req.kind == "language" and req.language:
            result = _match_language(cv, req)
        elif req.kind == "experience":
            result = _match_experience(cv, req)
        elif req.kind == "education":
            result = _match_education(cv, req)
        elif req.id in vacancy.requirement_vectors:
            result = _match_semantic(cv, req, vacancy.requirement_vectors[req.id])
        else:
            continue
        results.append(result)
        total += req.weight * STATUS_SCORE[result.status]
        weights += req.weight
        if req.must and result.status == "missing":
            gaps += 1
    score = total / weights if weights else 0.0
    return MatchResult(round(score, 4), gaps, round(semantic_similarity(cv, vacancy.vacancy_vector), 4), results)


def rank(cvs: Sequence[IndexedCV], vacancy: PreparedVacancy, taxonomy: Taxonomy) -> list[tuple[int, MatchResult]]:
    """(index into `cvs`, result), best match first."""
    scored = [(index, match(cv, vacancy, taxonomy)) for index, cv in enumerate(cvs)]
    scored.sort(key=lambda item: (item[1].rank_key(), item[0]))
    return scored
