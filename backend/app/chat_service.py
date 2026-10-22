"""The chat loop: send the rules + conversation to the AI, run any tools it asks for,
and return its final reply. Any failure becomes a friendly message."""
import json
import logging
import re
from dataclasses import dataclass
from datetime import date

from . import routing, sessions, tools
from .llm.base import LLMProvider, Message
from .prompts import build_system_prompt

log = logging.getLogger("chatbot")

FALLBACK_REPLY = "I'm having trouble right now. Please call the front office."
MAX_TOOL_ROUNDS = 4  # stop if the AI keeps asking for tools
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+91[\s-]*)?(?<!\d)\d{5}[\s-]?\d{5}(?!\d)")
CONTACT_CHECK = ("Check before sending: your reply contains contact details that are not in the KNOWLEDGE: {found}. "
                 "Write the reply again for the person, using only email addresses and phone numbers exactly as "
                 "written in the KNOWLEDGE. If the KNOWLEDGE has no contact for this, give the front office instead. "
                 "Do not mention this check.")


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
    contacts_checked = False
    # Contact details a reply may contain: those in the KNOWLEDGE or typed in the conversation.
    known_text = "\n".join([knowledge, *(m.content for m in conversation)])

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
            reply = repair_emails(result.text, knowledge)
            # Contact details the AI made up (found in the consistency test): ask once for a corrected reply.
            unknown = unknown_contacts(reply, known_text)
            if unknown and not contacts_checked:
                contacts_checked = True
                log.warning("Reply had %s contact detail(s) not in the knowledge; asking for a corrected reply",
                            len(unknown))
                conversation += [Message(role="assistant", content=result.text, provider_data=result.provider_data),
                                 Message(role="user", content=CONTACT_CHECK.format(found=", ".join(unknown)))]
                continue
            if unknown:
                reply = replace_contacts(reply, unknown, campus)
            # Only the visible conversation is remembered, not the tool steps.
            sessions.remember(session, user_message, Message(role="assistant", content=reply))
            return ChatOutcome(reply, action=ctx.action)

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


def repair_emails(reply: str, knowledge: str) -> str:
    """The AI sometimes garbles an email address it copies from the KNOWLEDGE, for example "hr.example.com" or
    "hr at example.com" for hr@example.com (found in the consistency test). Put the exact address back."""
    for email in sorted(set(EMAIL.findall(knowledge)), key=len, reverse=True):
        local, domain = email.split("@", 1)
        garbled = re.compile(rf"(?<![\w.@+-]){re.escape(local)}(?:\.|\s+at\s+|\s*[\[(]at[\])]\s*|\s+)"
                             rf"{re.escape(domain)}(?![\w-])", re.IGNORECASE)
        reply, count = garbled.subn(email, reply)
        if count:
            log.warning("Repaired %s garbled email address(es) in a reply", count)
    return reply


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-10:]


def unknown_contacts(reply: str, known_text: str) -> list[str]:
    """Email addresses and phone numbers in the reply that appear nowhere in the KNOWLEDGE or the conversation."""
    known_emails = {e.lower() for e in EMAIL.findall(known_text)}
    known_phones = {_digits(p) for p in PHONE.findall(known_text)}
    found = [e for e in EMAIL.findall(reply) if e.lower() not in known_emails]
    found += [p for p in PHONE.findall(reply) if _digits(p) not in known_phones]
    return list(dict.fromkeys(found))


def replace_contacts(reply: str, unknown: list[str], campus: str) -> str:
    """Last resort: never pass on a made-up contact. Point to the front office instead."""
    front = routing.front_office(campus)
    instead = f"the front office ({front['phone']})" if front.get("phone") else "the front office"
    for item in unknown:
        reply = reply.replace(item, instead)
    log.warning("Replaced %s made-up contact detail(s) with the front office", len(unknown))
    return reply
