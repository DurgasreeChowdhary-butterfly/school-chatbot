"""The chat loop: send the rules + conversation to the AI, run any tools it asks for,
and return its final reply. Any failure becomes a friendly message."""
import json
import logging
from dataclasses import dataclass
from datetime import date

from . import sessions, tools
from .llm.base import LLMProvider, Message
from .prompts import build_system_prompt

log = logging.getLogger("chatbot")

FALLBACK_REPLY = "I'm having trouble right now. Please call the front office."
MAX_TOOL_ROUNDS = 4  # stop if the AI keeps asking for tools


@dataclass
class ChatOutcome:
    reply: str
    action: str | None = None
    failed: bool = False


def handle_message(
    provider: LLMProvider,
    session: sessions.Session,
    campus: str,
    knowledge: str,
    text: str,
    group: str | None = None,
) -> ChatOutcome:
    session.turn += 1
    ctx = tools.ToolContext(session=session, campus=campus)
    system_prompt = build_system_prompt(knowledge, date.today().strftime("%A %d %B %Y"), group)
    user_message = Message(role="user", content=text)
    conversation = [*session.history, user_message]
    specs = tools.specs_for(campus) or None

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            result = provider.generate(system_prompt, conversation, specs)
        except Exception:
            log.exception("Provider error")
            return ChatOutcome(FALLBACK_REPLY, failed=True)
        if result.failed:
            log.error("Provider failed: %s", result.error)
            return ChatOutcome(FALLBACK_REPLY, failed=True)

        if not result.tool_calls:
            if not result.text:
                log.error("Provider returned an empty reply")
                return ChatOutcome(FALLBACK_REPLY, failed=True)
            # Only the visible conversation is remembered, not the tool steps.
            sessions.remember(session, user_message, Message(role="assistant", content=result.text))
            return ChatOutcome(result.text, action=ctx.action)

        # The AI asked for tools: run them and send the results back.
        conversation.append(
            Message(role="assistant", content=result.text, tool_calls=result.tool_calls,
                    provider_data=result.provider_data)
        )
        for call in result.tool_calls:
            output = tools.run_tool(call, ctx)
            log.info("Tool %s -> %s", call.name, "error" if "error" in output else "ok")
            conversation.append(
                Message(role="tool", content=json.dumps(output), tool_call_id=call.id, name=call.name)
            )

    log.error("Gave up after %s tool rounds", MAX_TOOL_ROUNDS)
    return ChatOutcome(FALLBACK_REPLY, failed=True)
