"""Tools the AI can ask the backend to run. Each tool has a spec (what the AI sees)
and a handler (what our code does). The backend always validates the AI's arguments."""
import logging
from dataclasses import dataclass

from . import enquiry_tools, ticket_tools
from .llm.base import ToolCall, ToolSpec
from .sessions import Session

log = logging.getLogger("chatbot.tools")

# Each module offers specs(campus) and a HANDLERS dict.
TOOL_MODULES = [enquiry_tools, ticket_tools]


@dataclass
class ToolContext:
    session: Session
    campus: str
    action: str | None = None  # an extra instruction for the chat window, e.g. "consent"


def specs_for(campus: str) -> list[ToolSpec]:
    """The tools offered to the AI for this campus."""
    return [spec for module in TOOL_MODULES for spec in module.specs(campus)]


def run_tool(call: ToolCall, ctx: ToolContext) -> dict:
    handler = next((m.HANDLERS[call.name] for m in TOOL_MODULES if call.name in m.HANDLERS), None)
    if handler is None:
        return {"error": f"Unknown tool '{call.name}'."}
    try:
        return handler(call.arguments or {}, ctx)
    except Exception:
        log.exception("Tool %s crashed", call.name)
        return {"error": "Something went wrong on our side. Offer to connect the person to the front office."}
