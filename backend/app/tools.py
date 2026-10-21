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

# Tools that store personal details: they only run after the visitor agreed to the privacy notice.
NEEDS_CONSENT = {"submit_enquiry", "confirm_enquiry", "create_ticket", "request_callback"}

CONSENT_SPEC = ToolSpec(
    name="request_consent",
    description=(
        "Call this BEFORE asking for any personal details (names, mobile number) for an enquiry, visit, "
        "concern or callback. It shows the privacy notice with an 'I agree' button, or says consent was already given."
    ),
    parameters={
        "type": "object",
        "properties": {"purpose": {"type": "string", "enum": ["enquiry", "concern", "callback"]}},
        "required": ["purpose"],
    },
)


@dataclass
class ToolContext:
    session: Session
    campus: str
    action: str | None = None  # an extra instruction for the chat window, e.g. "consent"


def specs_for(campus: str) -> list[ToolSpec]:
    """The tools offered to the AI for this campus."""
    return [CONSENT_SPEC] + [spec for module in TOOL_MODULES for spec in module.specs(campus)]


def run_tool(call: ToolCall, ctx: ToolContext) -> dict:
    if call.name == "request_consent":
        return _request_consent(ctx)
    handler = next((m.HANDLERS[call.name] for m in TOOL_MODULES if call.name in m.HANDLERS), None)
    if handler is None:
        return {"error": f"Unknown tool '{call.name}'."}
    if call.name in NEEDS_CONSENT and not ctx.session.consent_at:
        ctx.action = "consent"
        return {"error": "consent_required",
                "instruction": "Nothing was saved. A privacy notice is now shown to the person. Tell them briefly "
                               "to tap 'I agree' below if they want to continue, then wait."}
    try:
        return handler(call.arguments or {}, ctx)
    except Exception:
        log.exception("Tool %s crashed", call.name)
        return {"error": "Something went wrong on our side. Offer to connect the person to the front office."}


def _request_consent(ctx: ToolContext) -> dict:
    if ctx.session.consent_at:
        return {"status": "consent_given", "instruction": "Consent is already given. Ask for the details."}
    ctx.action = "consent"
    return {"status": "notice_shown",
            "instruction": "A short privacy notice with an 'I agree' button is now shown below your message. "
                           "In one or two sentences, ask the person to read it and tap 'I agree' to continue. "
                           "Do not ask for any details in this message."}
