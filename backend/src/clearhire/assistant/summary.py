"""A short written summary of a match, where every sentence must point at the evidence it rests on.

The model gets the requirement verdicts and the CV quotes behind them, numbered. It must end each
sentence with references such as [E2] or [R3]. Sentences without a reference to something it was actually
shown are dropped, so a claim the matcher cannot back never reaches the recruiter. If too little
survives, or no model is configured, a plain summary is built from the verdicts instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from clearhire.assistant.context import REF, MatchContext, source_view
from clearhire.assistant.llm import ChatModel, LLMError

LANGUAGE = {"ru": "Russian", "en": "English"}
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[^\s\[])")

SYSTEM = """You are a recruiting assistant. You write for a recruiter about one candidate's match \
against one vacancy. You are given each requirement with the matcher's verdict, and numbered quotes from \
the CV. Personal details are replaced by tokens like [name] or [age]; never guess them.

Write 3 to 5 short sentences in {language}: the overall fit, the strongest evidence, and the gaps that \
matter (must-haves that are missing or only partly met).

Rules:
- Use only the facts given below. Do not add skills, employers or numbers that are not there.
- End every sentence with the references it relies on, for example [E2] or [E1][E4]. A sentence about a \
missing or partly met requirement cites that requirement, for example [R3].
- Do not recommend hiring or rejecting the candidate: a person decides.
- Never mention age, gender, family, health, religion, ethnicity or nationality.
- Plain sentences only: no headings, no lists, no preamble."""


@dataclass
class Sentence:
    text: str
    refs: list[str]


@dataclass
class Summary:
    sentences: list[Sentence]
    sources: list[dict[str, Any]]
    model: str
    dropped: int = 0  # sentences removed for citing nothing the model was shown
    seconds: float = 0.0
    tokens: int = 0
    notes: list[str] = field(default_factory=list)


def split_cited(text: str, valid: set[str]) -> tuple[list[Sentence], int]:
    """Sentences with their references; those that cite nothing valid are counted and dropped."""
    kept, dropped = [], 0
    for raw in _SENTENCE_END.split(text.strip()):
        raw = raw.strip().lstrip("-•* ").strip()
        if not raw:
            continue
        refs = [r for r in dict.fromkeys(REF.findall(raw)) if r in valid]
        clean = re.sub(r"\s*\[[A-Z]\d{1,3}\]", "", raw).strip()
        clean = re.sub(r"\s+([.!?,;:])", r"\1", clean)
        if refs and len(clean) > 3:
            kept.append(Sentence(clean, refs))
        else:
            dropped += 1
    return kept, dropped


def rule_summary(context: MatchContext) -> Summary:
    """Without a model: the same facts, stated plainly."""
    result, by_id = context.result, {r["id"]: r for r in context.requirements}
    ru = context.language == "ru"
    must = [r for r in result.results if by_id.get(r.requirement_id, {}).get("must", True)]
    met = [r for r in must if r.status == "met"]
    gaps = [r for r in must if r.status != "met"]
    sentences = []
    if met:
        lead = "Выполнено обязательных требований" if ru else "Must-haves met"
        sentences.append(
            Sentence(
                f"{lead}: {len(met)} / {len(must)}.", [context.requirement_ref(r.requirement_id) for r in met]
            )
        )
    for item in gaps:
        text = by_id[item.requirement_id]["text"]
        word = (
            ("не найдено" if item.status == "missing" else "частично")
            if ru
            else ("not found" if item.status == "missing" else "partly met")
        )
        sentences.append(
            Sentence(f"{text}: {word}. {item.detail}", [context.requirement_ref(item.requirement_id)])
        )
    used = {r for s in sentences for r in s.refs}
    return Summary(
        sentences, [source_view(s) for s in context.grounding.sources.values() if s.ref in used], "rules"
    )


async def summarize(context: MatchContext, model: ChatModel | None) -> Summary:
    if model is None:
        return rule_summary(context)
    messages = [
        {"role": "system", "content": SYSTEM.format(language=LANGUAGE.get(context.language, "English"))},
        {"role": "user", "content": context.overview()},
    ]
    try:
        reply = await model.chat(messages, max_tokens=450)
    except LLMError:
        fallback = rule_summary(context)
        fallback.notes.append("the language model was unavailable")
        return fallback
    sentences, dropped = split_cited(reply.content, set(context.grounding.sources))
    if len(sentences) < 2:
        fallback = rule_summary(context)
        fallback.notes.append(f"the model's summary cited too little ({len(sentences)} grounded sentences)")
        fallback.dropped = dropped
        return fallback
    used = {r for s in sentences for r in s.refs}
    return Summary(sentences, [source_view(s) for s in context.grounding.sources.values() if s.ref in used], model.name,
                   dropped, reply.seconds, reply.prompt_tokens + reply.completion_tokens)  # fmt: skip
