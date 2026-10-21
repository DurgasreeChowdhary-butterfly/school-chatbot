"""Google Gemini provider, using the official Google Gen AI SDK (package: google-genai).
This is the only file that imports the Gemini SDK."""
from google import genai
from google.genai import errors, types

from .base import LLMProvider, LLMResult, Message, ToolCall, ToolSpec


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, timeout_seconds: int = 30):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is empty in .env")
        if not model:
            raise ValueError("MODEL_NAME is empty in .env")
        # HttpOptions.timeout is in milliseconds.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_seconds * 1000),
        )
        self._model = model

    def generate(
        self,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult:
        # Gemini calls the assistant role "model".
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part.from_text(text=m.content)],
            )
            for m in messages
        ]
        gemini_tools = None
        if tools:
            gemini_tools = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=t.parameters,
                        )
                        for t in tools
                    ]
                )
            ]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=gemini_tools,
        )

        try:
            response = self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )
        except errors.APIError as e:
            # Includes 429 (rate limited) and 5xx (server problems).
            return LLMResult(failed=True, error=f"Gemini API error {e.code}: {e.message}")
        except Exception as e:  # timeouts, network errors
            return LLMResult(failed=True, error=f"Gemini request failed: {e!r}")

        feedback = response.prompt_feedback
        if feedback and feedback.block_reason:
            return LLMResult(failed=True, error=f"Gemini blocked the prompt: {feedback.block_reason}")

        tool_calls = [
            ToolCall(name=fc.name, arguments=dict(fc.args or {}), id=fc.id)
            for fc in (response.function_calls or [])
        ]
        text = (response.text or "").strip()
        if not text and not tool_calls:
            reason = response.candidates[0].finish_reason if response.candidates else "no candidates"
            return LLMResult(failed=True, error=f"Gemini returned no answer (finish reason: {reason})")

        return LLMResult(text=text, tool_calls=tool_calls)
