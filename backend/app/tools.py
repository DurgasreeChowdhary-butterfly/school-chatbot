"""Tools the AI can ask the backend to run. Each tool has a spec (what the AI sees)
and a handler (what our code does). The backend always validates the AI's arguments."""
from dataclasses import dataclass

from .llm.base import ToolCall, ToolSpec
from .sessions import Session


@dataclass
class ToolContext:
    session: Session
    campus: str
    action: str | None = None  # an extra instruction for the chat window, e.g. "consent"


def specs_for(campus: str) -> list[ToolSpec]:
    """The tools offered to the AI for this campus. (Added in later stages.)"""
    return []


def run_tool(call: ToolCall, ctx: ToolContext) -> dict:
    return {"error": f"Unknown tool '{call.name}'."}
