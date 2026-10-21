"""FakeLLM: a pretend provider for automated tests. It returns scripted replies and
tool calls in order, and records what it was sent, so tests never need the live model."""
from .base import LLMProvider, LLMResult, Message, ToolSpec

DEFAULT_REPLY = "This is a scripted test reply."


class FakeLLM(LLMProvider):
    def __init__(self, script: list[LLMResult] | None = None):
        self.script = list(script or [])
        self.calls: list[dict] = []  # one entry per generate() call

    def add(self, *results: LLMResult) -> None:
        self.script.extend(results)

    def generate(
        self,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult:
        self.calls.append({"system_prompt": system_prompt, "messages": list(messages), "tools": tools or []})
        if self.script:
            return self.script.pop(0)
        return LLMResult(text=DEFAULT_REPLY)
