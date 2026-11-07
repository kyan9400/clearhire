"""A small client for any OpenAI-compatible chat API: Ollama, vLLM, llama.cpp's server or a hosted one.

Clearhire runs a local model by default (Qwen 3.5 9B on the server's GPU through Ollama), so CV text never
leaves the machine. Only what the assistant needs is implemented: chat with tool calls, no streaming.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


class LLMError(RuntimeError):
    """The model could not be reached or gave an unusable answer."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class Reply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0


Message = dict[str, Any]


class ChatModel(Protocol):
    name: str

    async def chat(
        self, messages: list[Message], *, tools: list[dict[str, Any]] | None = None, max_tokens: int = 700
    ) -> Reply: ...


def tool(name: str, description: str, **params: str) -> dict[str, Any]:
    """A tool definition whose parameters are all required strings, described by `params`."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {key: {"type": "string", "description": text} for key, text in params.items()},
                "required": list(params),
            },
        },
    }


class OpenAIChat:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 120,
        reasoning_effort: str | None = "none",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = model
        self.reasoning_effort = reasoning_effort  # "none" turns Qwen's and similar models' thinking off
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport
        )

    async def chat(
        self, messages: list[Message], *, tools: list[dict[str, Any]] | None = None, max_tokens: int = 700
    ) -> Reply:
        body: dict[str, Any] = {
            "model": self.name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if tools:
            body["tools"] = tools
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        started = time.perf_counter()
        try:
            response = await self._client.post("/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"the language model is unavailable ({type(exc).__name__})") from exc
        calls = []
        for call in message.get("tool_calls") or []:
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                ToolCall(
                    call.get("id", ""),
                    call["function"]["name"],
                    arguments if isinstance(arguments, dict) else {},
                )
            )
        usage = data.get("usage") or {}
        return Reply(content=(message.get("content") or "").strip(), tool_calls=calls,
                     prompt_tokens=int(usage.get("prompt_tokens", 0)), completion_tokens=int(usage.get("completion_tokens", 0)),
                     seconds=time.perf_counter() - started)  # fmt: skip

    async def close(self) -> None:
        await self._client.aclose()
