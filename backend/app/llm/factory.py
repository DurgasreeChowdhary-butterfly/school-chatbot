"""Picks the AI provider named by LLM_PROVIDER in .env."""
import os

from .base import LLMProvider


def get_provider() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    model = os.getenv("MODEL_NAME", "").strip()

    # Imports are inside each branch so only the chosen provider's SDK is loaded.
    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(api_key=os.getenv("GEMINI_API_KEY", "").strip(), model=model)
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(), model=model)

    raise ValueError(f"Unknown LLM_PROVIDER '{name}' in .env. Use 'gemini' or 'anthropic'.")
