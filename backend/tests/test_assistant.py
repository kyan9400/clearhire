"""The AI assistant with a scripted model: what it is shown, how its citations are checked, what it refuses."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from clearhire.assistant import MatchContext, ask, summarize
from clearhire.assistant.agent import check
from clearhire.assistant.guard import language_of, protected_topic
from clearhire.assistant.llm import LLMError, Message, OpenAIChat, Reply, ToolCall
from clearhire.assistant.summary import split_cited
from clearhire.cv.profile import extract_profile
from clearhire.embeddings import HashEmbedder
from clearhire.matching import index_cv, match, prepare_vacancy
from clearhire.skills import Taxonomy
from clearhire.vacancy import parse_requirements, vacancy_query_text
from conftest import RUSSIAN_CV, TODAY, VACANCY

PERSONAL = (
    "Анна",
    "Смирнова",
    "anna.smirnova@example.com",
    "916 123-45-67",
    "@anna_dev",
    "Женщина",
    "29 лет",
    "1997",
)


class Scripted:
    """A fake chat model: returns the prepared replies in order and records every request."""

    name = "scripted"

    def __init__(self, replies: Sequence[Reply | Exception]) -> None:
        self.replies = list(replies)
        self.requests: list[list[Message]] = []
        self.tools: list[Any] = []

    async def chat(self, messages: list[Message], *, tools: list[dict[str, Any]] | None = None, max_tokens: int = 700) -> Reply:  # fmt: skip
        self.requests.append([dict(m) for m in messages])
        self.tools.append(tools)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def seen(self) -> str:
        return json.dumps(self.requests, ensure_ascii=False)


@pytest.fixture
def context(taxonomy: Taxonomy, embedder: HashEmbedder) -> MatchContext:
    requirements = parse_requirements(VACANCY, taxonomy)
    profile = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    cv = index_cv(profile, embedder)
    prepared = prepare_vacancy(requirements, vacancy_query_text("Senior Python Developer", VACANCY), embedder)
    result = match(cv, prepared, taxonomy)
    return MatchContext.build(
        "Senior Python Developer", "en", [r.to_dict() for r in requirements], cv, result
    )


def ref_for(context: MatchContext, kind: str, needle: str) -> str:
    return next(s.ref for s in context.grounding.sources.values() if s.kind == kind and needle in s.text)


def test_the_model_never_sees_personal_details(context: MatchContext) -> None:
    shown = context.overview() + context.grounding.cv_text
    for detail in PERSONAL:
        assert detail not in shown, detail
    assert "[name]" in context.grounding.cv_text
    # Russian past tense is made gender-neutral too: "Разработала" would give the gender away
    assert "Разработала" not in shown and "Разработал" in shown


async def test_summary_keeps_only_cited_sentences(context: MatchContext) -> None:
    kafka = ref_for(context, "evidence", "Kafka")
    mentoring = ref_for(context, "evidence", "команд")
    reply = (
        f"The candidate has built Kafka consumers for payments [{kafka}]. "
        f"They led a team of four developers [{mentoring}]. "
        "They are probably a great culture fit. "  # no reference: dropped
        "They also know Rust [E99]."  # a reference to nothing the model was shown: dropped
    )
    model = Scripted([Reply(reply)])
    summary = await summarize(context, model)
    assert [s.refs for s in summary.sentences] == [[kafka], [mentoring]]
    assert summary.dropped == 2 and summary.model == "scripted"
    assert {s["ref"] for s in summary.sources} == {kafka, mentoring}
    assert all(detail not in model.seen() for detail in PERSONAL)


async def test_summary_falls_back_to_the_verdicts(context: MatchContext) -> None:
    for replies in ([Reply("A strong candidate overall. Recommend hiring.")], [LLMError("down")]):
        summary = await summarize(context, Scripted(replies))
        assert summary.model == "rules" and summary.notes
        assert summary.sentences and all(s.refs for s in summary.sentences)
    offline = await summarize(context, None)
    assert offline.model == "rules" and "Must-haves met" in offline.sentences[0].text


def test_citations_are_split_from_sentences() -> None:
    sentences, dropped = split_cited("Knows Python [E1]. Missing Go [R7]! Nothing here.", {"E1", "R7"})
    assert [(s.text, s.refs) for s in sentences] == [("Knows Python.", ["E1"]), ("Missing Go!", ["R7"])]
    assert dropped == 1


async def test_the_agent_searches_then_answers_with_checked_citations(context: MatchContext, embedder: HashEmbedder) -> None:  # fmt: skip
    model = Scripted([
        Reply("", [ToolCall("c1", "search_cv", {"query": "Kafka consumers"})]),
        Reply("", [ToolCall("c2", "read_section", {"section": "skills"})]),
        Reply("PLACEHOLDER"),
    ])  # fmt: skip

    async def answer_once_tools_ran() -> None:
        # the final reply cites the passage the search returned, which only exists after the tool ran
        passage = ref_for(context, "passage", "Kafka")
        model.replies[-1] = Reply(f"Yes: the CV says «Kafka consumers for payments» [{passage}].")

    original = model.chat

    async def chat(messages: list[Message], **kwargs: Any) -> Reply:
        if len(model.replies) == 1:
            await answer_once_tools_ran()
        return await original(messages, **kwargs)

    model.chat = chat  # type: ignore[method-assign]
    answer = await ask(context, "Has the candidate worked with Kafka?", model, embedder)
    assert [s.tool for s in answer.steps] == ["search_cv", "read_section"]
    assert answer.grounded and answer.quotes == [{"text": "Kafka consumers for payments", "found": True}]
    assert answer.sources and answer.sources[0]["kind"] == "passage"
    tool_results = [m["content"] for m in model.requests[-1] if m["role"] == "tool"]
    assert "Kafka" in tool_results[0] and "Python, SQL, Docker, Kubernetes" in tool_results[1]
    assert model.tools[0] and model.tools[-1]  # tools offered on every round that may use them
    assert all(detail not in model.seen() for detail in PERSONAL)


async def test_invented_quotes_and_uncited_claims_are_flagged(
    context: MatchContext, embedder: HashEmbedder
) -> None:
    model = Scripted([Reply("The CV says «managed a Kubernetes cluster of 500 nodes» [R1]. She is great.")])
    answer = await ask(context, "Tell me about infrastructure", model, embedder)
    assert answer.grounded is False
    assert answer.quotes == [{"text": "managed a Kubernetes cluster of 500 nodes", "found": False}]
    honest, _ = check("The CV does not mention Go.", context)
    assert honest


async def test_the_agent_stops_calling_tools_after_four_rounds(
    context: MatchContext, embedder: HashEmbedder
) -> None:
    looping = [Reply("", [ToolCall(f"c{i}", "search_cv", {"query": "python"})]) for i in range(4)]
    model = Scripted([*looping, Reply("It does not say [R1].")])
    answer = await ask(context, "What about Python?", model, embedder)
    assert len(answer.steps) == 4 and model.tools[-1] is None


@pytest.mark.parametrize(
    "question",
    ["How old is she?", "Is the candidate married or planning kids?", "Сколько ему лет?", "Она беременна?",
     "What is his nationality?", "Есть ли у кандидата дети?", "Any health conditions?"],
)  # fmt: skip
async def test_protected_questions_are_refused_without_the_model(context: MatchContext, embedder: HashEmbedder, question: str) -> None:  # fmt: skip
    model = Scripted([])
    answer = await ask(context, question, model, embedder)
    assert answer.refused and not model.requests
    assert ("Возраст" in answer.text) == (language_of(question) == "ru")


@pytest.mark.parametrize(
    "question",
    ["Has she debugged race conditions?", "Any healthcare domain experience?", "Did he manage a team?",
     "Клиентоориентированность есть?", "Опыт в старших позициях?", "What packages has the candidate used?"],
)  # fmt: skip
def test_fair_questions_are_not_refused(question: str) -> None:
    assert protected_topic(question) is None


async def test_the_http_client_speaks_the_openai_format() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={
            "choices": [{"message": {"content": None, "tool_calls": [
                {"id": "x", "type": "function", "function": {"name": "search_cv", "arguments": "{\"query\": \"Go\"}"}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        })  # fmt: skip

    model = OpenAIChat("http://llm/v1/", "qwen3.5:9b", api_key="k", transport=httpx.MockTransport(handler))
    reply = await model.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert reply.tool_calls == [ToolCall("x", "search_cv", {"query": "Go"})] and reply.content == ""
    assert seen["model"] == "qwen3.5:9b" and seen["reasoning_effort"] == "none" and seen["auth"] == "Bearer k"
    broken = OpenAIChat("http://llm/v1", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(LLMError):
        await broken.chat([{"role": "user", "content": "hi"}])
