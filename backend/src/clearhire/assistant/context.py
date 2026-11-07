"""What the language model is allowed to see about a candidate, and how its citations are checked.

The model never sees personal details: every piece of CV text it gets goes through the same redaction as
the embedding model (names, contacts, age, gender, family, citizenship replaced by "[label]" tokens, and
Russian past-tense verbs made gender-neutral). Every fact it can use carries a reference: E# for evidence
behind a requirement verdict, P# for a passage found by search, S# for a CV section, R# for a requirement.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from clearhire.embeddings import Embedder
from clearhire.fairness import Span, pii_spans, redact_for_model
from clearhire.matching import IndexedCV, MatchResult, duration
from clearhire.skills import Taxonomy
from clearhire.text import quote_window

STATUS_WORD = {"met": "met", "partial": "partly met", "missing": "not found"}
REF = re.compile(r"\[([EPSRK]\d{1,3})\]")


@dataclass(frozen=True, slots=True)
class Source:
    ref: str
    text: str  # redacted, exactly what the model was shown
    kind: str  # evidence | passage | section | requirement | skill
    section: str = ""
    page: int | None = None
    requirement_id: str | None = None


@dataclass
class Grounding:
    """Everything shown to the model in one task; citations and quotes are checked against it."""

    sources: dict[str, Source] = field(default_factory=dict)
    cv_text: str = ""  # the whole CV, redacted

    def add(self, source: Source) -> Source:
        self.sources.setdefault(source.ref, source)
        return self.sources[source.ref]

    def next_ref(self, prefix: str) -> str:
        return f"{prefix}{sum(r.startswith(prefix) for r in self.sources) + 1}"

    def cited(self, text: str) -> list[Source]:
        return [self.sources[r] for r in dict.fromkeys(REF.findall(text)) if r in self.sources]

    def quote_found(self, quote: str) -> bool:
        """A quoted phrase is genuine when it appears, word for word, in what the model was shown."""
        needle = _norm(quote)
        return bool(needle) and (
            needle in _norm(self.cv_text) or any(needle in _norm(s.text) for s in self.sources.values())
        )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("ё", "е").replace("Ё", "Е")).strip().lower()


@dataclass
class MatchContext:
    """A candidate against a vacancy, as the model sees it."""

    title: str
    language: str
    requirements: list[dict[str, Any]]
    result: MatchResult
    cv: IndexedCV
    spans: list[Span]
    grounding: Grounding

    @classmethod
    def build(cls, title: str, language: str, requirements: list[dict[str, Any]], cv: IndexedCV,
              result: MatchResult) -> MatchContext:  # fmt: skip
        spans = pii_spans(cv.profile)
        text = cv.profile.text
        context = cls(title, language, requirements, result, cv, spans,
                      Grounding(cv_text=redact_for_model(text, (0, len(text)), spans)))  # fmt: skip
        by_id = {r["id"]: r for r in requirements}
        for number, item in enumerate(result.results, start=1):
            req = by_id.get(item.requirement_id, {})
            context.grounding.add(Source(f"R{number}", req.get("text", item.requirement_id), "requirement",
                                         requirement_id=item.requirement_id))  # fmt: skip
            for evidence in item.evidence:
                if evidence.source == "inferred":
                    continue
                window = quote_window(text, *evidence.span)
                context.grounding.add(Source(context.grounding.next_ref("E"), redact_for_model(text, window, spans),
                                             "evidence", evidence.section, evidence.page, item.requirement_id))  # fmt: skip
        return context

    def requirement_ref(self, requirement_id: str) -> str:
        return next(
            s.ref
            for s in self.grounding.sources.values()
            if s.kind == "requirement" and s.requirement_id == requirement_id
        )

    def overview(self, *, with_evidence: bool = True) -> str:
        """The match as text: one block per requirement, with its verdict, the matcher's reason and the
        evidence quotes."""
        by_id = {r["id"]: r for r in self.requirements}
        lines = [f"Vacancy: {self.title}",
                 f"Experience read from the CV: {duration(self.cv.profile.total_months) or 'none'}",
                 f"Must-haves fully met: {self.result.must_met} of {self.result.must_total}", ""]  # fmt: skip
        for item in self.result.results:
            req = by_id.get(item.requirement_id, {})
            kind = "must-have" if req.get("must", True) else "nice to have"
            ref = self.requirement_ref(item.requirement_id)
            lines.append(f"[{ref}] ({kind}) {req.get('text', '')}: {STATUS_WORD[item.status]}. {item.detail}")
            if with_evidence:
                for source in self.grounding.sources.values():
                    if source.kind == "evidence" and source.requirement_id == item.requirement_id:
                        lines.append(f"    [{source.ref}] «{source.text}» ({source.section})")
        return "\n".join(lines)

    def search(self, embedder: Embedder, query: str, limit: int = 4) -> list[Source]:
        """CV passages closest in meaning to the query (the embeddings never saw personal details)."""
        cv = self.cv
        if not query.strip() or not len(cv.chunks):
            return []
        vector = embedder.embed_queries([query])[0]
        scores = cv.vectors @ vector
        found = []
        for index in np.argsort(-scores)[:limit]:
            chunk = cv.chunks[int(index)]
            text = redact_for_model(cv.profile.text, chunk.span, self.spans)
            existing = next(
                (s for s in self.grounding.sources.values() if s.kind == "passage" and s.text == text), None
            )
            found.append(existing or self.grounding.add(Source(self.grounding.next_ref("P"), text, "passage",
                                                               chunk.section, cv.page_of(chunk.span[0]))))  # fmt: skip
        return found

    def skill_lookup(self, taxonomy: Taxonomy, text: str) -> list[Source]:
        """What the deterministic skill matcher read about every skill named in `text`: where the CV names it
        (with quotes), the months of dated roles that use it, or that no alias of it appears anywhere."""
        cv_text = self.cv.profile.text
        found: list[Source] = []
        for skill_id in dict.fromkeys(m.skill_id for m in taxonomy.find(text)):
            name = taxonomy.name(skill_id)
            existing = next(
                (
                    s
                    for s in self.grounding.sources.values()
                    if s.kind == "skill" and s.requirement_id == skill_id
                ),
                None,
            )
            if existing:
                found.append(existing)
                continue
            evidence = self.cv.profile.skills.get(skill_id)
            if evidence is None:
                fact = f"{name}: not named anywhere in the CV, under any of its names, and not implied by another skill."
                quotes: list[str] = []
            else:
                months = f"; {duration(evidence.months)} in dated roles" if evidence.months else ""
                how = (
                    f"named {len(evidence.mentions)} time(s)"
                    if evidence.explicit
                    else f"not named, but implied by {', '.join(taxonomy.name(i) for i in evidence.implied_by)}"
                )
                fact = f"{name}: {how}{months}."
                quotes = [
                    redact_for_model(cv_text, quote_window(cv_text, m.start, m.end), self.spans)
                    for m in evidence.mentions[:2]
                ]
            body = fact + "".join(f"\n  «{q}»" for q in quotes)
            found.append(
                self.grounding.add(
                    Source(self.grounding.next_ref("K"), body, "skill", "skills", None, skill_id)
                )
            )
        return found

    def sections(self) -> list[str]:
        return list(
            dict.fromkeys(s.kind for s in self.cv.profile.sections if s.kind not in ("header", "contacts"))
        )

    def section(self, kind: str, limit: int = 1500) -> Source | None:
        parts = [
            s
            for s in self.cv.profile.sections
            if s.kind == kind.strip().lower() and kind not in ("header", "contacts")
        ]
        if not parts:
            return None
        text = "\n".join(redact_for_model(self.cv.profile.text, (s.start, s.end), self.spans) for s in parts)[
            :limit
        ]
        existing = next(
            (s for s in self.grounding.sources.values() if s.kind == "section" and s.section == kind), None
        )
        return existing or self.grounding.add(Source(self.grounding.next_ref("S"), text, "section", kind))


def source_view(source: Source) -> dict[str, Any]:
    return asdict(source)
