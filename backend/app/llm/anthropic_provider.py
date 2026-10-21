"""Anthropic Claude provider: not built yet. This is the switch point.
To add it: install the anthropic SDK, import it only in this file, and fill in generate()."""
from .base import LLMProvider, LLMResult, Message, ToolSpec


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    def generate(
        self,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult:
        raise NotImplementedError(
            "Anthropic provider is not implemented yet. Set LLM_PROVIDER=gemini in .env."
        )
