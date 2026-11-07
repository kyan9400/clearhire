"""The AI assistant: grounded match summaries and answers to recruiters' questions, from a local LLM.

Everything the model reads is redacted (no personal details), everything it says must cite what it read,
and every call is written to the audit log.
"""

from clearhire.assistant.agent import Answer, ask
from clearhire.assistant.context import MatchContext
from clearhire.assistant.llm import ChatModel, LLMError, OpenAIChat
from clearhire.assistant.summary import Summary, summarize

__all__ = ["Answer", "ChatModel", "LLMError", "MatchContext", "OpenAIChat", "Summary", "ask", "summarize"]
