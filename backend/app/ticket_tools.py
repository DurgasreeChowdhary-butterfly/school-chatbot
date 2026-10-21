"""Concern tickets and callback requests: create_ticket, get_ticket_status, request_callback.
Categories and who handles them come from kb/<campus>/routing.json (mirrors escalation.md)."""
import logging
import re

from . import db, routing
from .llm.base import ToolSpec
from .notify import notify
from .validation import clean_name, clean_text, mask_mobile, normalize_mobile

log = logging.getLogger("chatbot.tickets")

MAX_FAILED_LOOKUPS = 5  # per chat session, to stop guessing of ticket numbers or mobiles
NO_MATCH = ("No ticket matches that reference and mobile number. Ask the person to check both. "
            "Do not say whether the ticket exists.")


def specs(campus: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="create_ticket",
            description=(
                "Log a parent's concern or suggestion for the right staff member. Use when something needs action "
                "(something pending, not done, a request to change something, or a safety concern)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": [c["name"] for c in routing.categories(campus)]},
                    "description": {"type": "string", "description": "The concern in the person's own words"},
                    "parent_name": {"type": "string"},
                    "mobile": {"type": "string", "description": "10-digit Indian mobile number, exactly as typed"},
                },
                "required": ["category", "description", "parent_name", "mobile"],
            },
        ),
        ToolSpec(
            name="get_ticket_status",
            description="Look up a ticket's status. Needs the ticket reference (like T-1001) AND the mobile number it was registered with.",
            parameters={
                "type": "object",
                "properties": {
                    "ticket_ref": {"type": "string", "description": "Like T-1001"},
                    "mobile": {"type": "string", "description": "The mobile number registered on the ticket"},
                },
                "required": ["ticket_ref", "mobile"],
            },
        ),
        ToolSpec(
            name="request_callback",
            description="Ask the front office to call the person back (for 'talk to a person' requests).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "mobile": {"type": "string", "description": "10-digit Indian mobile number, exactly as typed"},
                    "reason": {"type": "string", "description": "Optional: what they want to talk about"},
                },
                "required": ["name", "mobile"],
            },
        ),
    ]


def create_ticket(args: dict, ctx) -> dict:
    campus = ctx.campus
    problems = {}
    category = routing.category(campus, str(args.get("category") or ""))
    description = clean_text(args.get("description"), 500, required=True)
    name = clean_name(args.get("parent_name"))
    mobile = normalize_mobile(args.get("mobile"))
    if not category:
        problems["category"] = "Choose one of: " + ", ".join(c["name"] for c in routing.categories(campus))
    if not description:
        problems["description"] = "Ask the person to describe the concern in a sentence or two (max 500 characters)."
    if not name:
        problems["parent_name"] = "Ask for their name (letters only)."
    if not mobile:
        problems["mobile"] = "Not a valid 10-digit Indian mobile number. Ask the person to type it again."
    if problems:
        return {"error": "Some details need fixing. Ask the person about these only.", "problems": problems}

    urgent = bool(category.get("urgent"))
    row = db.insert("tickets", {
        "campus": campus, "category": category["name"], "description": description, "parent_name": name,
        "mobile": mobile, "urgent": int(urgent), "first_contact": category["first"],
        "backup_contact": category["backup"],
    })
    body = (f"Ticket {row['ref']}{' URGENT' if urgent else ''}\nCategory: {row['category']}\n"
            f"Concern: {description}\nParent: {name}\nMobile: {mobile}")
    first = routing.role(campus, category["first"])
    notify(campus, first, f"{'URGENT ' if urgent else ''}New ticket {row['ref']}: {row['category']}",
           body, row["ref"], "ticket")
    if urgent:
        # Safety concerns: tell the backup and the front office straight away too.
        for role in {category["backup"], routing.load(campus)["front_office"]} - {category["first"]}:
            notify(campus, routing.role(campus, role), f"URGENT ticket {row['ref']}: {row['category']}",
                   body, row["ref"], "ticket")
    log.info("Ticket %s (%s) created for %s", row["ref"], row["category"], mask_mobile(mobile))

    result = {
        "status": "created",
        "ref": row["ref"],
        "sent_to": first["name"],
        "urgent": urgent,
        "message": "Tell the person their ticket reference, who it was sent to, and that they can check "
                   "its status here with the reference and their mobile number.",
    }
    if urgent:
        phone = routing.front_office(campus).get("phone", "")
        result["message"] = (f"This is urgent. Tell the person to call the front office now on {phone}, "
                             f"and that the principal has been alerted. Then give the ticket reference.")
    return result


def get_ticket_status(args: dict, ctx) -> dict:
    session = ctx.session
    if session.failed_lookups >= MAX_FAILED_LOOKUPS:
        return {"error": "Too many attempts in this chat. Ask the person to contact the front office instead."}

    ref = str(args.get("ticket_ref") or "").strip().upper()
    mobile = normalize_mobile(args.get("mobile"))
    if not re.fullmatch(r"T-\d{1,8}", ref) or not mobile:
        session.failed_lookups += 1
        return {"error": "Ask for the ticket reference (like T-1001) and the 10-digit mobile number used for it."}

    ticket = db.find_one("tickets", ref=ref, campus=ctx.campus)
    if not ticket or ticket["mobile"] != mobile:
        session.failed_lookups += 1
        log.info("Ticket lookup failed for %s", ref)
        return {"status": "no_match", "message": NO_MATCH}

    return {
        "ref": ticket["ref"],
        "category": ticket["category"],
        "status": ticket["status"],
        "handled_by": ticket["first_contact"],
        "logged_on": ticket["created_at"][:10],
    }


def request_callback(args: dict, ctx) -> dict:
    campus = ctx.campus
    problems = {}
    name = clean_name(args.get("name"))
    mobile = normalize_mobile(args.get("mobile"))
    reason = clean_text(args.get("reason"), 300)
    if not name:
        problems["name"] = "Ask for their name (letters only)."
    if not mobile:
        problems["mobile"] = "Not a valid 10-digit Indian mobile number. Ask the person to type it again."
    if reason is None:
        problems["reason"] = "Too long. Ask for a shorter reason."
    if problems:
        return {"error": "Some details need fixing. Ask the person about these only.", "problems": problems}

    front = routing.front_office(campus)
    row = db.insert("callbacks", {"campus": campus, "name": name, "mobile": mobile, "reason": reason,
                                  "assigned_to": front["role"]})
    notify(campus, front, f"Callback request {row['ref']}",
           f"Callback {row['ref']}\nName: {name}\nMobile: {mobile}\nAbout: {reason or '-'}", row["ref"], "callback")
    log.info("Callback %s requested for %s", row["ref"], mask_mobile(mobile))
    return {"status": "created", "ref": row["ref"],
            "message": "Tell the person the front office will call them back during office hours."}


HANDLERS = {
    "create_ticket": create_ticket,
    "get_ticket_status": get_ticket_status,
    "request_callback": request_callback,
}
