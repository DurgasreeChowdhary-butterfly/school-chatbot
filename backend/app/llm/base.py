"""Neutral AI provider interface. The rest of the app only talks to these classes,
so the provider (Gemini, Claude, ...) can be swapped without changing other code."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    """A tool the AI may ask us to run (for example: save an enquiry).
    parameters is a JSON Schema describing the tool's inputs."""
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    """The AI asking us to run a tool with these arguments."""
    name: str
    arguments: dict
    id: str | None = None


@dataclass
class Message:
    """One message in the conversation.
    role is "user", "assistant" or "tool".
    - assistant messages may carry tool_calls (the AI asked us to run tools)
    - tool messages carry the result of one tool call (tool_call_id and name say which)
    provider_data is an opaque value a provider may attach and read back later
    (for example Gemini's raw reply, which must be sent back unchanged). Other code ignores it."""
    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    provider_data: Any = None


@dataclass
class LLMResult:
    """What every provider returns. failed=True means the provider errored,
    timed out, was rate limited or blocked the answer; error says why (for logs only)."""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    failed: bool = False
    error: str | None = None
    provider_data: Any = None


class LLMProvider(ABC):
    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult:
        """Send the rules and the conversation, get back the AI's reply."""
