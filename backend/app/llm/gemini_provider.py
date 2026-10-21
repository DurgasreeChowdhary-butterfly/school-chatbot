"""Google Gemini provider, using the official Google Gen AI SDK (package: google-genai).
This is the only file that imports the Gemini SDK."""
import logging
import time

from google import genai
from google.genai import errors, types

from .base import LLMProvider, LLMResult, Message, ToolCall, ToolSpec

log = logging.getLogger("chatbot.gemini")

# Errors worth retrying: rate limited (429) and temporary server trouble.
# Timeouts (504) are not retried, so a visitor never waits minutes for a reply.
RETRY_CODES = {429, 500, 502, 503}
RETRY_DELAYS = [2, 6]  # seconds to wait before the 2nd and 3rd attempt


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
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=_to_gemini_tools(tools),
            # We run tools ourselves, so switch off the SDK's automatic function calling.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = _to_gemini_contents(messages)

        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
                return _to_result(response)
            except errors.APIError as e:
                # A used-up daily quota will not recover in a few seconds, so don't retry it.
                daily_quota = "PerDay" in str(e.details)
                if e.code in RETRY_CODES and not daily_quota and attempt < len(RETRY_DELAYS):
                    log.warning("Gemini error %s, retrying in %ss", e.code, RETRY_DELAYS[attempt])
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                return LLMResult(failed=True, error=f"Gemini API error {e.code}: {e.message}")
            except Exception as e:  # timeouts, network errors
                return LLMResult(failed=True, error=f"Gemini request failed: {e!r}")
        return LLMResult(failed=True, error="Gemini: retries used up")


def _to_gemini_tools(tools: list[ToolSpec] | None):
    if not tools:
        return None
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t.name, description=t.description, parameters_json_schema=t.parameters
                )
                for t in tools
            ]
        )
    ]


def _to_gemini_contents(messages: list[Message]) -> list[types.Content]:
    """Turn neutral messages into Gemini contents. Gemini calls the assistant "model",
    and tool results are sent back as function_response parts in a "user" turn."""
    contents: list[types.Content] = []
    for m in messages:
        if m.role == "tool":
            part = types.Part(
                function_response=types.FunctionResponse(
                    id=m.tool_call_id, name=m.name, response={"result": m.content}
                )
            )
            # Several tool results in a row go into one turn.
            if contents and contents[-1].role == "user" and contents[-1].parts[0].function_response:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
        elif m.role == "assistant":
            if isinstance(m.provider_data, types.Content):
                # Gemini's own reply, sent back unchanged (keeps its thought signatures).
                contents.append(m.provider_data)
                continue
            parts = [types.Part.from_text(text=m.content)] if m.content else []
            parts += [
                types.Part(function_call=types.FunctionCall(id=c.id, name=c.name, args=c.arguments))
                for c in m.tool_calls
            ]
            contents.append(types.Content(role="model", parts=parts))
        else:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m.content)]))
    return contents


def _to_result(response) -> LLMResult:
    feedback = response.prompt_feedback
    if feedback and feedback.block_reason:
        return LLMResult(failed=True, error=f"Gemini blocked the prompt: {feedback.block_reason}")
    if not response.candidates or not response.candidates[0].content:
        reason = response.candidates[0].finish_reason if response.candidates else "no candidates"
        return LLMResult(failed=True, error=f"Gemini returned no answer (finish reason: {reason})")

    content = response.candidates[0].content
    parts = content.parts or []
    # Join the visible text parts (skip the model's hidden "thought" parts).
    text = "".join(p.text for p in parts if p.text and not p.thought).strip()
    tool_calls = [
        ToolCall(name=p.function_call.name, arguments=dict(p.function_call.args or {}), id=p.function_call.id)
        for p in parts
        if p.function_call
    ]
    if not text and not tool_calls:
        return LLMResult(
            failed=True,
            error=f"Gemini returned no answer (finish reason: {response.candidates[0].finish_reason})",
        )
    return LLMResult(text=text, tool_calls=tool_calls, provider_data=content)
