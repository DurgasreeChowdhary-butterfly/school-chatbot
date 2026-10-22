"""Picks the AI provider named by LLM_PROVIDER in .env."""
import os

from .base import LLMProvider


def get_provider(model_name: str | None = None) -> LLMProvider:
    """model_name overrides MODEL_NAME (used by scripts/compare_models.py)."""
    name = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    model = model_name or os.getenv("MODEL_NAME", "").strip()
    # Empty = the model's own default temperature (what Google recommends for Gemini 3).
    temperature = os.getenv("LLM_TEMPERATURE", "").strip()

    # Imports are inside each branch so only the chosen provider's SDK is loaded.
    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(api_key=os.getenv("GEMINI_API_KEY", "").strip(), model=model,
                              temperature=float(temperature) if temperature else None)
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(), model=model)
    if name == "fake":
        from .fake_provider import FakeLLM
        return FakeLLM()

    raise ValueError(f"Unknown LLM_PROVIDER '{name}' in .env. Use 'gemini', 'anthropic' or 'fake'.")
