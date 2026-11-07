"""Answering a recruiter's question about one candidate, with tools and checked citations.

The model starts from the match overview (requirements and verdicts, no quotes) and can call three tools:
search the CV by meaning, open a requirement's evidence, or read a CV section. Every result it gets has a
reference (P#, E#, S#), and its answer must cite them. Afterwards the answer is checked: references must
point at something the model was really shown, and every phrase it puts in «guillemets» must appear word
for word in the CV. The recruiter sees the answer, the sources, each tool call, and whether the checks
passed. Questions about protected traits are refused before the model is called.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from clearhire.assistant.context import REF, MatchContext, source_view
from clearhire.assistant.guard import REFUSAL, language_of, protected_topic
from clearhire.assistant.llm import ChatModel, LLMError, Message, ToolCall, tool
from clearhire.embeddings import Embedder

MAX_ROUNDS = 4
_QUOTE = re.compile(r"«([^»]{3,300})»|\"([^\"]{3,300})\"")

SYSTEM = """You are a recruiting assistant answering a recruiter's question about one candidate for one \
vacancy. Below is the match overview: each requirement [R#] with the matcher's verdict.

Read the CV through the tools before answering anything the overview does not settle:
- search_cv: passages closest in meaning to a query; returns [P#] passages
- requirement_evidence: the CV quotes behind one requirement's verdict; returns [E#] quotes
- read_section: one CV section (experience, skills, education, languages, summary, projects...); returns [S#]

Rules:
- Answer in the language of the question, in 2 to 6 sentences.
- Every factual sentence ends with the references it relies on, for example [P2] or [E1][R3].
- When you quote the CV, copy the words exactly and put them in «guillemets».
- If the CV does not say, answer that it does not say. Do not guess, and do not fill gaps from general knowledge.
- Personal details are replaced by tokens like [name]. Never guess age, gender, family, health, religion, \
ethnicity or nationality, and do not discuss them.
- Do not recommend hiring or rejecting: a person decides.

{overview}"""

TOOLS = [
    tool("search_cv", "Find the CV passages closest in meaning to a query.",
         query="What to look for, e.g. 'Kafka in production' or 'team leadership'"),
    tool("requirement_evidence", "The CV quotes behind one requirement's verdict.",
         requirement="The requirement reference, e.g. R2"),
    tool("read_section", "Read one section of the CV.",
         section="Section name: experience, skills, education, languages, summary, projects, courses or certificates"),
]  # fmt: skip


@dataclass
class Step:
    tool: str
    arguments: dict[str, Any]
    refs: list[str]


@dataclass
class Answer:
    text: str
    sources: list[dict[str, Any]]
    steps: list[Step] = field(default_factory=list)
    model: str = ""
    refused: str | None = None  # the protected topic, when the question was refused
    grounded: bool = True  # every sentence cites something the model was shown
    quotes: list[dict[str, Any]] = field(default_factory=list)  # each «quote» and whether the CV contains it
    seconds: float = 0.0
    tokens: int = 0


def _run(context: MatchContext, embedder: Embedder, call: ToolCall) -> tuple[str, list[str]]:
    args = call.arguments
    if call.name == "search_cv":
        found = context.search(embedder, str(args.get("query", "")))
        if not found:
            return "No passages found.", []
        return "\n".join(f"[{s.ref}] ({s.section}) {s.text}" for s in found), [s.ref for s in found]
    if call.name == "requirement_evidence":
        ref = str(args.get("requirement", "")).strip().strip("[]").upper()
        requirement = context.grounding.sources.get(ref)
        if requirement is None or requirement.kind != "requirement":
            return f"Unknown requirement {ref!r}. Use one of the [R#] references in the overview.", []
        quotes = [s for s in context.grounding.sources.values()
                  if s.kind == "evidence" and s.requirement_id == requirement.requirement_id]  # fmt: skip
        if not quotes:
            return f"[{ref}] has no supporting quotes in the CV.", [ref]
        return "\n".join(f"[{s.ref}] ({s.section}) «{s.text}»" for s in quotes), [s.ref for s in quotes]
    if call.name == "read_section":
        source = context.section(str(args.get("section", "")))
        if source is None:
            return f"No such section. The CV has: {', '.join(context.sections()) or 'no sections'}.", []
        return f"[{source.ref}] {source.text}", [source.ref]
    return f"Unknown tool {call.name!r}.", []


def check(text: str, context: MatchContext) -> tuple[bool, list[dict[str, Any]]]:
    """Every sentence with a claim must cite a real source; every «quote» must be in the CV."""
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if len(s) > 3]
    valid = set(context.grounding.sources)
    says_nothing = re.compile(
        r"\b(?:does not|doesn't|no mention|not mention|not say|нет\s+упоминан|не\s+указ|не\s+упомина|не\s+говорит|нет\s+данных)",
        re.I,
    )
    grounded = all(any(r in valid for r in REF.findall(s)) or says_nothing.search(s) for s in sentences)
    quotes = [
        {"text": q, "found": context.grounding.quote_found(q)}
        for pair in _QUOTE.findall(text)
        for q in pair
        if q
    ]
    return grounded and all(q["found"] for q in quotes), quotes


async def ask(context: MatchContext, question: str, model: ChatModel, embedder: Embedder) -> Answer:
    language = language_of(question)
    topic = protected_topic(question)
    if topic:
        return Answer(REFUSAL[language], [], model=model.name, refused=topic)

    started = time.perf_counter()
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM.format(overview=context.overview(with_evidence=False))},
        {"role": "user", "content": question},
    ]
    steps: list[Step] = []
    tokens = 0
    reply = None
    for round_ in range(MAX_ROUNDS + 1):
        final = round_ == MAX_ROUNDS  # out of tool rounds: the model must answer with what it has
        reply = await model.chat(messages, tools=None if final else TOOLS)
        tokens += reply.prompt_tokens + reply.completion_tokens
        if not reply.tool_calls or final:
            break
        messages.append({"role": "assistant", "content": reply.content or "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": _json(c.arguments)}}
            for c in reply.tool_calls
        ]})  # fmt: skip
        for call in reply.tool_calls:
            result, refs = _run(context, embedder, call)
            steps.append(Step(call.name, call.arguments, refs))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    assert reply is not None
    text = reply.content.strip()
    if not text:
        raise LLMError("the model gave an empty answer")
    grounded, quotes = check(text, context)
    used = context.grounding.cited(text)
    return Answer(text, [source_view(s) for s in used], steps, model.name, None, grounded, quotes,
                  time.perf_counter() - started, tokens)  # fmt: skip


def _json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
